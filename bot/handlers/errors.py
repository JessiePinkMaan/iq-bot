"""Глобальный обработчик ошибок."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.errors()
async def handle_error(event: ErrorEvent) -> bool:
    logger.error(
        "Необработанная ошибка при обработке апдейта",
        exc_info=event.exception,
    )
    update = event.update
    try:
        if update.callback_query is not None:
            await update.callback_query.answer(
                "Что-то пошло не так. Попробуй ещё раз через несколько секунд.",
                show_alert=True,
            )
        elif update.message is not None:
            await update.message.answer(
                "⚠️ <b>ВРЕМЕННАЯ ОШИБКА</b>\n\n"
                "Не удалось выполнить действие. Попробуй ещё раз через несколько секунд.",
                parse_mode="HTML",
            )
    except Exception:
        logger.exception("Не удалось сообщить пользователю об ошибке")
    return True
