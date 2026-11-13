"""Асинхронный слой данных на SQLite (aiosqlite).

Схема рассчитана на идемпотентность: один активный тест на пользователя,
один ответ на вопрос и один платёж на charge_id.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from .questions import TOTAL_QUESTIONS, get_question


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,
    username        TEXT,
    first_name      TEXT NOT NULL DEFAULT '',
    last_name       TEXT,
    language_code   TEXT,
    registered_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL,
    tests_completed INTEGER NOT NULL DEFAULT 0,
    total_paid_stars INTEGER NOT NULL DEFAULT 0,
    is_blocked      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'in_progress'
                    CHECK (status IN ('in_progress', 'completed', 'abandoned')),
    current_index   INTEGER NOT NULL DEFAULT 0,
    correct_count   INTEGER NOT NULL DEFAULT 0,
    score_percent   REAL,
    started_at      TEXT NOT NULL,
    completed_at    TEXT,
    abandoned_at    TEXT,
    paid            INTEGER NOT NULL DEFAULT 0,
    paid_at         TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_tests_one_active
    ON tests(user_id) WHERE status = 'in_progress';
CREATE INDEX IF NOT EXISTS ix_tests_user ON tests(user_id);
CREATE INDEX IF NOT EXISTS ix_tests_status ON tests(status);
CREATE INDEX IF NOT EXISTS ix_tests_paid ON tests(paid);

CREATE TABLE IF NOT EXISTS answers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id         INTEGER NOT NULL REFERENCES tests(id) ON DELETE CASCADE,
    question_index  INTEGER NOT NULL,
    option_index    INTEGER NOT NULL,
    is_correct      INTEGER NOT NULL,
    answered_at     TEXT NOT NULL,
    UNIQUE (test_id, question_index)
);

CREATE INDEX IF NOT EXISTS ix_answers_test ON answers(test_id);

CREATE TABLE IF NOT EXISTS payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(id),
    test_id             INTEGER REFERENCES tests(id),
    charge_id           TEXT UNIQUE,
    provider_charge_id  TEXT,
    amount              INTEGER NOT NULL,
    currency            TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'paid'
                        CHECK (status IN ('paid', 'duplicate', 'unmatched')),
    payload             TEXT,
    created_at          TEXT NOT NULL,
    delivered_at        TEXT
);

CREATE INDEX IF NOT EXISTS ix_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS ix_payments_test ON payments(test_id);
CREATE INDEX IF NOT EXISTS ix_payments_status ON payments(status);
"""


@dataclass(frozen=True, slots=True)
class UserRecord:
    id: int
    username: str | None
    first_name: str
    last_name: str | None
    language_code: str | None
    registered_at: str
    last_seen_at: str
    tests_completed: int
    total_paid_stars: int
    is_blocked: int

    @property
    def display_name(self) -> str:
        name = " ".join(x for x in (self.first_name, self.last_name) if x).strip()
        return name or (f"@{self.username}" if self.username else str(self.id))

    @property
    def mention(self) -> str:
        return f'<a href="tg://user?id={self.id}">{self.display_name}</a>'


@dataclass(frozen=True, slots=True)
class TestRecord:
    id: int
    user_id: int
    status: str
    current_index: int
    correct_count: int
    score_percent: float | None
    started_at: str
    completed_at: str | None
    abandoned_at: str | None
    paid: int
    paid_at: str | None

    @property
    def answered(self) -> int:
        return min(self.current_index, TOTAL_QUESTIONS)

    @property
    def is_complete(self) -> bool:
        return self.status == "completed"

    @property
    def accuracy(self) -> int:
        if self.score_percent is not None:
            return round(self.score_percent)
        return round(self.correct_count / TOTAL_QUESTIONS * 100)


@dataclass(frozen=True, slots=True)
class AnswerRecord:
    id: int
    test_id: int
    question_index: int
    option_index: int
    is_correct: int
    answered_at: str


@dataclass(frozen=True, slots=True)
class PaymentRecord:
    id: int
    user_id: int
    test_id: int | None
    charge_id: str | None
    provider_charge_id: str | None
    amount: int
    currency: str
    status: str
    payload: str | None
    created_at: str
    delivered_at: str | None


