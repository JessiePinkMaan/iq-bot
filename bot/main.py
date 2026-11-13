"""Сборка и запуск приложения."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat

from .config import LOGS_DIR, ConfigError, Settings, load_settings
from .database import Database
from .handlers import admin, errors, payment, results, start, test
from .middlewares import PrivateChatMiddleware, UserSyncMiddleware
from .questions import validate_questions
from .services import AssetManager

logger = logging.getLogger(__name__)

USER_COMMANDS = [
    BotCommand(command="start", description="Главное меню"),
    BotCommand(command="test", description="Начать или продолжить тест"),
    BotCommand(command="result", description="Мои отчёты"),
    BotCommand(command="about", description="О проекте"),
    BotCommand(command="help", description="Помощь"),
]

ADMIN_COMMANDS = [
    BotCommand(command="admin", description="Админ-панель"),
]

DESCRIPTION = (
    "NOEMA - авторский интеллектуальный тест.\n\n"
    "20 заданий на логику, закономерности и абстрактное мышление. "
    "Персональный аналитический отчёт с разбором решений."
)
SHORT_DESCRIPTION = "Авторский IQ-тест · 20 заданий · персональный отчёт"


def configure_logging(level: str) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    numeric = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    file = RotatingFileHandler(
        LOGS_DIR / "bot.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file.setFormatter(formatter)
    logging.basicConfig(level=numeric, handlers=[console, file], force=True)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def _configure_bot_profile(bot: Bot, settings: Settings) -> None:
    try:
        await bot.set_my_commands(USER_COMMANDS)
    except Exception:
        logger.exception("Не удалось установить команды бота")
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                USER_COMMANDS + ADMIN_COMMANDS,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:  # noqa: BLE001
            logger.warning("Не удалось установить админ-команды для %s", admin_id)
    try:
        await bot.set_my_description(DESCRIPTION)
        await bot.set_my_short_description(SHORT_DESCRIPTION)
    except Exception:  # noqa: BLE001
        logger.warning("Не удалось обновить описание бота")


def _check_assets(settings: Settings) -> None:
    required = (
        "hero.jpg",
        "analysis.jpg",
        "locked.jpg",
        "unlocked.jpg",
        "report.jpg",
        "q09.jpg",
    )
    missing = [name for name in required if not (settings.assets_dir / name).exists()]
    if missing:
        raise ConfigError(
            "Не найдены изображения: "
            + ", ".join(missing)
            + ". Запусти: python assets/generate_assets.py"
        )


async def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001,S110
        pass

    settings = load_settings()
    configure_logging(settings.log_level)
    validate_questions()
    _check_assets(settings)

    db = Database(settings.db_path)
    await db.init()
    assets = AssetManager(settings.assets_dir, settings.db_path.parent / "file_ids.json")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher["settings"] = settings
    dispatcher["db"] = db
    dispatcher["assets"] = assets

    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError as exc:
        await bot.session.close()
        raise ConfigError(
            "Telegram отклонил BOT_TOKEN. Проверь токен в .env "
            "(он мог быть отозван в @BotFather)."
        ) from exc
    logger.info("Подключение установлено: @%s", me.username)

    private_only = PrivateChatMiddleware()
    middleware = UserSyncMiddleware(db, settings)
    dispatcher.update.outer_middleware(private_only)
    dispatcher.update.outer_middleware(middleware)

    # Порядок важен: платёжные события обрабатываются раньше остальных.
    dispatcher.include_router(payment.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(start.router)
    dispatcher.include_router(test.router)
    dispatcher.include_router(results.router)
    dispatcher.include_router(errors.router)

    await _configure_bot_profile(bot, settings)
    await bot.delete_webhook(drop_pending_updates=False)

    logger.info("NOEMA запущен. База: %s", settings.db_path)
    logger.info("Администраторы: %s", ", ".join(map(str, sorted(settings.admin_ids))))
    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()
        logger.info("NOEMA остановлен")


if __name__ == "__main__":
    try:
        import asyncio

        asyncio.run(main())
    except (ConfigError, KeyboardInterrupt) as exc:
        if isinstance(exc, ConfigError):
            print(f"Ошибка конфигурации: {exc}")
        raise SystemExit(1) from None
