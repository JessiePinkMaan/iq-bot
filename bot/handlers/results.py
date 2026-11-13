"""Архив отчётов, повторное открытие оплаченных результатов."""

from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..database import Database, TestRecord
from ..keyboards import details_keyboard, open_paid_result
from ..report import send_full_report
from ..services import AssetManager
from ..texts import details_text
from ..ui import safe_delete, send_locked, send_results

logger = logging.getLogger(__name__)
router = Router(name="results")


async def _owned_test(db: Database, user_id: int, raw_id: str) -> TestRecord | None:
    try:
        test_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    test = await db.get_test(test_id)
    if test is None or test.user_id != user_id or test.status != "completed":
        return None
    return test


@router.message(Command("result"))
async def cmd_result(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
    db_user,
) -> None:
    await send_results(
        bot, message.chat.id, db=db, settings=settings, user_id=db_user.id
    )


@router.callback_query(F.data == "results:list")
async def cb_results(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    db_user,
) -> None:
    await callback.answer()
    await safe_delete(callback.message)
    await send_results(
        bot, callback.from_user.id, db=db, settings=settings, user_id=db_user.id
    )


@router.callback_query(F.data.startswith("locked:"))
async def cb_locked(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
) -> None:
    test = await _owned_test(db, db_user.id, (callback.data or "").split(":", 1)[-1])
    if test is None:
        await callback.answer("Отчёт не найден", show_alert=True)
        return
    await callback.answer()
    if test.paid:
        await safe_delete(callback.message)
        answers = await db.get_answers(test.id)
        await send_full_report(
            bot,
            callback.from_user.id,
            test=test,
            answers=answers,
            settings=settings,
            assets=assets,
            photo_asset="report.jpg",
        )
        return
    await send_locked(
        bot,
        callback.from_user.id,
        test=test,
        settings=settings,
        assets=assets,
        edit_message=callback.message,
    )


@router.callback_query(F.data.startswith("details:"))
async def cb_details(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    db_user,
) -> None:
    test = await _owned_test(db, db_user.id, (callback.data or "").split(":", 1)[-1])
    if test is None:
        await callback.answer("Отчёт не найден", show_alert=True)
        return
    await callback.answer()
    await safe_delete(callback.message)
    await bot.send_message(
        callback.from_user.id,
        details_text(settings.price_stars),
        parse_mode="HTML",
        reply_markup=(
            open_paid_result(test.id)
            if test.paid
            else details_keyboard(test.id, settings.price_stars)
        ),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data.startswith("resend:"))
async def cb_resend(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
) -> None:
    test = await _owned_test(db, db_user.id, (callback.data or "").split(":", 1)[-1])
    if test is None:
        await callback.answer("Отчёт не найден", show_alert=True)
        return
    if not test.paid:
        await callback.answer(
            "Отчёт ещё не оплачен. Открой его и заверши оплату.",
            show_alert=True,
        )
        return
    await callback.answer("Открываю отчёт")
    await safe_delete(callback.message)
    answers = await db.get_answers(test.id)
    await send_full_report(
        bot,
        callback.from_user.id,
        test=test,
        answers=answers,
        settings=settings,
        assets=assets,
        photo_asset="report.jpg",
    )
