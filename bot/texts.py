"""Вся визуальная и текстовая система NOEMA.

Единый голос бренда: короткие фразы, воздух, тонкие разделители,
сдержанные акценты и никаких обещаний «научного IQ».
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import AdminStats, TestRecord, UserRecord
from .questions import CATEGORIES, TOTAL_QUESTIONS, Question
from .scoring import Analysis, CategoryStat, answer_letter, correct_letter

BRAND = "NOEMA"
DIVIDER = "━━━━━━━━━━━━"
THIN = "────────────"
TOTAL = TOTAL_QUESTIONS

# ------------------------------------------------------------------ утилиты


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def plural_ru(number: int, one: str, few: str, many: str) -> str:
    n = abs(number) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def format_dt(iso_value: str | None, tz_name: str = "Europe/Moscow", with_year: bool = True) -> str:
    if not iso_value:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        try:
            dt = dt.astimezone(ZoneInfo(tz_name))
        except ZoneInfoNotFoundError:
            dt = dt.astimezone(UTC)
        pattern = "%d.%m.%Y · %H:%M" if with_year else "%d.%m · %H:%M"
        return dt.strftime(pattern)
    except (ValueError, TypeError):
        return "-"


def progress_bar(answered: int, total: int = TOTAL, width: int = 20) -> str:
    filled = max(0, min(width, round(answered / total * width)))
    return "▰" * filled + "▱" * (width - filled)


def percent_bar(percent: int, width: int = 10) -> str:
    filled = max(0, min(width, round(percent / 100 * width)))
    return "▰" * filled + "▱" * (width - filled)


def short_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


# ------------------------------------------------------------------ основные экраны


def welcome_caption(active: TestRecord | None, has_unpaid: bool) -> str:
    text = (
        "🧠 <b>ДОБРО ПОЖАЛОВАТЬ В IQ TEST</b>\n"
        "<code>NOEMA · INTELLECTUAL ASSESSMENT</code>\n"
        f"{DIVIDER}\n\n"
        "<b>Насколько силён твой интеллект?</b>\n\n"
        "20 авторских заданий на логику, числовые и абстрактные "
        "закономерности.\n\n"
        "В конце тебя ждёт персональный отчёт: результат, профиль "
        "по 7 категориям и разбор решений.\n\n"
        "Когда будешь готов, нажми «Старт».\n\n"
        "<blockquote>⏱ 7-12 минут · 7 категорий · 20 заданий</blockquote>"
    )
    if active:
        text += (
            "\n\n<b>НЕЗАКОНЧЕННАЯ СЕССИЯ</b>\n"
            f"Вопрос <b>{active.current_index + 1} / {TOTAL}</b>. "
            "Ответы сохранены. Продолжи с того же места."
        )
    elif has_unpaid:
        text += (
            "\n\n<b>ОТЧЁТ УЖЕ ГОТОВ</b>\n"
            "Результат защищён до оплаты. Открой его, когда будешь готов."
        )
    return text


def question_text(question: Question, answered: int) -> str:
    percent = round(answered / TOTAL * 100)
    return (
        f"<code>ВОПРОС {question.index:02d} / {TOTAL}  ·  {percent}%</code>\n"
        f"{progress_bar(answered)}\n\n"
        f"<b>{esc(question.category_title)}</b>\n"
        f"<code>УРОВЕНЬ {question.difficulty} ИЗ 5 · {question.difficulty_dots()}</code>\n"
        f"{DIVIDER}\n\n"
        f"{question.text}\n\n"
        "<blockquote>Выбери один ответ. Вернуться назад будет нельзя.</blockquote>"
    )


def analysis_caption(step: int) -> str:
    stages = (
        (
            14,
            "СЧИТЫВАЕМ ОТВЕТЫ",
            "Проверяем целостность сессии и фиксируем 20 ответов.",
        ),
        (
            43,
            "СВЕРЯЕМ РЕШЕНИЯ",
            "Сопоставляем ответы с ключами по 7 категориям мышления.",
        ),
        (
            76,
            "СТРОИМ ПРОФИЛЬ",
            "Собираем сильные стороны, зоны роста и разбор ошибок.",
        ),
        (
            100,
            "ОТЧЁТ СФОРМИРОВАН",
            "Персональный анализ готов. Доступ защищён до оплаты.",
        ),
    )
    percent, title, subtitle = stages[max(0, min(step, 3))]
    return (
        "⚙️ <b>АНАЛИТИЧЕСКИЙ ДВИЖОК</b>\n"
        "<code>NOEMA · PROCESSING</code>\n"
        f"{DIVIDER}\n\n"
        f"<code>ЭТАП {step + 1} ИЗ 4  ·  {percent}%</code>\n"
        f"{percent_bar(percent)}\n\n"
        f"<b>{title}</b>\n"
        f"{subtitle}"
    )


def locked_caption(price: int) -> str:
    return (
        "🔒 <b>ПЕРСОНАЛЬНЫЙ ОТЧЁТ ГОТОВ</b>\n"
        "<code>NOEMA · REPORT LOCKED</code>\n"
        f"{DIVIDER}\n\n"
        "20 ответов обработаны. Профиль по 7 категориям и разбор "
        "решений уже сформированы.\n\n"
        "<b>ЧТО ВНУТРИ</b>\n"
        "01 · Верные ответы и точность\n"
        "02 · Профиль по 7 категориям\n"
        "03 · Сильные стороны и зоны роста\n"
        "04 · Разбор сложных заданий\n\n"
        f"<blockquote>Открыть отчёт: <b>{price} ⭐</b>\n"
        "Один платёж. Доступ навсегда.</blockquote>"
    )


def details_text(price: int) -> str:
    return (
        "◆ <b>ЧТО ВХОДИТ В ОТЧЁТ</b>\n"
        "<code>NOEMA · PERSONAL REPORT</code>\n"
        f"{DIVIDER}\n\n"
        "<b>01 · Результат</b>\n"
        "Верные ответы, точность и общий уровень.\n\n"
        "<b>02 · Профиль</b>\n"
        "Результат по 7 категориям: числа, логика, пространство, "
        "абстракция, аналитика, паттерны, математика.\n\n"
        "<b>03 · Интерпретация</b>\n"
        "Сильные стороны и зоны роста. Без клинических ярлыков "
        "и выдуманного коэффициента IQ.\n\n"
        "<b>04 · Разбор</b>\n"
        "Объяснение правильного решения для каждого задания, "
        "которое вызвало трудности.\n\n"
        f"<blockquote>Полный отчёт: <b>{price} ⭐</b>\n"
        "Доступ сохраняется в «Моих результатах» навсегда.</blockquote>"
    )


def about_text() -> str:
    return (
        "◆ <b>О ПРОЕКТЕ</b>\n"
        "<code>NOEMA · INTELLECTUAL ASSESSMENT</code>\n"
        f"{DIVIDER}\n\n"
        "<b>Интеллект как система навыков</b>\n\n"
        "NOEMA: авторский тест о том, как ты работаешь с логикой, числами, "
        "пространством и абстракцией.\n\n"
        "Здесь нет вопросов на школьную эрудицию. Каждое задание проверяет "
        "умение найти правило, удержать условие и сделать точный вывод.\n\n"
        "<b>КАК ЭТО УСТРОЕНО</b>\n"
        "- 20 уникальных заданий;\n"
        "- 7 категорий мышления;\n"
        "- сложность растёт постепенно;\n"
        "- прогресс сохраняется автоматически;\n"
        "- отчёт открывается после оплаты и остаётся доступным.\n\n"
        "<blockquote>Это авторский тест, а не клиническая шкала IQ. "
        "Мы показываем объективный результат и аналитический профиль, "
        "а не выдуманный коэффициент.</blockquote>"
    )



def results_list_text(results: list[TestRecord], tz_name: str) -> str:
    if not results:
        return (
            "📊 <b>МОИ РЕЗУЛЬТАТЫ</b>\n"
            "<code>NOEMA · ARCHIVE</code>\n"
            f"{DIVIDER}\n\n"
            "Пока здесь пусто.\n\n"
            "Заверши тест, и здесь появится персональный отчёт. "
            "Оплаченные результаты можно открывать повторно в любое время."
        )
    lines = [
        "📊 <b>МОИ РЕЗУЛЬТАТЫ</b>",
        "<code>NOEMA · ARCHIVE</code>",
        DIVIDER,
        "",
        "Оплаченные отчёты открываются повторно, без новой оплаты.",
        "",
    ]
    for test in results[:8]:
        date = format_dt(test.completed_at, tz_name)
        number = f"№{test.id:04d}"
        if test.paid:
            lines.append(
                f"<b>{number}</b>  ·  <b>{test.correct_count} / {TOTAL}</b>  ·  "
                f"{test.accuracy}%\n<code>{date} · доступ открыт</code>"
            )
        else:
            lines.append(
                f"<b>{number}</b>  ·  отчёт готов\n<code>{date} · ожидает оплаты</code>"
            )
        lines.append("")
    if len(results) > 8:
        lines.append(f"\n<i>Показаны 8 последних из {len(results)}.</i>")
    lines.append(
        "\n<blockquote>Каждый отчёт привязан к своему владельцу. "
        "Чужие результаты недоступны.</blockquote>"
    )
    return "\n".join(lines)


# ------------------------------------------------------------------ отчёт


def report_caption(analysis: Analysis) -> str:
    return (
        "✅ <b>ДОСТУП ОТКРЫТ</b>\n"
        "<code>NOEMA · PERSONAL REPORT</code>\n"
        f"{DIVIDER}\n\n"
        "Оплата подтверждена. Персональный отчёт разблокирован.\n\n"
        f"<b>{analysis.correct} / {analysis.total}</b>  ·  точность {analysis.accuracy}%"
    )


def report_summary(analysis: Analysis) -> str:
    return (
        "🧠 <b>ТВОЙ РЕЗУЛЬТАТ</b>\n"
        "<code>NOEMA · INTELLECTUAL ASSESSMENT</code>\n"
        f"{DIVIDER}\n\n"
        "<b>ПРАВИЛЬНЫХ ОТВЕТОВ</b>\n"
        f"<code>{analysis.correct} / {analysis.total}</code>   ·   "
        f"<b>точность {analysis.accuracy}%</b>\n"
        f"{analysis.score_bar}\n\n"
        "<b>АНАЛИТИЧЕСКИЙ ПРОФИЛЬ</b>\n"
        f"<b>{analysis.band.title}</b>\n"
        f"<i>{analysis.band.subtitle}</i>\n\n"
        f"{analysis.band.description}\n\n"
        f"<blockquote>Авторский тест. Это не клиническая оценка IQ, "
        f"а результат по конкретному набору из {TOTAL} заданий.</blockquote>"
    )


def _category_line(stat: CategoryStat) -> str:
    return (
        f"<b>{esc(stat.title)}</b>\n"
        f"{stat.bar}  {stat.correct}/{stat.total} · {stat.percent}%"
    )


def report_profile(analysis: Analysis) -> str:
    category_lines = "\n\n".join(_category_line(stat) for stat in analysis.categories)

    strength_lines: list[str] = []
    for stat in analysis.strengths:
        strength_lines.append(
            f"- <b>{esc(stat.title)}</b> · {stat.correct}/{stat.total}\n"
            f"  {CATEGORIES[stat.key].strength.capitalize()}."
        )

    growth_lines: list[str] = []
    for stat in analysis.growth:
        growth_lines.append(
            f"- <b>{esc(stat.title)}</b> · {stat.correct}/{stat.total} ({stat.percent}%)"
        )
    if analysis.growth and min(stat.percent for stat in analysis.growth) >= 75:
        growth_note = (
            "Профиль очень ровный: даже относительно более скромные категории "
            "показывают высокий результат."
        )
    else:
        growth_note = (
            "Это не «слабые места», а направления, где системная практика "
            "даст самый заметный прирост."
        )

    return (
        "<b>ПРОФИЛЬ ПО КАТЕГОРИЯМ</b>\n"
        f"{DIVIDER}\n\n"
        f"{category_lines}\n\n"
        f"{DIVIDER}\n"
        "<b>СИЛЬНЫЕ СТОРОНЫ</b>\n"
        + ("\n".join(strength_lines) if strength_lines else "- Пока не выделены.")
        + "\n\n<b>ЗОНЫ РОСТА</b>\n"
        + ("\n".join(growth_lines) if growth_lines else "- Пока не выделены.")
        + f"\n\n{growth_note}"
    )


def _error_block(answer_index: int, question: Question, chosen: int) -> str:
    return (
        f"<b>{question.index:02d} · {esc(question.category_title)}</b>\n"
        f"Твой ответ: <b>{answer_letter(chosen)} · {esc(question.options[chosen])}</b>\n"
        f"Верный ответ: <b>{correct_letter(question)} · {esc(question.correct_option)}</b>\n"
        f"<i>Почему:</i> {esc(question.explanation)}"
    )


def _pack_blocks(header: str, blocks: list[str], limit: int = 3600) -> list[str]:
    if not blocks:
        return [header]
    chunks: list[str] = []
    current = header
    for block in blocks:
        addition = "\n\n" + block
        if len(current) + len(addition) > limit and current != header:
            chunks.append(current)
            current = header + addition
        else:
            current += addition
    chunks.append(current)
    return chunks


def report_error_chunks(analysis: Analysis) -> list[str]:
    if not analysis.wrong:
        return [
            (
                "<b>РАЗБОР ЗАДАНИЙ</b>\n"
                f"{DIVIDER}\n\n"
                "Все 20 ответов верны. Разбирать нечего: это редкий "
                "и очень точный результат.\n\n"
                "Если хочешь проверить устойчивость, пройди тест ещё раз. "
                "Вопросы те же, но внимание и скорость уже другие."
            )
        ]

    header = (
        f"<b>РАЗБОР ЗАДАНИЙ</b>\n"
        f"<code>ОШИБКИ · {len(analysis.wrong)} ИЗ {TOTAL}</code>\n"
        f"{DIVIDER}\n\n"
        "Ниже только задания, где ответ отличался от ключа. "
        "У каждого есть короткое объяснение."
    )
    blocks = [
        _error_block(0, question, answer.option_index)
        for answer, question in analysis.wrong
    ]
    return _pack_blocks(header, blocks)


def report_final() -> str:
    return (
        f"{DIVIDER}\n"
        "<b>ЧТО ДАЛЬШЕ</b>\n\n"
        "Отчёт сохранён в «Моих результатах». Его можно открыть "
        "в любой момент, без повторной оплаты.\n\n"
        "<b>Хочешь проверить динамику?</b>\n"
        "Пройди тест заново. Вопросы те же, но внимание и скорость "
        "уже другие.\n\n"
        "<blockquote>NOEMA · авторский интеллектуальный тест. "
        "Не является клинической оценкой IQ.</blockquote>"
    )


def duplicate_payment_notice(price: int) -> str:
    return (
        "⚠️ <b>ПОВТОРНЫЙ ПЛАТЁЖ</b>\n"
        f"{DIVIDER}\n\n"
        f"Отчёт уже был оплачен ранее. Платёж на {price} ⭐ получен повторно: "
        "мы зафиксировали его и передали владельцу для возврата.\n\n"
        "Доступ к отчёту уже открыт. Повторная оплата не требуется."
    )


def payment_problem_notice(support: str = "") -> str:
    contact = f"\n\n<b>Поддержка:</b> {esc(support)}" if support else ""
    return (
        "⚠️ <b>ПЛАТЁЖ ПОЛУЧЕН, НО НЕ ПРИВЯЗАН</b>\n"
        f"{DIVIDER}\n\n"
        "Мы получили платёж, но не смогли автоматически сопоставить его "
        "с завершённым тестом.\n\n"
        "Напиши в поддержку и укажи дату оплаты: доступ восстановим вручную."
        + contact
    )



# ------------------------------------------------------------------ админ


def admin_home(stats: AdminStats) -> str:
    conversion = (
        round(stats.tests_paid / stats.tests_completed * 100)
        if stats.tests_completed
        else 0
    )
    avg = f"{stats.avg_score:.1f}%" if stats.avg_score is not None else "-"
    return (
        "⚙️ <b>АДМИН-ПАНЕЛЬ</b>\n"
        "<code>NOEMA · CONTROL ROOM</code>\n"
        f"{DIVIDER}\n\n"
        "<b>АУДИТОРИЯ</b>\n"
        f"Пользователи · <b>{short_number(stats.users_total)}</b>\n"
        f"Новые сегодня · <b>{short_number(stats.users_today)}</b>\n\n"
        "<b>ТЕСТЫ</b>\n"
        f"Запущено · <b>{short_number(stats.tests_started)}</b>\n"
        f"Завершено · <b>{short_number(stats.tests_completed)}</b>\n"
        f"Активных сессий · <b>{short_number(stats.active_tests)}</b>\n\n"
        "<b>ОПЛАТЫ</b>\n"
        f"Оплачено отчётов · <b>{short_number(stats.tests_paid)}</b>\n"
        f"Выручка · <b>{short_number(stats.revenue_stars)} ⭐</b>\n"
        f"Конверсия · <b>{conversion}%</b>\n"
        f"Средний результат · <b>{avg}</b>\n\n"
        "<blockquote>Доступ только для администраторов из ADMIN_IDS.</blockquote>"
    )


def admin_users(users: list[UserRecord], tz_name: str) -> str:
    if not users:
        return "👥 <b>ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ</b>\n\nПока пусто."
    lines = ["👥 <b>ПОСЛЕДНИЕ ПОЛЬЗОВАТЕЛИ</b>", DIVIDER, ""]
    for user in users:
        username = f"@{esc(user.username)}" if user.username else "без username"
        blocked = "\n<i>Заблокировал бота</i>" if user.is_blocked else ""
        lines.append(
            f"<b>{esc(user.display_name)}</b> · <code>{user.id}</code>\n"
            f"{username}\n"
            f"Регистрация: {format_dt(user.registered_at, tz_name)}\n"
            f"Тестов: {user.tests_completed} · Оплачено: {user.total_paid_stars} ⭐"
            f"{blocked}"
        )
    return "\n\n".join(lines)


def admin_results(
    results: list[tuple[TestRecord, UserRecord]], tz_name: str
) -> str:
    if not results:
        return "🧪 <b>ПОСЛЕДНИЕ РЕЗУЛЬТАТЫ</b>\n\nЗавершённых тестов пока нет."
    lines = ["🧪 <b>ПОСЛЕДНИЕ РЕЗУЛЬТАТЫ</b>", DIVIDER, ""]
    for test, user in results:
        paid = "✅ оплачен" if test.paid else "не оплачен"
        lines.append(
            f"<b>№{test.id:04d}</b> · <b>{test.correct_count}/{TOTAL}</b> · "
            f"{test.accuracy}% · {paid}\n"
            f"{esc(user.display_name)} · <code>{user.id}</code>\n"
            f"<code>{format_dt(test.completed_at, tz_name)}</code>"
        )
    return "\n\n".join(lines)


def admin_test_detail(
    test: TestRecord, user: UserRecord, answers: list, tz_name: str
) -> str:
    paid = f"✅ оплачен · {format_dt(test.paid_at, tz_name)}" if test.paid else "не оплачен"
    return (
        f"🧪 <b>ТЕСТ №{test.id:04d}</b>\n"
        f"{DIVIDER}\n\n"
        f"<b>ПОЛЬЗОВАТЕЛЬ</b>\n"
        f"{esc(user.display_name)} · <code>{user.id}</code>\n"
        f"{('@' + esc(user.username)) if user.username else 'без username'}\n\n"
        f"<b>РЕЗУЛЬТАТ</b>\n"
        f"{test.correct_count} / {TOTAL} · {test.accuracy}%\n"
        f"{paid}\n\n"
        f"<b>ДАТЫ</b>\n"
        f"Старт: {format_dt(test.started_at, tz_name)}\n"
        f"Финиш: {format_dt(test.completed_at, tz_name)}\n\n"
        f"<b>ОТВЕТЫ</b>\n"
        f"Записано: {len(answers)} из {TOTAL}\n\n"
        f"<code>test_id={test.id} · user_id={user.id}</code>"
    )

