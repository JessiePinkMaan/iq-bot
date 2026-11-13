"""Автономная проверка ядра без Telegram.

Запуск: python scripts/selftest.py
Проверяет вопросы, БД, ответы, идемпотентность оплаты, отчёты,
подписи платежей, защиту от чужих результатов и наличие ассетов.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config import ASSETS_DIR, Settings
from bot.database import Database
from bot.questions import CATEGORIES, QUESTIONS, validate_questions
from bot.scoring import analyze
from bot.texts import (
    admin_home,
    admin_results,
    admin_users,
    details_text,
    locked_caption,
    question_text,
    report_caption,
    report_error_chunks,
    report_profile,
    report_summary,
    results_list_text,
    welcome_caption,
)

PASSED = 0


def ok(label: str) -> None:
    global PASSED
    PASSED += 1
    print(f"  OK  {label}")


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"FAIL: {label}")
    ok(label)


def make_settings(db_path: Path) -> Settings:
    return Settings(
        bot_token="123456789:TEST-TOKEN-FOR-SELFTEST",
        admin_ids=frozenset({1001}),
        payment_secret="selftest-secret-key",
        price_stars=50,
        db_path=db_path,
        timezone="Europe/Moscow",
        log_level="INFO",
        brand="NOEMA",
        support_contact="@support",
        assets_dir=ASSETS_DIR,
        env_path=ROOT / ".env",
    )


async def run() -> None:
    print("\n[1] Вопросы и категории")
    validate_questions()
    ok("20 вопросов проходят структурную валидацию")
    check([q.index for q in QUESTIONS] == list(range(1, 21)), "индексы 1..20")
    check(len({q.text for q in QUESTIONS}) == 20, "тексты уникальны")
    check(all(len(q.options) == 4 for q in QUESTIONS), "у всех по 4 варианта")
    check(all(len(set(q.options)) == 4 for q in QUESTIONS), "варианты уникальны")
    check(all(0 <= q.correct_index < 4 for q in QUESTIONS), "правильные ответы валидны")
    check(all(q.explanation.strip() for q in QUESTIONS), "у всех есть объяснение")
    check(
        [q.difficulty for q in QUESTIONS] == sorted(q.difficulty for q in QUESTIONS),
        "сложность не убывает",
    )
    counts = {key: sum(1 for q in QUESTIONS if q.category == key) for key in CATEGORIES}
    check(all(value >= 2 for value in counts.values()), f"все 7 категорий покрыты: {counts}")
    check(sum(counts.values()) == 20, "категории покрывают все 20 вопросов")

    print("\n[2] Тексты и лимиты Telegram")
    welcome = welcome_caption(None, False)
    check(len(welcome) < 1024, f"приветствие помещается в caption ({len(welcome)})")
    check("правильных ответов" not in welcome.lower(), "приветствие не раскрывает результат")
    locked = locked_caption(50)
    check(len(locked) < 1024, f"paywall помещается в caption ({len(locked)})")
    check("правильных ответов" not in locked.lower(), "paywall не раскрывает число ответов")
    check("70%" not in locked and "14 / 20" not in locked, "paywall не раскрывает точность")
    q9 = QUESTIONS[8]
    check(bool(q9.image), "у визуального вопроса есть изображение")
    check(len(question_text(q9, 8)) < 1024, "текст визуального вопроса помещается в caption")
    check(len(details_text(50)) < 4096, "экран «что входит» в лимите")

    print("\n[3] База, прохождение, защита от параллельных тестов")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.sqlite3"
        settings = make_settings(db_path)
        db = Database(db_path)
        await db.init()
        ok("схема БД создана")

        user1 = await db.upsert_user(111, "alice", "Алиса", "Иванова", "ru")
        user2 = await db.upsert_user(222, "bob", "Боб", None, "ru")
        check(user1.id == 111 and user2.id == 222, "пользователи сохранены")
        check((await db.get_admin_stats()).users_total == 2, "статистика видит пользователей")

        test1, created = await db.create_test(111)
        check(created and test1.status == "in_progress", "первый тест создан")
        duplicate_active, created_again = await db.create_test(111)
        check(not created_again and duplicate_active.id == test1.id, "второй активный тест не создаётся")

        out_of_order = await db.record_answer(111, test1.id, 2, 0)
        check(out_of_order.status == "stale", "ответ не по порядку отклонён")

        wrong_owner = await db.record_answer(222, test1.id, 1, 0)
        check(wrong_owner.status == "not_found", "чужой пользователь не может отвечать")

        for question in QUESTIONS:
            if question.index <= 14:
                choice = question.correct_index
            else:
                choice = (question.correct_index + 1) % 4
            outcome = await db.record_answer(111, test1.id, question.index, choice)
            expected = "completed" if question.index == 20 else "ok"
            if outcome.status != expected:
                raise AssertionError(
                    f"вопрос {question.index}: ожидался {expected}, получен {outcome.status}"
                )
        ok("20 ответов записаны, тест завершён")
        check((await db.get_test(test1.id)).correct_count == 14, "подсчёт верных ответов = 14")
        duplicate = await db.record_answer(111, test1.id, 20, 0)
        check(duplicate.status == "not_active", "повторный ответ после завершения отклонён")
        check((await db.get_test(test1.id)).paid == 0, "до оплаты результат закрыт")

        await db.abandon_active_test(111)
        check((await db.get_active_test(111)) is None, "abandon снимает активную сессию")
        test1b, created_b = await db.create_test(111)
        check(created_b and test1b.id != test1.id, "после завершения можно начать новый тест")

        print("\n[4] Оплата и идемпотентность")
        payload = settings.make_payment_payload(test1.id, 111)
        check(
            settings.parse_payment_payload(payload) == (test1.id, 111, 50),
            "payload подписан и читается вместе с ценой",
        )
        tampered = payload[:-1] + ("0" if payload[-1] != "0" else "1")
        check(settings.parse_payment_payload(tampered) is None, "подделанный payload отклонён")
        parts = payload.split(":")
        parts[3] = "1"
        price_tampered = ":".join(parts)
        check(
            settings.parse_payment_payload(price_tampered) is None,
            "подмена цены в payload отклонена",
        )

        paid = await db.mark_paid(111, test1.id, "charge-1", "provider-1", 50, "XTR", payload)
        check(paid.status == "ok" and paid.test and paid.test.paid == 1, "оплата разблокирует тест")
        stats = await db.get_admin_stats()
        check(stats.revenue_stars == 50, "выручка = 50 Stars")
        check(stats.tests_paid == 1 and stats.tests_completed == 1, "оплаченный тест учтён")

        second_payment = await db.mark_paid(
            111, test1.id, "charge-2", "provider-2", 50, "XTR", payload
        )
        check(second_payment.status == "already_paid", "повторная оплата не разблокирует заново")
        check((await db.get_admin_stats()).revenue_stars == 50, "повторный платёж не раздувает выручку")

        duplicate_charge = await db.mark_paid(
            111, test1.id, "charge-1", "provider-1", 50, "XTR", payload
        )
        check(duplicate_charge.status == "duplicate_charge", "charge_id защищён UNIQUE")

        check((await db.get_payment_for_test(test1.id)).status == "paid", "платёж сохранён")

        print("\n[5] Аналитика и отчёт")
        answers = await db.get_answers(test1.id)
        analysis = analyze(await db.get_test(test1.id), answers)
        check(analysis.correct == 14 and analysis.total == 20, "анализ: 14 из 20")
        check(analysis.accuracy == 70, "точность 70%")
        check(len(analysis.categories) == 7, "7 категорий в профиле")
        check(sum(stat.total for stat in analysis.categories) == 20, "категории покрывают 20 вопросов")
        check(len(analysis.wrong) == 6, "6 ошибок для разбора")
        check(all(explanation for _ans, question in analysis.wrong for explanation in [question.explanation]), "у ошибок есть объяснения")
        check("70%" in report_summary(analysis), "итог содержит точность")
        check("70%" in report_caption(analysis), "caption содержит точность после оплаты")
        check("СИЛЬНЫЕ СТОРОНЫ" in report_profile(analysis), "профиль содержит сильные стороны")
        chunks = report_error_chunks(analysis)
        check(all(len(chunk) < 4096 for chunk in chunks), f"разбор ошибок разбит на {len(chunks)} сообщение(й)")

        print("\n[6] Чужие результаты и сохранность после перезапуска")
        other_test, _ = await db.create_test(222)
        for question in QUESTIONS:
            await db.record_answer(222, other_test.id, question.index, question.correct_index)
        paid_other = await db.mark_paid(
            222, other_test.id, "charge-3", "provider-3", 50, "XTR",
            settings.make_payment_payload(other_test.id, 222),
        )
        check(paid_other.status == "ok", "второй пользователь оплатил свой тест")
        cross = await db.mark_paid(
            111, other_test.id, "charge-4", "provider-4", 50, "XTR",
            settings.make_payment_payload(other_test.id, 222),
        )
        check(cross.status == "wrong_owner", "нельзя оплатить/открыть чужой тест")
        stats = await db.get_admin_stats()
        check(stats.revenue_stars == 100 and stats.tests_paid == 2, "выручка двух оплат = 100")
        check(stats.tests_completed == 2, "завершённых тестов два")

        recent = await db.recent_results(10)
        check(len(recent) == 2, "админ видит последние результаты")
        check("ПОЛЬЗОВАТЕЛИ" in admin_users(await db.recent_users(10), "Europe/Moscow"), "админ-список пользователей собирается")
        check("РЕЗУЛЬТАТЫ" in admin_results(recent, "Europe/Moscow"), "админ-список результатов собирается")
        check("АДМИН-ПАНЕЛЬ" in admin_home(stats), "админ-статистика собирается")
        check(len(results_list_text(await db.get_user_results(111), "Europe/Moscow")) < 4096, "архив результатов в лимите")
        check(len(await db.all_user_ids()) == 2, "рассылка видит двух получателей")

        db_reopened = Database(db_path)
        restored = await db_reopened.get_test(test1.id)
        check(restored is not None and restored.paid == 1, "оплата сохраняется после перезапуска")
        restored_answers = await db_reopened.get_answers(test1.id)
        check(len(restored_answers) == 20, "ответы сохраняются после перезапуска")
        check((await db_reopened.get_user(111)).tests_completed == 1, "счётчик тестов сохраняется")

        print("\n[7] Крайние случаи отчёта")
        await db.upsert_user(333, "carol", "Кэрол", None, "ru")
        worst_test, _ = await db.create_test(333)
        for question in QUESTIONS:
            wrong_choice = (question.correct_index + 1) % 4
            await db.record_answer(333, worst_test.id, question.index, wrong_choice)
        worst = analyze(await db.get_test(worst_test.id), await db.get_answers(worst_test.id))
        check(worst.correct == 0 and worst.accuracy == 0, "нулевой результат считается")
        check(worst.band.title == "Стартовая точка", "для нуля выбрана корректная интерпретация")
        check(len(report_summary(worst)) < 4096, "summary нулевого результата в лимите")
        check(len(report_profile(worst)) < 4096, "профиль нулевого результата в лимите")
        worst_chunks = report_error_chunks(worst)
        check(
            all(len(chunk) < 4096 for chunk in worst_chunks),
            f"20 ошибок разбиты на {len(worst_chunks)} безопасных сообщений",
        )
        check(len(worst.wrong) == 20, "все 20 ошибок попадают в разбор")

    print("\n[8] Изображения")
    required = ["hero.jpg", "analysis.jpg", "locked.jpg", "unlocked.jpg", "report.jpg", "q09.jpg"]
    for name in required:
        path = ASSETS_DIR / name
        check(path.exists() and path.stat().st_size > 20_000, f"{name} существует")
        with Image.open(path) as image:
            check(image.width >= 1000 and image.height >= 700, f"{name} корректного размера")
    ok("все изображения на месте")

    print(f"\nВСЕ ПРОВЕРКИ ПРОЙДЕНЫ: {PASSED}")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except AssertionError as exc:
        print(f"\n{exc}")
        raise SystemExit(1) from None
