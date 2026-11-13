"""Точка входа: python run.py"""

from __future__ import annotations

import asyncio
import sys

from bot.config import BASE_DIR, ConfigError
from bot.locking import SingleInstance
from bot.main import main


def _run() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001,S110
        pass

    lock = SingleInstance(BASE_DIR / "data" / "bot.lock")
    if not lock.acquire():
        print("\nБот уже запущен в другом процессе.")
        print("Закрой предыдущее окно или останови старый процесс, затем запусти снова.\n")
        raise SystemExit(1)

    try:
        asyncio.run(main())
    except ConfigError as exc:
        print("\n" + "=" * 64)
        print("ОШИБКА КОНФИГУРАЦИИ")
        print("=" * 64)
        print(exc)
        print("\nПроверь файл .env в корне проекта.")
        print("=" * 64 + "\n")
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")
    finally:
        lock.release()


if __name__ == "__main__":
    _run()
