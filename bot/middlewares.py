"""Middleware: регистрация пользователя и инъекция контекста."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User

from .config import Settings
from .database import Database

logger = logging.getLogger(__name__)


class PrivateChatMiddleware(BaseMiddleware):
    """Бот работает только в личных чатах: не светим отчёты в группах."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = data.get("event_chat")
        chat_type = getattr(chat, "type", None)
        if chat_type is not None and chat_type != "private":
            message: Message | None = None
            callback: CallbackQuery | None = None
            if isinstance(event, Update):
                message = event.message
                callback = event.callback_query
                if callback is not None and callback.message is not None:
                    message = callback.message
            if callback is not None:
                await callback.answer(
                    "Тест и отчёт доступны только в личном чате с ботом.",
                    show_alert=True,
                )
            elif message is not None:
                await message.answer(
                    "◆ <b>NOEMA · ЛИЧНЫЙ ФОРМАТ</b>\n\n"
                    "Тест и персональный отчёт доступны только в личном чате с ботом.\n\n"
                    "<blockquote>Открой бота в private-чате и отправь /start.</blockquote>",
                    parse_mode="HTML",
                )
            return None
        return await handler(event, data)


class UserSyncMiddleware(BaseMiddleware):
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        if user is not None and not user.is_bot:
            try:
                record = await self.db.upsert_user(
                    user_id=user.id,
                    username=user.username,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    language_code=user.language_code,
                )
                data["db_user"] = record
                data["is_admin"] = user.id in self.settings.admin_ids
            except Exception:
                logger.exception("Не удалось синхронизировать пользователя %s", user.id)
                data["is_admin"] = user.id in self.settings.admin_ids
        else:
            data.setdefault("is_admin", False)
        return await handler(event, data)
