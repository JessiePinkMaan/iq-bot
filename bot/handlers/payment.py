"""Telegram Stars: invoice, pre-checkout, successful_payment, разблокировка."""

from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
)

from ..config import Settings
from ..database import Database, TestRecord
from ..keyboards import open_paid_result, payment_problem
from ..report import send_full_report
from ..services import AssetManager
from ..texts import duplicate_payment_notice, payment_problem_notice
from ..ui import safe_delete

logger = logging.getLogger(__name__)
router = Router(name="payments")


async def _notify_admins(bot: Bot, settings: Settings, text: str) -> None:
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(
                admin_id, text, parse_mode="HTML", disable_web_page_preview=True
            )
        except TelegramBadRequest as exc:
            logger.warning("Не удалось уведомить админа %s: %s", admin_id, exc.message)
        except Exception:
            logger.exception("Не удалось уведомить админа %s", admin_id)


def _payment_details(payment: SuccessfulPayment) -> str:
    charge = html.escape(payment.telegram_payment_charge_id or "-")
    provider = html.escape(payment.provider_payment_charge_id or "-")
    payload = html.escape(payment.invoice_payload or "-")
    return (
        f"charge_id: <code>{charge}</code>\n"
        f"provider_charge_id: <code>{provider}</code>\n"
        f"payload: <code>{payload}</code>"
    )


def _user_label(user_id: int, username: str | None, full_name: str | None) -> str:
    safe_name = html.escape(full_name or username or str(user_id))
    handle = f" @{html.escape(username)}" if username else ""
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>{handle} (<code>{user_id}</code>)'


async def _load_owned_completed(
    db: Database, settings: Settings, payload: str, user_id: int
) -> tuple[TestRecord | None, int | None, str]:
    parsed = settings.parse_payment_payload(payload)
    if parsed is None:
        return None, None, "Некорректный payload счёта"
    test_id, payload_user_id, amount = parsed
    if payload_user_id != user_id:
        return None, None, "Счёт оформлен для другого пользователя"
    test = await db.get_test(test_id)
    if test is None or test.user_id != user_id:
        return None, None, "Счёт не привязан к твоему тесту"
    if test.status != "completed":
        return test, amount, "Тест ещё не завершён"
    return test, amount, ""


@router.callback_query(F.data.startswith("pay:"))
async def cb_pay(
    callback: CallbackQuery,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
    db_user,
) -> None:
    try:
        test_id = int((callback.data or "").split(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Некорректная кнопка", show_alert=True)
        return
    test = await db.get_test(test_id)
    if test is None or test.user_id != db_user.id:
        await callback.answer("Отчёт не найден", show_alert=True)
        return
    if test.status != "completed":
        await callback.answer("Тест ещё не завершён", show_alert=True)
        return
    if test.paid:
        await callback.answer("Отчёт уже оплачен")
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

    await callback.answer()
    payload = settings.make_payment_payload(test.id, db_user.id)
    try:
        await bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"{settings.brand} · персональный отчёт",
            description=(
                "Полный отчёт по 20 заданиям: результат, профиль по 7 категориям, "
                "сильные стороны и разбор решений. Доступ навсегда."
            ),
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=f"{settings.brand} · полный отчёт",
                    amount=settings.price_stars,
                )
            ],
        )
    except TelegramBadRequest:
        logger.exception("Не удалось выставить счёт test_id=%s", test.id)
        await bot.send_message(
            callback.from_user.id,
            "⚠️ <b>НЕ УДАЛОСЬ ВЫСТАВИТЬ СЧЁТ</b>\n\n"
            "Попробуй ещё раз через минуту. Если ошибка повторится, "
            "напиши в поддержку.",
            parse_mode="HTML",
            reply_markup=payment_problem(),
        )


@router.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery,
    db: Database,
    settings: Settings,
) -> None:
    user_id = query.from_user.id
    if query.currency != "XTR":
        await query.answer(
            ok=False, error_message="Оплата возможна только в Telegram Stars."
        )
        return

    test, expected_amount, error = await _load_owned_completed(
        db, settings, query.invoice_payload, user_id
    )
    if test is None or error or expected_amount is None:
        logger.warning(
            "pre_checkout отклонён user=%s payload=%s reason=%s",
            user_id,
            query.invoice_payload,
            error,
        )
        await query.answer(
            ok=False,
            error_message="Счёт устарел или не относится к твоему тесту. Открой отчёт заново.",
        )
        return
    if query.total_amount != expected_amount:
        logger.warning(
            "pre_checkout: неверная сумма user=%s expected=%s got=%s",
            user_id,
            expected_amount,
            query.total_amount,
        )
        await query.answer(
            ok=False,
            error_message="Неверная сумма счёта. Открой отчёт заново.",
        )
        return
    if test.paid:
        await query.answer(
            ok=False,
            error_message="Этот отчёт уже оплачен. Повторная оплата не требуется.",
        )
        return

    await query.answer(ok=True)
    logger.info(
        "pre_checkout подтверждён user=%s test=%s amount=%s",
        user_id,
        test.id,
        expected_amount,
    )


