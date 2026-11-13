"""Общие UI-операции: главный экран, вопросы, paywall-экран."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from .config import Settings
from .database import Database, TestRecord
from .keyboards import (
    about_keyboard,
    locked_report_for,
    main_menu,
    pause_keyboard,
    question_keyboard,
    results_list,
)
from .questions import Question
from .services import AssetManager
from .texts import (
    about_text,
    locked_caption,
    question_text,
    results_list_text,
    welcome_caption,
)

logger = logging.getLogger(__name__)


async def safe_delete(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def send_welcome(
    bot: Bot,
    chat_id: int,
    *,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    user_id: int,
    is_admin: bool = False,
) -> Message:
    active = await db.get_active_test(user_id)
    unpaid = await db.get_latest_completed_unpaid(user_id)
    results = await db.get_user_results(user_id, limit=20)
    keyboard = main_menu(
        active_index=active.current_index if active else None,
        unmet_paid_test_id=unpaid.id if unpaid else None,
        has_results=bool(results),
        is_admin=is_admin,
    )
    caption = welcome_caption(active, unpaid is not None)
    return await assets.send_photo_to(bot, chat_id, "hero.jpg", caption, keyboard)


async def send_about(bot: Bot, chat_id: int, is_admin: bool = False) -> Message:
    return await bot.send_message(
        chat_id,
        about_text(),
        parse_mode="HTML",
        reply_markup=about_keyboard(),
        disable_web_page_preview=True,
    )


async def send_results(
    bot: Bot,
    chat_id: int,
    *,
    db: Database,
    settings: Settings,
    user_id: int,
) -> Message:
    results = await db.get_user_results(user_id, limit=20)
    return await bot.send_message(
        chat_id,
        results_list_text(results, settings.timezone),
        parse_mode="HTML",
        reply_markup=results_list(results, settings.price_stars),
        disable_web_page_preview=True,
    )


async def send_question(
    bot: Bot,
    chat_id: int,
    *,
    test: TestRecord,
    question: Question,
    assets: AssetManager,
    edit_message: Message | None = None,
) -> Message:
    text = question_text(question, test.current_index)
    keyboard = question_keyboard(question, test.id)

    if question.image:
        if edit_message and edit_message.photo:
            try:
                result = await assets.edit_photo(
                    edit_message, question.image, text, keyboard
                )
                if isinstance(result, Message):
                    return result
                if result is True:
                    return edit_message
            except TelegramBadRequest:
                logger.exception("Не удалось обновить изображение вопроса")
        elif edit_message:
            await safe_delete(edit_message)
        return await assets.send_photo_to(
            bot, chat_id, question.image, text, keyboard
        )

    if edit_message and not edit_message.photo:
        try:
            return await edit_message.edit_text(
                text, parse_mode="HTML", reply_markup=keyboard
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in exc.message.lower():
                logger.warning("edit_text вопроса не удался: %s", exc.message)
                await safe_delete(edit_message)
            else:
                return edit_message
    elif edit_message and edit_message.photo:
        await safe_delete(edit_message)

    return await bot.send_message(
        chat_id, text, parse_mode="HTML", reply_markup=keyboard
    )


async def send_locked(
    bot: Bot,
    chat_id: int,
    *,
    test: TestRecord,
    settings: Settings,
    assets: AssetManager,
    edit_message: Message | None = None,
) -> Message:
    caption = locked_caption(settings.price_stars)
    keyboard = locked_report_for(test.id, settings.price_stars)
    if edit_message is None:
        return await assets.send_photo_to(bot, chat_id, "locked.jpg", caption, keyboard)
    if edit_message.photo:
        try:
            result = await assets.edit_photo(edit_message, "locked.jpg", caption, keyboard)
            if isinstance(result, Message):
                return result
            if result is True:
                return edit_message
        except TelegramBadRequest:
            logger.exception("Не удалось показать paywall")
    else:
        await safe_delete(edit_message)
        return await assets.send_photo_to(bot, chat_id, "locked.jpg", caption, keyboard)
    return await assets.send_photo_to(bot, chat_id, "locked.jpg", caption, keyboard)


async def send_pause(bot: Bot, chat_id: int, test: TestRecord) -> Message:
    return await bot.send_message(
        chat_id,
        "<b>СЕССИЯ ПРИОСТАНОВЛЕНА</b>\n"
        "━━━━━━━━━━━━\n\n"
        f"Ты ответил на <b>{test.current_index}</b> из <b>20</b> вопросов.\n\n"
        "Ответы сохранены. Продолжить можно с того же места, "
        "с любого устройства.\n\n"
        "<blockquote>Кнопка ниже или команда /start.</blockquote>",
        parse_mode="HTML",
        reply_markup=pause_keyboard(),
    )
