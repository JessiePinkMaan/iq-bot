"""Конфигурация приложения. Все секреты - только из переменных окружения."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH, override=False)


class ConfigError(RuntimeError):
    pass


def _parse_admin_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            value = int(chunk)
        except ValueError as exc:
            raise ConfigError(f"ADMIN_IDS: «{chunk}» не является числом") from exc
        if value <= 0:
            raise ConfigError("ADMIN_IDS: Telegram ID должен быть положительным")
        ids.add(value)
    return frozenset(ids)


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    payment_secret: str
    price_stars: int
    db_path: Path
    timezone: str
    log_level: str
    brand: str
    support_contact: str
    assets_dir: Path
    env_path: Path

    @property
    def is_payment_secret_derived(self) -> bool:
        return not os.getenv("PAYMENT_SECRET", "").strip()

    def make_payment_payload(
        self, test_id: int, user_id: int, amount: int | None = None
    ) -> str:
        price = self.price_stars if amount is None else int(amount)
        raw = f"iq1:{test_id}:{user_id}:{price}"
        signature = hmac.new(
            self.payment_secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:20]
        return f"{raw}:{signature}"

    def parse_payment_payload(self, payload: str) -> tuple[int, int, int] | None:
        try:
            version, raw_test_id, raw_user_id, raw_amount, signature = payload.split(":")
            if version != "iq1":
                return None
            test_id = int(raw_test_id)
            user_id = int(raw_user_id)
            amount = int(raw_amount)
        except (ValueError, AttributeError):
            return None
        if amount < 1:
            return None
        raw = f"iq1:{test_id}:{user_id}:{amount}"
        expected = hmac.new(
            self.payment_secret.encode("utf-8"),
            raw.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:20]
        if not hmac.compare_digest(expected, signature):
            return None
        return test_id, user_id, amount


def load_settings(require_token: bool = True) -> Settings:
    raw_token = os.getenv("BOT_TOKEN", "").strip().strip('"').strip("'")
    if require_token and not raw_token:
        raise ConfigError(
            "BOT_TOKEN не задан. Открой файл .env и укажи токен из @BotFather."
        )
    if raw_token and ":" not in raw_token:
        raise ConfigError("BOT_TOKEN выглядит некорректно: ожидается формат 123456:ABC-DEF...")

    admin_raw = os.getenv("ADMIN_IDS", "").strip()
    admin_ids = _parse_admin_ids(admin_raw)
    if require_token and not admin_ids:
        raise ConfigError(
            "ADMIN_IDS не задан. Укажи свой Telegram ID в .env (например, ADMIN_IDS=123456789)."
        )

    raw_price = os.getenv("PRICE_STARS", "50").strip()
    try:
        price = int(raw_price)
    except ValueError as exc:
        raise ConfigError("PRICE_STARS должен быть целым числом") from exc
    if price < 1:
        raise ConfigError("PRICE_STARS должен быть больше нуля")

    payment_secret = os.getenv("PAYMENT_SECRET", "").strip()
    if not payment_secret:
        payment_secret = hashlib.sha256(f"noema-payload:{raw_token}".encode()).hexdigest()

    db_raw = os.getenv("DB_PATH", "data/noema.sqlite3").strip()
    db_path = Path(db_raw)
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path

    return Settings(
        bot_token=raw_token,
        admin_ids=admin_ids,
        payment_secret=payment_secret,
        price_stars=price,
        db_path=db_path,
        timezone=os.getenv("TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        brand=os.getenv("BRAND", "NOEMA").strip() or "NOEMA",
        support_contact=os.getenv("SUPPORT_CONTACT", "").strip(),
        assets_dir=ASSETS_DIR,
        env_path=ENV_PATH,
    )