@router.message(F.successful_payment)
async def successful_payment(
    message: Message,
    bot: Bot,
    db: Database,
    settings: Settings,
    assets: AssetManager,
) -> None:
    payment = message.successful_payment
    user = message.from_user
    if payment is None or user is None:
        return

    parsed = settings.parse_payment_payload(payment.invoice_payload)
    if parsed is None:
        logger.error("Некорректный payload успешного платежа user=%s", user.id)
        await _notify_admins(
            bot,
            settings,
            "🚨 <b>ПЛАТЁЖ С НЕКОРРЕКТНЫМ PAYLOAD</b>\n\n"
            f"Пользователь: {_user_label(user.id, user.username, user.full_name)}\n"
            f"Сумма: {payment.total_amount} {html.escape(payment.currency)}\n"
            f"{_payment_details(payment)}",
        )
        await bot.send_message(
            user.id,
            payment_problem_notice(settings.support_contact),
            parse_mode="HTML",
            reply_markup=payment_problem(),
        )
        return

    test_id, payload_user_id, invoice_amount = parsed
    if payload_user_id != user.id:
        logger.critical(
            "Платёж с чужим payload: test=%s payload_user=%s sender=%s",
            test_id,
            payload_user_id,
            user.id,
        )
        await _notify_admins(
            bot,
            settings,
            "🚨 <b>ПЛАТЁЖ НА ЧУЖОЙ PAYLOAD</b>\n\n"
            f"Отправитель: {_user_label(user.id, user.username, user.full_name)}\n"
            f"Payload user_id: <code>{payload_user_id}</code>\n"
            f"{_payment_details(payment)}",
        )
        await bot.send_message(
            user.id,
            payment_problem_notice(settings.support_contact),
            parse_mode="HTML",
            reply_markup=payment_problem(),
        )
        return

    if payment.currency != "XTR" or payment.total_amount != invoice_amount:
        logger.error(
            "Неверные параметры successful_payment user=%s amount=%s %s expected=%s",
            user.id,
            payment.total_amount,
            payment.currency,
            invoice_amount,
        )
        await _notify_admins(
            bot,
            settings,
            "🚨 <b>ПЛАТЁЖ С НЕВЕРНЫМИ ПАРАМЕТРАМИ</b>\n\n"
            f"Пользователь: {_user_label(user.id, user.username, user.full_name)}\n"
            f"Ожидалось: {invoice_amount} XTR\n"
            f"Получено: {payment.total_amount} {html.escape(payment.currency)}\n"
            f"{_payment_details(payment)}",
        )
        await bot.send_message(
            user.id,
            payment_problem_notice(settings.support_contact),
            parse_mode="HTML",
            reply_markup=payment_problem(),
        )
        return

    charge_id = (
        payment.telegram_payment_charge_id
        or f"missing:{message.message_id}:{user.id}"
    )

    outcome = await db.mark_paid(
        user_id=user.id,
        test_id=test_id,
        charge_id=charge_id,
        provider_charge_id=payment.provider_payment_charge_id,
        amount=payment.total_amount,
        currency=payment.currency,
        payload=payment.invoice_payload,
    )

    if outcome.status == "duplicate_charge":
        existing = await db.get_payment_by_charge(charge_id)
        if existing and existing.delivered_at is None and existing.test_id:
            test = await db.get_test(existing.test_id)
            if test and test.paid and test.user_id == user.id:
                answers = await db.get_answers(test.id)
                await send_full_report(
                    bot,
                    user.id,
                    test=test,
                    answers=answers,
                    settings=settings,
                    assets=assets,
                    photo_asset="unlocked.jpg",
                )
                await db.mark_payment_delivered(existing.id)
                return
        logger.info("Повторная доставка платежа charge=%s проигнорирована", charge_id)
        return

    if outcome.status == "already_paid":
        logger.warning(
            "Повторная оплата уже оплаченного теста user=%s test=%s charge=%s",
            user.id,
            test_id,
            charge_id,
        )
        if outcome.test is not None:
            await bot.send_message(
                user.id,
                duplicate_payment_notice(payment.total_amount),
                parse_mode="HTML",
                reply_markup=open_paid_result(outcome.test.id),
            )
        await _notify_admins(
            bot,
            settings,
            "💸 <b>ПОВТОРНАЯ ОПЛАТА</b>\n\n"
            f"Пользователь: {_user_label(user.id, user.username, user.full_name)}\n"
            f"Тест: <code>{test_id}</code>\n"
            f"Сумма: {payment.total_amount} ⭐\n"
            f"{_payment_details(payment)}\n\n"
            "Отчёт уже был оплачен. Нужен возврат дублирующего платежа.",
        )
        if outcome.payment_id:
            await db.mark_payment_delivered(outcome.payment_id)
        return

    if outcome.status in {"unmatched", "wrong_owner"}:
        logger.critical(
            "Платёж не привязан status=%s user=%s test=%s",
            outcome.status,
            user.id,
            test_id,
        )
        await bot.send_message(
            user.id,
            payment_problem_notice(settings.support_contact),
            parse_mode="HTML",
            reply_markup=payment_problem(),
        )
        await _notify_admins(
            bot,
            settings,
            "🚨 <b>ПЛАТЁЖ НЕ ПРИВЯЗАН</b>\n\n"
            f"Статус: <code>{outcome.status}</code>\n"
            f"Пользователь: {_user_label(user.id, user.username, user.full_name)}\n"
            f"Тест: <code>{test_id}</code>\n"
            f"Сумма: {payment.total_amount} ⭐\n"
            f"{_payment_details(payment)}",
        )
        return

    test = outcome.test
    if test is None:
        logger.error("Оплата прошла, но тест %s не найден", test_id)
        return

    answers = await db.get_answers(test.id)
    await send_full_report(
        bot,
        user.id,
        test=test,
        answers=answers,
        settings=settings,
        assets=assets,
        photo_asset="unlocked.jpg",
    )
    if outcome.payment_id:
        await db.mark_payment_delivered(outcome.payment_id)
    logger.info(
        "Отчёт разблокирован: user=%s test=%s charge=%s",
        user.id,
        test.id,
        charge_id,
    )
