"""Управление изображениями и кэшем Telegram file_id."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    FSInputFile,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

logger = logging.getLogger(__name__)


class AssetManager:
    def __init__(self, assets_dir: Path, cache_path: Path) -> None:
        self.assets_dir = Path(assets_dir)
        self.cache_path = Path(cache_path)
        self._cache: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._stamp = self._assets_stamp()
        self._load()

    def _assets_stamp(self) -> str:
        digest = hashlib.sha1()
        try:
            for path in sorted(self.assets_dir.glob("*.jpg")):
                stat = path.stat()
                digest.update(path.name.encode())
                digest.update(str(stat.st_size).encode())
                digest.update(str(stat.st_mtime_ns).encode())
        except OSError:
            return "unknown"
        return digest.hexdigest()[:16]

    def _load(self) -> None:
        try:
            if self.cache_path.exists():
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    if data.pop("__stamp__", None) != self._stamp:
                        logger.info("Ассеты изменились - сбрасываю кэш file_id")
                        self._cache = {}
                    else:
                        self._cache = {str(k): str(v) for k, v in data.items()}
        except (OSError, json.JSONDecodeError):
            logger.warning("Не удалось прочитать кэш file_id, начинаю заново")
            self._cache = {}

    def _save(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            payload = dict(self._cache)
            payload["__stamp__"] = self._stamp
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.cache_path)
        except OSError:
            logger.exception("Не удалось сохранить кэш file_id")

    def path(self, name: str) -> Path:
        return self.assets_dir / name

    async def _remember(self, name: str, message: Message) -> None:
        if not message.photo:
            return
        file_id = message.photo[-1].file_id
        if self._cache.get(name) == file_id:
            return
        async with self._lock:
            self._cache[name] = file_id
            self._save()

    def _media(self, name: str) -> str | FSInputFile:
        cached = self._cache.get(name)
        if cached:
            return cached
        return FSInputFile(self.path(name), filename=name)

    async def send_photo(
        self,
        message: Message,
        name: str,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message:
        cached = self._cache.get(name)
        if cached:
            try:
                sent = await message.answer_photo(
                    photo=cached,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
                return sent
            except TelegramBadRequest as exc:
                logger.warning("Устаревший file_id для %s: %s", name, exc.message)
                async with self._lock:
                    self._cache.pop(name, None)
                    self._save()
        sent = await message.answer_photo(
            photo=FSInputFile(self.path(name), filename=name),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        await self._remember(name, sent)
        return sent

    async def send_photo_to(
        self,
        bot: Bot,
        chat_id: int,
        name: str,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message:
        cached = self._cache.get(name)
        if cached:
            try:
                return await bot.send_photo(
                    chat_id=chat_id,
                    photo=cached,
                    caption=caption,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                )
            except TelegramBadRequest as exc:
                logger.warning("Устаревший file_id для %s: %s", name, exc.message)
                async with self._lock:
                    self._cache.pop(name, None)
                    self._save()
        sent = await bot.send_photo(
            chat_id=chat_id,
            photo=FSInputFile(self.path(name), filename=name),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        await self._remember(name, sent)
        return sent

    def _input_media(self, name: str, caption: str) -> InputMediaPhoto:
        return InputMediaPhoto(
            media=self._media(name),
            caption=caption,
            parse_mode="HTML",
        )

    async def edit_photo(
        self,
        message: Message,
        name: str,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message | bool:
        """Меняет фото и подпись. Если файл или сообщение не подходят - fallback."""
        try:
            result = await message.edit_media(
                media=self._input_media(name, caption),
                reply_markup=reply_markup,
            )
            if isinstance(result, Message):
                await self._remember(name, result)
            return result
        except TelegramBadRequest as exc:
            logger.warning("edit_media не удался для %s: %s", name, exc.message)
            async with self._lock:
                had_cache = self._cache.pop(name, None) is not None
                if had_cache:
                    self._save()
            if had_cache:
                try:
                    result = await message.edit_media(
                        media=self._input_media(name, caption),
                        reply_markup=reply_markup,
                    )
                    if isinstance(result, Message):
                        await self._remember(name, result)
                    return result
                except TelegramBadRequest:
                    pass
            try:
                await message.delete()
            except TelegramBadRequest:
                pass
            return await self.send_photo(
                message, name, caption, reply_markup=reply_markup
            )

    async def edit_caption(
        self,
        message: Message,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> Message | bool:
        try:
            return await message.edit_caption(
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        except TelegramBadRequest as exc:
            logger.warning("edit_caption не удался: %s", exc.message)
            return False
