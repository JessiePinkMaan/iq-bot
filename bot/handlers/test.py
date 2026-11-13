"""Прохождение теста: старт, ответы, прогресс, завершение."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..database import AnswerOutcome, Database, TestRecord
from ..keyboards import reset_confirm
from ..questions import TOTAL_QUESTIONS, get_question
from ..report import send_full_report
from ..services import AssetManager
from ..texts import analysis_caption
from ..ui import (
    safe_delete,
    send_locked,
    send_pause,
    send_question,
    send_welcome,
)

logger = logging.getLogger(__name__)
router = Router(name="test")


def _parse_answer(data: str) -> tuple[int, int, int] | None:
    parts = data.split(":")
    if len(parts) != 4 or parts[0] != "ans":
        return None
    try:
        return int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return None


async def _show_current(
    callback: CallbackQuery,
    *,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    user_id: int,
    is_admin: bool = False,
) -> None:
    test = await db.get_active_test(user_id)
    if test is None:
        await safe_delete(callback.message)
        await send_welcome(
            bot,
            user_id,
            db=db,
            settings=settings,
            assets=assets,
            user_id=user_id,
            is_admin=is_admin,
        )
        return
    await safe_delete(callback.message)
    question = get_question(min(test.current_index + 1, TOTAL_QUESTIONS))
    await send_question(
        bot,
        user_id,
        test=test,
        question=question,
        assets=assets,
    )


@router.message(Command("test"))
async def cmd_test(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
) -> None:
    test = await db.get_active_test(db_user.id)
    if test is None:
        test, _created = await db.create_test(db_user.id)
    question = get_question(min(test.current_index + 1, TOTAL_QUESTIONS))
    await send_question(
        bot,
        message.chat.id,
        test=test,
        question=question,
        assets=assets,
    )


@router.callback_query(F.data == "test:new")
async def cb_test_new(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
    is_admin: bool = False,
) -> None:
    active = await db.get_active_test(db_user.id)
    if active is not None:
        await callback.answer("Продолжаем сохранённую сессию")
        await _show_current(
            callback,
            bot=bot,
            db=db,
            settings=settings,
            assets=assets,
            user_id=db_user.id,
            is_admin=is_admin,
        )
        return

    test, created = await db.create_test(db_user.id)
    await callback.answer("Тест начат" if created else "Продолжаем сессию")
    await safe_delete(callback.message)
    question = get_question(min(test.current_index + 1, TOTAL_QUESTIONS))
    await send_question(
        bot,
        callback.from_user.id,
        test=test,
        question=question,
        assets=assets,
    )


@router.callback_query(F.data == "test:continue")
async def cb_test_continue(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
    is_admin: bool = False,
) -> None:
    await callback.answer()
    await _show_current(
        callback,
        bot=bot,
        db=db,
        settings=settings,
        assets=assets,
        user_id=db_user.id,
        is_admin=is_admin,
    )


@router.callback_query(F.data == "test:pause")
async def cb_test_pause(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    db_user,
) -> None:
    test = await db.get_active_test(db_user.id)
    if test is None:
        await callback.answer("Активной сессии нет", show_alert=True)
        return
    await callback.answer("Прогресс сохранён")
    await safe_delete(callback.message)
    await send_pause(bot, callback.from_user.id, test)


@router.callback_query(F.data == "test:reset")
async def cb_test_reset(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    db_user,
) -> None:
    test = await db.get_active_test(db_user.id)
    if test is None:
        await callback.answer("Активной сессии нет", show_alert=True)
        return
    await callback.answer()
    await safe_delete(callback.message)
    await bot.send_message(
        callback.from_user.id,
        "⚠️ <b>НАЧАТЬ ЗАНОВО?</b>\n"
        "━━━━━━━━━━━━\n\n"
        f"Ты ответил на <b>{test.current_index} из 20</b> вопросов.\n\n"
        "Если начать заново, этот прогресс будет удалён без возможности "
        "восстановления.\n\n"
        "<blockquote>Завершённые и оплаченные отчёты останутся доступны.</blockquote>",
        parse_mode="HTML",
        reply_markup=reset_confirm(test.id),
    )


@router.callback_query(F.data.startswith("test:reset:yes:"))
async def cb_test_reset_yes(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
) -> None:
    try:
        test_id = int(callback.data.rsplit(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer("Некорректная кнопка", show_alert=True)
        return
    active = await db.get_active_test(db_user.id)
    if active is None or active.id != test_id:
        await callback.answer("Эта сессия уже изменилась", show_alert=True)
        return
    await callback.answer("Сессия сброшена")
    await db.abandon_active_test(db_user.id)
    test, _ = await db.create_test(db_user.id)
    await safe_delete(callback.message)
    await send_question(
        bot,
        callback.from_user.id,
        test=test,
        question=get_question(1),
        assets=assets,
    )


async def _complete_flow(
    callback: CallbackQuery,
    *,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    test: TestRecord,
) -> None:
    await safe_delete(callback.message)

    if test.paid:
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

    message = await assets.send_photo_to(
        bot,
        callback.from_user.id,
        "analysis.jpg",
        analysis_caption(0),
    )
    for step in range(1, 4):
        await asyncio.sleep(0.9 if step < 3 else 0.8)
        await assets.edit_caption(message, analysis_caption(step))
    await asyncio.sleep(0.55)
    await send_locked(
        bot,
        callback.from_user.id,
        test=test,
        settings=settings,
        assets=assets,
        edit_message=message,
    )


@router.callback_query(F.data.startswith("ans:"))
async def cb_answer(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
    is_admin: bool = False,
) -> None:
    parsed = _parse_answer(callback.data or "")
    if parsed is None:
        await callback.answer("Некорректный ответ", show_alert=True)
        return
    test_id, question_index, option_index = parsed

    outcome: AnswerOutcome = await db.record_answer(
        db_user.id, test_id, question_index, option_index
    )

    if outcome.status == "ok" and outcome.test is not None:
        await callback.answer("Ответ принят")
        next_question = get_question(
            min(outcome.test.current_index + 1, TOTAL_QUESTIONS)
        )
        await send_question(
            bot,
            callback.from_user.id,
            test=outcome.test,
            question=next_question,
            assets=assets,
            edit_message=callback.message,
        )
        return

    if outcome.status == "completed" and outcome.test is not None:
        await callback.answer("Тест завершён")
        await _complete_flow(
            callback,
            bot=bot,
            db=db,
            settings=settings,
            assets=assets,
            test=outcome.test,
        )
        return

    if outcome.status in {"duplicate", "stale"}:
        await callback.answer("Этот ответ уже принят", show_alert=True)
        return

    if outcome.status == "not_active":
        await callback.answer("Эта сессия уже завершена", show_alert=True)
        return

    if outcome.status == "not_found":
        await callback.answer(
            "Сессия не найдена. Начни тест заново через /start.",
            show_alert=True,
        )
        return

    await callback.answer("Не удалось записать ответ", show_alert=True)
