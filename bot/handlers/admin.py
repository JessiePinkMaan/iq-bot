"""Админ-панель: статистика, пользователи, результаты, рассылка."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..config import Settings
from ..database import Database
from ..keyboards import (
    admin_back,
    admin_keyboard,
    admin_results_keyboard,
    broadcast_cancel,
    broadcast_confirm,
)
from ..texts import DIVIDER, admin_home, admin_results, admin_test_detail, admin_users
from ..ui import safe_delete

logger = logging.getLogger(__name__)
router = Router(name="admin")


class AdminFilter(BaseFilter):
    async def __call__(self, event, is_admin: bool = False) -> bool:
        return bool(is_admin)


class Broadcast(StatesGroup):
    waiting_text = State()
    confirm = State()


router.message.filter(AdminFilter())
router.callback_query.filter(AdminFilter())


async def _render(
    callback: CallbackQuery,
    bot: Bot,
    text: str,
    keyboard,
) -> None:
    message = callback.message
    if message is not None and not message.photo:
        try:
            await message.edit_text(
                text, parse_mode="HTML", reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            return
        except TelegramBadRequest as exc:
            if "message is not modified" in exc.message.lower():
                return
            logger.warning("Не удалось обновить админ-сообщение: %s", exc.message)
    await safe_delete(message)
    await bot.send_message(
        callback.from_user.id,
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    stats = await db.get_admin_stats()
    await message.answer(
        admin_home(stats),
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "admin:home")
async def cb_admin_home(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
) -> None:
    await callback.answer()
    stats = await db.get_admin_stats()
    await _render(callback, bot, admin_home(stats), admin_keyboard())


@router.callback_query(F.data == "admin:users")
async def cb_admin_users(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    await callback.answer()
    users = await db.recent_users(limit=10)
    await _render(
        callback,
        bot,
        admin_users(users, settings.timezone),
        admin_keyboard(),
    )


@router.callback_query(F.data == "admin:results")
async def cb_admin_results(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    await callback.answer()
    results = await db.recent_results(limit=10)
    await _render(
        callback,
        bot,
        admin_results(results, settings.timezone),
        admin_results_keyboard(results),
    )


@router.callback_query(F.data.startswith("admin:test:"))
async def cb_admin_test(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
) -> None:
    try:
        test_id = int((callback.data or "").split(":")[-1])
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return
    test = await db.get_test(test_id)
    if test is None:
        await callback.answer("Тест не найден", show_alert=True)
        return
    user = await db.get_user(test.user_id)
    if user is None:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    answers = await db.get_answers(test.id)
    await callback.answer()
    await _render(
        callback,
        bot,
        admin_test_detail(test, user, answers, settings.timezone),
        admin_back(),
    )


@router.callback_query(F.data == "admin:broadcast")
async def cb_admin_broadcast(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    db: Database,
) -> None:
    await callback.answer()
    await state.clear()
    await state.set_state(Broadcast.waiting_text)
    await safe_delete(callback.message)
    total = len(await db.all_user_ids(include_blocked=False))
    await bot.send_message(
        callback.from_user.id,
        "📣 <b>РАССЫЛКА</b>\n"
        f"{DIVIDER}\n\n"
        f"Получателей сейчас: <b>{total}</b>.\n\n"
        "Отправь текст сообщения. Поддерживается HTML-разметка Telegram "
        "(<code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, ссылки). "
        "Максимум 3900 символов.\n\n"
        "<blockquote>Перед отправкой появится предпросмотр с подтверждением.</blockquote>",
        parse_mode="HTML",
        reply_markup=broadcast_cancel(),
    )


@router.message(StateFilter(Broadcast.waiting_text))
async def broadcast_text(
    message: Message,
    bot: Bot,
    state: FSMContext,
) -> None:
    if not message.text:
        await message.answer("Отправь именно текст сообщения.")
        return
    if message.text.startswith("/"):
        await message.answer(
            "Сейчас активен режим рассылки. Отправь текст сообщения "
            "или нажми «Отмена».",
            reply_markup=broadcast_cancel(),
        )
        return
    text = message.html_text
    if len(text) > 3900:
        await message.answer(
            f"Слишком длинный текст: {len(text)} символов. "
            "Сократи до 3900 и отправь снова.",
            reply_markup=broadcast_cancel(),
        )
        return
    await state.update_data(broadcast_text=text)
    await state.set_state(Broadcast.confirm)
    await message.answer(
        "👁 <b>ПРЕДПРОСМОТР</b>\n"
        f"{DIVIDER}\n\n"
        f"{text}\n\n"
        f"{DIVIDER}\n"
        "<b>Отправить это сообщение всем?</b>",
        parse_mode="HTML",
        reply_markup=broadcast_confirm(),
        disable_web_page_preview=True,
    )


@router.callback_query(F.data == "admin:broadcast:cancel")
async def cb_broadcast_cancel(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    db: Database,
) -> None:
    await state.clear()
    await callback.answer("Отменено")
    stats = await db.get_admin_stats()
    await _render(callback, bot, admin_home(stats), admin_keyboard())


@router.callback_query(F.data == "admin:broadcast:confirm")
async def cb_broadcast_confirm(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    db: Database,
) -> None:
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.answer("Текст не найден, начни заново", show_alert=True)
        await state.clear()
        return
    await callback.answer("Рассылка запущена")
    await state.clear()
    await safe_delete(callback.message)

    recipients = await db.all_user_ids(include_blocked=False)
    status = await bot.send_message(
        callback.from_user.id,
        f"📣 <b>РАССЫЛКА</b>\n{DIVIDER}\n\n"
        f"Отправляю: <b>0 / {len(recipients)}</b>",
        parse_mode="HTML",
    )

    sent = 0
    blocked = 0
    failed = 0
    for index, user_id in enumerate(recipients, start=1):
        try:
            await bot.send_message(
                user_id,
                text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
            await db.mark_blocked(user_id, True)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 0.5)
            try:
                await bot.send_message(
                    user_id,
                    text,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
                sent += 1
            except Exception:  # noqa: BLE001
                failed += 1
        except TelegramBadRequest as exc:
            failed += 1
            logger.warning("Рассылка: BadRequest для %s: %s", user_id, exc.message)
        except Exception:
            failed += 1
            logger.exception("Рассылка: ошибка для %s", user_id)

        if index % 25 == 0 or index == len(recipients):
            try:
                await status.edit_text(
                    f"📣 <b>РАССЫЛКА</b>\n{DIVIDER}\n\n"
                    f"Отправляю: <b>{index} / {len(recipients)}</b>\n"
                    f"Доставлено: {sent} · заблокировали: {blocked} · ошибок: {failed}",
                    parse_mode="HTML",
                )
            except TelegramBadRequest:
                pass
        await asyncio.sleep(0.045)

    await bot.send_message(
        callback.from_user.id,
        "✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n"
        f"{DIVIDER}\n\n"
        f"Получателей: <b>{len(recipients)}</b>\n"
        f"Доставлено: <b>{sent}</b>\n"
        f"Заблокировали бота: <b>{blocked}</b>\n"
        f"Ошибок: <b>{failed}</b>",
        parse_mode="HTML",
        reply_markup=admin_keyboard(),
    )
    logger.info(
        "Рассылка завершена: recipients=%s sent=%s blocked=%s failed=%s",
        len(recipients),
        sent,
        blocked,
        failed,
    )