@dataclass(frozen=True, slots=True)
class AnswerOutcome:
    status: str  # ok | completed | duplicate | stale | not_active | not_found | invalid
    test: TestRecord | None
    question_index: int


@dataclass(frozen=True, slots=True)
class PaymentOutcome:
    status: str  # ok | already_paid | duplicate_charge | unmatched | wrong_owner
    test: TestRecord | None
    payment_id: int | None = None


@dataclass(frozen=True, slots=True)
class AdminStats:
    users_total: int
    users_today: int
    tests_started: int
    tests_completed: int
    tests_paid: int
    revenue_stars: int
    avg_score: float | None
    active_tests: int


def _user_from_row(row: sqlite3.Row) -> UserRecord:
    return UserRecord(**dict(row))


def _test_from_row(row: sqlite3.Row) -> TestRecord:
    return TestRecord(**dict(row))


def _answer_from_row(row: sqlite3.Row) -> AnswerRecord:
    return AnswerRecord(**dict(row))


def _payment_from_row(row: sqlite3.Row) -> PaymentRecord:
    return PaymentRecord(**dict(row))


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(self.path, isolation_level=None)
        db.row_factory = aiosqlite.Row
        try:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA busy_timeout = 5000")
            yield db
        finally:
            await db.close()

    async def init(self) -> None:
        async with self.connect() as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.executescript(SCHEMA)
            await db.execute("PRAGMA synchronous = NORMAL")

    # ------------------------------------------------------------------ users
    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
        language_code: str | None,
    ) -> UserRecord:
        now = utc_now()
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                await db.execute(
                    """
                    INSERT INTO users (id, username, first_name, last_name, language_code,
                                       registered_at, last_seen_at, is_blocked)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(id) DO UPDATE SET
                        username = excluded.username,
                        first_name = excluded.first_name,
                        last_name = excluded.last_name,
                        language_code = excluded.language_code,
                        last_seen_at = excluded.last_seen_at,
                        is_blocked = 0
                    """,
                    (user_id, username, first_name or "", last_name, language_code, now, now),
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
        assert row is not None
        return _user_from_row(row)

    async def mark_blocked(self, user_id: int, blocked: bool) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE users SET is_blocked = ? WHERE id = ?", (1 if blocked else 0, user_id)
            )

    async def get_user(self, user_id: int) -> UserRecord | None:
        async with self.connect() as db:
            cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            await cursor.close()
        return _user_from_row(row) if row else None

    async def all_user_ids(self, include_blocked: bool = False) -> list[int]:
        query = "SELECT id FROM users"
        if not include_blocked:
            query += " WHERE is_blocked = 0"
        query += " ORDER BY id"
        async with self.connect() as db:
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            await cursor.close()
        return [int(row["id"]) for row in rows]

    # ------------------------------------------------------------------ tests
    async def get_active_test(self, user_id: int) -> TestRecord | None:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM tests WHERE user_id = ? AND status = 'in_progress' "
                "ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return _test_from_row(row) if row else None

    async def get_test(self, test_id: int) -> TestRecord | None:
        async with self.connect() as db:
            cursor = await db.execute("SELECT * FROM tests WHERE id = ?", (test_id,))
            row = await cursor.fetchone()
            await cursor.close()
        return _test_from_row(row) if row else None

    async def create_test(self, user_id: int) -> tuple[TestRecord, bool]:
        """Возвращает (тест, создан_ли_новый). Активный тест не дублируется."""
        now = utc_now()
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cursor = await db.execute(
                    "SELECT * FROM tests WHERE user_id = ? AND status = 'in_progress' "
                    "ORDER BY id DESC LIMIT 1",
                    (user_id,),
                )
                existing = await cursor.fetchone()
                await cursor.close()
                if existing:
                    await db.commit()
                    return _test_from_row(existing), False
                cursor = await db.execute(
                    "INSERT INTO tests (user_id, status, started_at) VALUES (?, 'in_progress', ?)",
                    (user_id, now),
                )
                test_id = int(cursor.lastrowid or 0)
                await cursor.close()
                await db.commit()
            except sqlite3.IntegrityError:
                await db.rollback()
                existing = await self.get_active_test(user_id)
                if existing:
                    return existing, False
                raise
            except Exception:
                await db.rollback()
                raise
            created = await self.get_test(test_id)
        assert created is not None
        return created, True

    async def abandon_active_test(self, user_id: int) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE tests SET status = 'abandoned', abandoned_at = ?
                WHERE user_id = ? AND status = 'in_progress'
                """,
                (utc_now(), user_id),
            )
            changed = cursor.rowcount
            await cursor.close()
        return bool(changed)

    async def record_answer(
        self,
        user_id: int,
        test_id: int,
        question_index: int,
        option_index: int,
    ) -> AnswerOutcome:
        if not 1 <= question_index <= TOTAL_QUESTIONS:
            return AnswerOutcome("invalid", None, question_index)
        if not 0 <= option_index <= 3:
            return AnswerOutcome("invalid", None, question_index)
        question = get_question(question_index)
        is_correct = 1 if option_index == question.correct_index else 0
        now = utc_now()

        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cursor = await db.execute(
                    "SELECT * FROM tests WHERE id = ? AND user_id = ?", (test_id, user_id)
                )
                row = await cursor.fetchone()
                await cursor.close()
                if row is None:
                    await db.rollback()
                    return AnswerOutcome("not_found", None, question_index)
                test = _test_from_row(row)
                if test.status != "in_progress":
                    await db.rollback()
                    return AnswerOutcome("not_active", test, question_index)
                if test.current_index >= TOTAL_QUESTIONS:
                    await db.rollback()
                    return AnswerOutcome("stale", test, question_index)
                expected = test.current_index + 1
                if question_index != expected:
                    await db.rollback()
                    return AnswerOutcome("stale", test, question_index)

                try:
                    await db.execute(
                        """
                        INSERT INTO answers (test_id, question_index, option_index, is_correct, answered_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (test_id, question_index, option_index, is_correct, now),
                    )
                except sqlite3.IntegrityError:
                    await db.rollback()
                    current = await self.get_test(test_id)
                    return AnswerOutcome("duplicate", current, question_index)

                new_index = test.current_index + 1
                new_correct = test.correct_count + is_correct
                if new_index >= TOTAL_QUESTIONS:
                    percent = round(new_correct / TOTAL_QUESTIONS * 100, 1)
                    await db.execute(
                        """
                        UPDATE tests SET status = 'completed', current_index = ?,
                            correct_count = ?, score_percent = ?, completed_at = ?
                        WHERE id = ?
                        """,
                        (new_index, new_correct, percent, now, test_id),
                    )
                    await db.execute(
                        "UPDATE users SET tests_completed = tests_completed + 1 WHERE id = ?",
                        (user_id,),
                    )
                    outcome = "completed"
                else:
                    await db.execute(
                        "UPDATE tests SET current_index = ?, correct_count = ? WHERE id = ?",
                        (new_index, new_correct, test_id),
                    )
                    outcome = "ok"
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            updated = await self.get_test(test_id)
        return AnswerOutcome(outcome, updated, question_index)

    async def get_answers(self, test_id: int) -> list[AnswerRecord]:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM answers WHERE test_id = ? ORDER BY question_index", (test_id,)
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [_answer_from_row(row) for row in rows]

    async def get_user_results(self, user_id: int, limit: int = 20) -> list[TestRecord]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT * FROM tests
                WHERE user_id = ? AND status = 'completed'
                ORDER BY completed_at DESC, id DESC LIMIT ?
                """,
                (user_id, limit),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [_test_from_row(row) for row in rows]

    async def get_latest_completed_unpaid(self, user_id: int) -> TestRecord | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT * FROM tests
                WHERE user_id = ? AND status = 'completed' AND paid = 0
                ORDER BY completed_at DESC, id DESC LIMIT 1
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return _test_from_row(row) if row else None

    async def get_latest_completed_paid(self, user_id: int) -> TestRecord | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT * FROM tests
                WHERE user_id = ? AND status = 'completed' AND paid = 1
                ORDER BY completed_at DESC, id DESC LIMIT 1
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return _test_from_row(row) if row else None

    # --------------------------------------------------------------- payments
    async def mark_paid(
        self,
        user_id: int,
        test_id: int,
        charge_id: str,
        provider_charge_id: str | None,
        amount: int,
        currency: str,
        payload: str,
    ) -> PaymentOutcome:
        now = utc_now()
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                cursor = await db.execute(
                    "SELECT * FROM payments WHERE charge_id = ?", (charge_id,)
                )
                existing_payment_row = await cursor.fetchone()
                await cursor.close()
                if existing_payment_row:
                    existing_payment = _payment_from_row(existing_payment_row)
                    await db.rollback()
                    test = (
                        await self.get_test(existing_payment.test_id)
                        if existing_payment.test_id
                        else None
                    )
                    return PaymentOutcome("duplicate_charge", test, existing_payment.id)

                cursor = await db.execute("SELECT * FROM tests WHERE id = ?", (test_id,))
                test_row = await cursor.fetchone()
                await cursor.close()
                if test_row is None:
                    cursor = await db.execute(
                        """
                        INSERT INTO payments (user_id, test_id, charge_id, provider_charge_id,
                            amount, currency, status, payload, created_at)
                        VALUES (?, NULL, ?, ?, ?, ?, 'unmatched', ?, ?)
                        """,
                        (user_id, charge_id, provider_charge_id, amount, currency, payload, now),
                    )
                    payment_id = int(cursor.lastrowid or 0)
                    await cursor.close()
                    await db.commit()
                    return PaymentOutcome("unmatched", None, payment_id)

                test = _test_from_row(test_row)
                if test.user_id != user_id:
                    cursor = await db.execute(
                        """
                        INSERT INTO payments (user_id, test_id, charge_id, provider_charge_id,
                            amount, currency, status, payload, created_at)
                        VALUES (?, NULL, ?, ?, ?, ?, 'unmatched', ?, ?)
                        """,
                        (user_id, charge_id, provider_charge_id, amount, currency, payload, now),
                    )
                    payment_id = int(cursor.lastrowid or 0)
                    await cursor.close()
                    await db.commit()
                    return PaymentOutcome("wrong_owner", test, payment_id)

                if test.status != "completed":
                    cursor = await db.execute(
                        """
                        INSERT INTO payments (user_id, test_id, charge_id, provider_charge_id,
                            amount, currency, status, payload, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'unmatched', ?, ?)
                        """,
                        (user_id, test_id, charge_id, provider_charge_id, amount, currency, payload, now),
                    )
                    payment_id = int(cursor.lastrowid or 0)
                    await cursor.close()
                    await db.commit()
                    return PaymentOutcome("unmatched", test, payment_id)

                if test.paid:
                    cursor = await db.execute(
                        """
                        INSERT INTO payments (user_id, test_id, charge_id, provider_charge_id,
                            amount, currency, status, payload, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'duplicate', ?, ?)
                        """,
                        (user_id, test_id, charge_id, provider_charge_id, amount, currency, payload, now),
                    )
                    payment_id = int(cursor.lastrowid or 0)
                    await cursor.close()
                    await db.commit()
                    return PaymentOutcome("already_paid", test, payment_id)

                await db.execute(
                    "UPDATE tests SET paid = 1, paid_at = ? WHERE id = ? AND paid = 0",
                    (now, test_id),
                )
                await db.execute(
                    """
                    INSERT INTO payments (user_id, test_id, charge_id, provider_charge_id,
                        amount, currency, status, payload, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'paid', ?, ?)
                    """,
                    (user_id, test_id, charge_id, provider_charge_id, amount, currency, payload, now),
                )
                cursor = await db.execute("SELECT last_insert_rowid() AS id")
                row = await cursor.fetchone()
                await cursor.close()
                payment_id = int(row["id"]) if row else 0
                await db.execute(
                    "UPDATE users SET total_paid_stars = total_paid_stars + ? WHERE id = ?",
                    (amount, user_id),
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
            updated = await self.get_test(test_id)
        return PaymentOutcome("ok", updated, payment_id)

    async def mark_payment_delivered(self, payment_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE payments SET delivered_at = ? WHERE id = ? AND delivered_at IS NULL",
                (utc_now(), payment_id),
            )

    async def get_payment_by_charge(self, charge_id: str) -> PaymentRecord | None:
        async with self.connect() as db:
            cursor = await db.execute("SELECT * FROM payments WHERE charge_id = ?", (charge_id,))
            row = await cursor.fetchone()
            await cursor.close()
        return _payment_from_row(row) if row else None

    async def get_payment_for_test(self, test_id: int) -> PaymentRecord | None:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM payments WHERE test_id = ? AND status = 'paid' "
                "ORDER BY id DESC LIMIT 1",
                (test_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return _payment_from_row(row) if row else None

    # ----------------------------------------------------------------- admin
    async def get_admin_stats(self) -> AdminStats:
        today_prefix = datetime.now(UTC).date().isoformat()
        async with self.connect() as db:
            async def scalar(query: str, params: Iterable = ()) -> int:
                cursor = await db.execute(query, tuple(params))
                row = await cursor.fetchone()
                await cursor.close()
                return int(row[0]) if row and row[0] is not None else 0

            users_total = await scalar("SELECT COUNT(*) FROM users")
            users_today = await scalar(
                "SELECT COUNT(*) FROM users WHERE registered_at LIKE ?", (f"{today_prefix}%",)
            )
            tests_started = await scalar("SELECT COUNT(*) FROM tests")
            tests_completed = await scalar(
                "SELECT COUNT(*) FROM tests WHERE status = 'completed'"
            )
            tests_paid = await scalar(
                "SELECT COUNT(*) FROM tests WHERE status = 'completed' AND paid = 1"
            )
            active_tests = await scalar(
                "SELECT COUNT(*) FROM tests WHERE status = 'in_progress'"
            )
            revenue = await scalar(
                "SELECT COALESCE(SUM(amount), 0) FROM payments "
                "WHERE status = 'paid' AND currency = 'XTR'"
            )
            cursor = await db.execute(
                "SELECT AVG(score_percent) FROM tests WHERE status = 'completed'"
            )
            row = await cursor.fetchone()
            await cursor.close()
            avg_score = float(row[0]) if row and row[0] is not None else None
        return AdminStats(
            users_total=users_total,
            users_today=users_today,
            tests_started=tests_started,
            tests_completed=tests_completed,
            tests_paid=tests_paid,
            revenue_stars=revenue,
            avg_score=avg_score,
            active_tests=active_tests,
        )

    async def recent_users(self, limit: int = 10) -> list[UserRecord]:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM users ORDER BY last_seen_at DESC, id DESC LIMIT ?", (limit,)
            )
            rows = await cursor.fetchall()
            await cursor.close()
        return [_user_from_row(row) for row in rows]

    async def recent_results(self, limit: int = 10) -> list[tuple[TestRecord, UserRecord]]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT t.*, u.username AS u_username, u.first_name AS u_first_name,
                       u.last_name AS u_last_name, u.language_code AS u_language_code,
                       u.registered_at AS u_registered_at, u.last_seen_at AS u_last_seen_at,
                       u.tests_completed AS u_tests_completed,
                       u.total_paid_stars AS u_total_paid_stars, u.is_blocked AS u_is_blocked
                FROM tests t JOIN users u ON u.id = t.user_id
                WHERE t.status = 'completed'
                ORDER BY t.completed_at DESC, t.id DESC LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            await cursor.close()
        result: list[tuple[TestRecord, UserRecord]] = []
        for row in rows:
            data = dict(row)
            user = UserRecord(
                id=int(data["user_id"]),
                username=data["u_username"],
                first_name=data["u_first_name"],
                last_name=data["u_last_name"],
                language_code=data["u_language_code"],
                registered_at=data["u_registered_at"],
                last_seen_at=data["u_last_seen_at"],
                tests_completed=int(data["u_tests_completed"]),
                total_paid_stars=int(data["u_total_paid_stars"]),
                is_blocked=int(data["u_is_blocked"]),
            )
            test_data = {
                key: data[key]
                for key in (
                    "id", "user_id", "status", "current_index", "correct_count",
                    "score_percent", "started_at", "completed_at", "abandoned_at",
                    "paid", "paid_at",
                )
            }
            test_data["paid"] = int(test_data["paid"])
            result.append((_test_from_row(test_data), user))
        return result

    async def count_paid_results(self) -> int:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM tests WHERE status = 'completed' AND paid = 1"
            )
            row = await cursor.fetchone()
            await cursor.close()
        return int(row[0]) if row else 0
