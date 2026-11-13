"""Сквозной smoke-тест обработчиков без сети.

Создаёт фейковый Bot, который перехватывает все Telegram-вызовы, и
прогоняет полный сценарий: /start → 20 ответов → paywall → оплата → отчёт →
повторное открытие → чужие callback → админ-панель → рассылка.

Запуск: python scripts/flowtest.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    PhotoSize,
    PreCheckoutQuery,
    SuccessfulPayment,
    Update,
    User,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config import ASSETS_DIR, Settings
from bot.database import Database
from bot.handlers import admin, errors, payment, results, start, test
from bot.middlewares import PrivateChatMiddleware, UserSyncMiddleware
from bot.questions import QUESTIONS
from bot.services import AssetManager

CHECK = 0


def ok(label: str) -> None:
    global CHECK
    CHECK += 1
    print(f"  OK  {label}")


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(f"FAIL: {label}")
    ok(label)


class FakeSession:
    """Перехватывает все вызовы Telegram API через Bot.__call__."""

    def __init__(self, flow: Flow) -> None:
        self.flow = flow

    async def __call__(self, bot: Bot, method, timeout: float | None = None):
        return self.flow.handle_method(method)

    async def close(self) -> None:
        return None


class Flow:
    def __init__(self) -> None:
        self.bot = Bot(token="123456789:FLOW-TEST")
        self.captured: list[tuple[str, dict[str, Any]]] = []
        self.update_id = 0
        self.message_id = 100
        self.bot.session = FakeSession(self)  # type: ignore[assignment]

    def _next_message(
        self,
        *,
        chat_id: int = 111,
        user_id: int = 111,
        text: str | None = None,
        caption: str | None = None,
        photo: bool = False,
        successful_payment: SuccessfulPayment | None = None,
    ) -> Message:
        self.message_id += 1
        message = Message(
            message_id=self.message_id,
            date=datetime.now(UTC),
            chat=Chat(id=chat_id, type="private"),
            from_user=User(id=user_id, is_bot=False, first_name=f"U{user_id}"),
            text=text,
            caption=caption,
            photo=(
                [
                    PhotoSize(
                        file_id=f"file-{self.message_id}",
                        file_unique_id=f"uniq-{self.message_id}",
                        width=1280,
                        height=720,
                    )
                ]
                if photo
                else None
            ),
            successful_payment=successful_payment,
        )
        return message.as_(self.bot)

    def _capture(self, kind: str, kwargs: dict[str, Any]) -> None:
        self.captured.append((kind, dict(kwargs)))

    def handle_method(self, method) -> Any:
        name = type(method).__name__
        chat_id = int(getattr(method, "chat_id", 111) or 111)

        if name == "SendMessage":
            self._capture(
                "send_message",
                {
                    "chat_id": chat_id,
                    "text": method.text,
                    "reply_markup": method.reply_markup,
                },
            )
            return self._next_message(chat_id=chat_id, text=method.text)

        if name == "SendPhoto":
            self._capture(
                "send_photo",
                {
                    "chat_id": chat_id,
                    "caption": method.caption,
                    "photo": method.photo,
                },
            )
            return self._next_message(chat_id=chat_id, caption=method.caption, photo=True)

        if name == "SendInvoice":
            self._capture(
                "send_invoice",
                {
                    "chat_id": chat_id,
                    "currency": method.currency,
                    "prices": method.prices,
                    "payload": method.payload,
                    "provider_token": method.provider_token,
                    "description": method.description,
                    "title": method.title,
                },
            )
            return self._next_message(chat_id=chat_id, text="invoice")

        if name == "EditMessageText":
            self._capture(
                "edit_message_text",
                {
                    "chat_id": chat_id,
                    "message_id": method.message_id,
                    "text": method.text,
                    "reply_markup": method.reply_markup,
                },
            )
            return self._next_message(chat_id=chat_id, text=method.text)

        if name == "EditMessageMedia":
            self._capture(
                "edit_message_media",
                {
                    "chat_id": chat_id,
                    "message_id": method.message_id,
                    "media": method.media,
                    "reply_markup": method.reply_markup,
                },
            )
            return self._next_message(
                chat_id=chat_id,
                caption=getattr(method.media, "caption", None),
                photo=True,
            )

        if name == "EditMessageCaption":
            self._capture(
                "edit_message_caption",
                {
                    "chat_id": chat_id,
                    "message_id": method.message_id,
                    "caption": method.caption,
                    "reply_markup": method.reply_markup,
                },
            )
            return self._next_message(chat_id=chat_id, caption=method.caption, photo=True)

        if name == "DeleteMessage":
            self._capture("delete_message", {"chat_id": chat_id})
            return True

        if name == "AnswerCallbackQuery":
            self._capture(
                "answer_callback_query",
                {
                    "callback_query_id": method.callback_query_id,
                    "text": method.text,
                    "show_alert": method.show_alert,
                },
            )
            return True

        if name == "AnswerPreCheckoutQuery":
            self._capture(
                "answer_pre_checkout_query",
                {
                    "ok": method.ok,
                    "error_message": method.error_message,
                },
            )
            return True

        self._capture(name, {})
        return True

    def reset(self) -> None:
        self.captured.clear()

    def texts(self) -> list[str]:
        result: list[str] = []
        for _kind, kwargs in self.captured:
            value = (
                kwargs.get("text")
                or kwargs.get("caption")
                or getattr(kwargs.get("media"), "caption", None)
            )
            if value:
                result.append(str(value))
        return result

    def find(self, needle: str) -> str | None:
        for text in reversed(self.texts()):
            if needle in text:
                return text
        return None

    def last_kind(self) -> str | None:
        return self.captured[-1][0] if self.captured else None

    async def message(
        self,
        text: str | None = None,
        *,
        user_id: int = 111,
        chat_id: int | None = None,
        successful_payment: SuccessfulPayment | None = None,
    ) -> None:
        self.update_id += 1
        update = Update(
            update_id=self.update_id,
            message=self._next_message(
                chat_id=chat_id or user_id,
                user_id=user_id,
                text=text,
                successful_payment=successful_payment,
            ),
        )
        await self.dp.feed_update(self.bot, update)

    async def callback(
        self,
        data: str,
        *,
        user_id: int = 111,
        photo: bool = False,
        text: str = "interface",
    ) -> None:
        self.update_id += 1
        msg = self._next_message(
            chat_id=user_id,
            user_id=user_id,
            text=None if photo else text,
            caption=text if photo else None,
            photo=photo,
        )
        update = Update(
            update_id=self.update_id,
            callback_query=CallbackQuery(
                id=f"cb-{self.update_id}",
                from_user=User(id=user_id, is_bot=False, first_name=f"U{user_id}"),
                chat_instance="flow",
                message=msg,
                data=data,
            ),
        )
        await self.dp.feed_update(self.bot, update)


async def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        settings = Settings(
            bot_token="123456789:FLOW-TEST",
            admin_ids=frozenset({111}),
            payment_secret="flow-secret",
            price_stars=50,
            db_path=tmp_path / "flow.sqlite3",
            timezone="Europe/Moscow",
            log_level="WARNING",
            brand="NOEMA",
            support_contact="@support",
            assets_dir=ASSETS_DIR,
            env_path=tmp_path / ".env",
        )
        db = Database(settings.db_path)
        await db.init()
        assets = AssetManager(ASSETS_DIR, tmp_path / "file_ids.json")

        flow = Flow()
        flow.dp = Dispatcher(storage=MemoryStorage())
        flow.dp["settings"] = settings
        flow.dp["db"] = db
        flow.dp["assets"] = assets
        flow.dp.update.outer_middleware(PrivateChatMiddleware())
        flow.dp.update.outer_middleware(UserSyncMiddleware(db, settings))
        flow.dp.include_router(payment.router)
        flow.dp.include_router(admin.router)
        flow.dp.include_router(start.router)
        flow.dp.include_router(test.router)
        flow.dp.include_router(results.router)
        flow.dp.include_router(errors.router)

        print("\n[1] /start и старт теста")
        await flow.message("/start")
        check(flow.find("ДОБРО ПОЖАЛОВАТЬ В IQ TEST") is not None, "приветствие отправлено")
        check(flow.last_kind() == "send_photo", "приветствие - фото-карточка")

        await flow.callback("test:new", photo=True)
        check(flow.find("ВОПРОС 01 / 20") is not None, "первый вопрос показан")
        active = await db.get_active_test(111)
        check(active is not None and active.current_index == 0, "сессия создана в БД")

        print("\n[2] 20 ответов, прогресс и paywall")
        for question in QUESTIONS:
            data = f"ans:{active.id}:{question.index}:{question.correct_index}"
            await flow.callback(data, photo=bool(question.image))
            if question.index < 20:
                check(
                    flow.find(f"ВОПРОС {question.index + 1:02d} / 20") is not None,
                    f"после ответа {question.index} показан следующий вопрос",
                )
        completed = await db.get_test(active.id)
        check(completed is not None and completed.status == "completed", "тест завершён")
        check(completed.correct_count == 20, "все 20 ответов верны")
        check(completed.paid == 0, "до оплаты тест не оплачен")
        analysis = flow.find("АНАЛИТИЧЕСКИЙ ДВИЖОК")
        check(analysis is not None, "показан экран аналитики")
        locked = flow.find("ПЕРСОНАЛЬНЫЙ ОТЧЁТ ГОТОВ")
        check(locked is not None, "показан paywall")
        check("Правильных ответов" not in (locked or ""), "paywall не раскрывает результат")
        check("20 / 20" not in (locked or ""), "paywall не раскрывает счёт")

        print("\n[3] Счёт и успешная оплата")
        flow.reset()
        await flow.callback(f"pay:{active.id}", photo=True)
        invoice = next(
            (kwargs for kind, kwargs in flow.captured if kind == "send_invoice"), None
        )
        check(invoice is not None, "invoice отправлен")
        check(invoice["currency"] == "XTR", "валюта XTR")
        check(invoice["prices"][0].amount == 50, "цена 50 Stars")
        check(invoice["provider_token"] == "", "без внешнего provider_token")
        payload = invoice["payload"]
        check(settings.parse_payment_payload(payload) is not None, "payload подписан")

        def precheckout_query(user_id: int, amount: int):
            flow.update_id += 1
            return PreCheckoutQuery(
                id=f"pc-{flow.update_id}",
                from_user=User(id=user_id, is_bot=False, first_name=f"U{user_id}"),
                currency="XTR",
                total_amount=amount,
                invoice_payload=payload,
            ).as_(flow.bot)

        flow.reset()
        await payment.pre_checkout(precheckout_query(111, 50), db, settings)
        pc_ok = next(
            (kwargs for kind, kwargs in flow.captured if kind == "answer_pre_checkout_query"),
            None,
        )
        check(pc_ok is not None and pc_ok["ok"] is True, "pre_checkout подтверждён")

        flow.reset()
        await payment.pre_checkout(precheckout_query(111, 49), db, settings)
        pc_bad_amount = next(
            (kwargs for kind, kwargs in flow.captured if kind == "answer_pre_checkout_query"),
            None,
        )
        check(
            pc_bad_amount is not None and pc_bad_amount["ok"] is False,
            "pre_checkout отклоняет неверную сумму",
        )

        flow.reset()
        await payment.pre_checkout(precheckout_query(222, 50), db, settings)
        pc_other = next(
            (kwargs for kind, kwargs in flow.captured if kind == "answer_pre_checkout_query"),
            None,
        )
        check(
            pc_other is not None and pc_other["ok"] is False,
            "pre_checkout отклоняет чужой счёт",
        )

        payment_data = SuccessfulPayment(
            currency="XTR",
            total_amount=50,
            invoice_payload=payload,
            telegram_payment_charge_id="flow-charge-1",
            provider_payment_charge_id="flow-provider-1",
        )
        flow.reset()
        await flow.message(successful_payment=payment_data)
        paid = await db.get_test(active.id)
        check(paid is not None and paid.paid == 1, "successful_payment разблокировал тест")
        check(flow.find("ТВОЙ РЕЗУЛЬТАТ") is not None, "отчёт с результатом отправлен")
        check(flow.find("ПРАВИЛЬНЫХ ОТВЕТОВ") is not None, "в отчёте есть число ответов")
        check(flow.find("20 / 20") is not None, "в отчёте 20/20")
        check(flow.find("ПРОФИЛЬ ПО КАТЕГОРИЯМ") is not None, "отчёт содержит профиль")
        check(flow.find("ЧТО ДАЛЬШЕ") is not None, "финальный экран с кнопками отправлен")

        flow.reset()
        await payment.pre_checkout(precheckout_query(111, 50), db, settings)
        pc_paid = next(
            (kwargs for kind, kwargs in flow.captured if kind == "answer_pre_checkout_query"),
            None,
        )
        check(
            pc_paid is not None and pc_paid["ok"] is False,
            "pre_checkout отклоняет повторную оплату",
        )

        print("\n[4] Идемпотентность и чужие результаты")
        before = len(flow.captured)
        await flow.message(successful_payment=payment_data)
        check(len(flow.captured) == before, "повторный successful_payment не дублирует отчёт")
        check((await db.get_admin_stats()).revenue_stars == 50, "выручка не задвоилась")

        flow.reset()
        await flow.callback(f"resend:{active.id}", user_id=222)
        alert = next(
            (
                kwargs
                for kind, kwargs in flow.captured
                if kind == "answer_callback_query"
            ),
            None,
        )
        check(alert is not None and alert.get("show_alert") is True, "чужой callback отклонён")
        check(flow.find("ТВОЙ РЕЗУЛЬТАТ") is None, "чужой результат не отправлен")

        print("\n[5] Восстановление после перезапуска")
        flow.reset()
        await flow.message("/start")
        check(flow.find("Мои результаты") is None, "кнопки - в клавиатуре, не в тексте")
        await flow.callback(f"resend:{active.id}")
        check(flow.find("ТВОЙ РЕЗУЛЬТАТ") is not None, "оплаченный отчёт открыт повторно")
        check(flow.find("20 / 20") is not None, "повторный отчёт содержит результат")

        print("\n[6] Админ-панель и доступ")
        flow.reset()
        await flow.message("/admin", user_id=222)
        check(flow.find("ДОСТУП ЗАКРЫТ") is not None, "обычному пользователю /admin запрещён")

        flow.reset()
        await flow.message("/admin", user_id=111)
        check(flow.find("АДМИН-ПАНЕЛЬ") is not None, "админ видит панель")
        check(flow.find("50 ⭐") is not None, "админ видит выручку")

        flow.reset()
        await flow.callback("admin:results")
        check(flow.find("ПОСЛЕДНИЕ РЕЗУЛЬТАТЫ") is not None, "админ видит результаты")
        results_kb = next(
            (
                kwargs.get("reply_markup")
                for kind, kwargs in flow.captured
                if kind in {"edit_message_text", "send_message"}
            ),
            None,
        )
        check(results_kb is not None, "у результатов есть клавиатура")

        print("\n[7] Рассылка")
        flow.reset()
        await flow.callback("admin:broadcast")
        check(flow.find("РАССЫЛКА") is not None, "открыт сценарий рассылки")
        await flow.message("Тестовое сообщение для всех", user_id=111)
        check(flow.find("ПРЕДПРОСМОТР") is not None, "показан предпросмотр")
        flow.reset()
        await flow.callback("admin:broadcast:confirm")
        check(flow.find("РАССЫЛКА ЗАВЕРШЕНА") is not None, "рассылка завершена")
        delivered = [
            kwargs
            for kind, kwargs in flow.captured
            if kind == "send_message" and kwargs.get("text") == "Тестовое сообщение для всех"
        ]
        check(len(delivered) == 2, "сообщение доставлено двум пользователям")
        check(
            await db.get_admin_stats() is not None,
            "статистика доступна после рассылки",
        )

        print(f"\nFLOW OK: {CHECK} проверок")
        await flow.bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except AssertionError as exc:
        print(f"\n{exc}")
        raise SystemExit(1) from None
