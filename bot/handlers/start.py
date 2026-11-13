"""Главное меню, приветствие и информационные экраны."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..database import Database
from ..services import AssetManager
from ..texts import DIVIDER
from ..ui import safe_delete, send_about, send_welcome

router = Router(name="start")


def _admin(is_admin: bool | None) -> bool:
    return bool(is_admin)


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
    is_admin: bool = False,
) -> None:
    await send_welcome(
        bot,
        message.chat.id,
        db=db,
        settings=settings,
        assets=assets,
        user_id=db_user.id,
        is_admin=_admin(is_admin),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "◆ <b>КОМАНДЫ</b>\n"
        f"{DIVIDER}\n\n"
        "/start - главное меню\n"
        "/test - начать или продолжить тест\n"
        "/result - мои отчёты\n"
        "/about - о проекте\n"
        "/help - эта подсказка\n\n"
        "<blockquote>Прогресс теста сохраняется автоматически. "
        "Начать второй тест параллельно нельзя.</blockquote>",
        parse_mode="HTML",
    )


@router.message(Command("about"))
async def cmd_about(message: Message, is_admin: bool = False) -> None:
    await send_about(message.bot, message.chat.id, is_admin=_admin(is_admin))


@router.message(Command("admin"))
async def cmd_admin_denied(message: Message) -> None:
    await message.answer(
        "⛔ <b>ДОСТУП ЗАКРЫТ</b>\n\n"
        "Административная панель доступна только владельцу бота.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "menu:home")
async def cb_home(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
    is_admin: bool = False,
) -> None:
    await callback.answer()
    await safe_delete(callback.message)
    await send_welcome(
        bot,
        callback.from_user.id,
        db=db,
        settings=settings,
        assets=assets,
        user_id=db_user.id,
        is_admin=_admin(is_admin),
    )


@router.callback_query(F.data == "about")
async def cb_about(
    callback: CallbackQuery,
    bot: Bot,
    is_admin: bool = False,
) -> None:
    await callback.answer()
    await safe_delete(callback.message)
    await send_about(bot, callback.from_user.id, is_admin=_admin(is_admin))


@router.callback_query(F.data.startswith("admin:"))
async def cb_admin_denied(callback: CallbackQuery) -> None:
    await callback.answer(
        "Административная панель доступна только владельцу бота.",
        show_alert=True,
    )
