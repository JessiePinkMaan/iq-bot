"""Отправка полного оплаченного отчёта."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import Message

from .config import Settings
from .database import AnswerRecord, TestRecord
from .keyboards import report_final
from .scoring import analyze
from .services import AssetManager
from .texts import report_caption, report_error_chunks, report_profile, report_summary
from .texts import report_final as final_text

logger = logging.getLogger(__name__)


async def send_full_report(
    bot: Bot,
    chat_id: int,
    *,
    test: TestRecord,
    answers: list[AnswerRecord],
    settings: Settings,
    assets: AssetManager,
    photo_asset: str = "report.jpg",
) -> list[Message]:
    analysis = analyze(test, answers)
    sent: list[Message] = []

    sent.append(
        await assets.send_photo_to(
            bot,
            chat_id,
            photo_asset,
            report_caption(analysis),
        )
    )

    sent.append(
        await bot.send_message(
            chat_id,
            report_summary(analysis),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    )
    sent.append(
        await bot.send_message(
            chat_id,
            report_profile(analysis),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    )
    for chunk in report_error_chunks(analysis):
        sent.append(
            await bot.send_message(
                chat_id,
                chunk,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        )
    sent.append(
        await bot.send_message(
            chat_id,
            final_text(),
            parse_mode="HTML",
            reply_markup=report_final(),
            disable_web_page_preview=True,
        )
    )
    logger.info(
        "Отчёт test_id=%s отправлен пользователю %s (%s/%s)",
        test.id,
        chat_id,
        analysis.correct,
        analysis.total,
    )
    return sent
