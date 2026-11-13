"""Единая система inline-клавиатур."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .questions import Question


def _markup(rows: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _button(text: str, callback_data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data)


def main_menu(
    *,
    active_index: int | None = None,
    unmet_paid_test_id: int | None = None,
    has_results: bool = False,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if active_index is None:
        rows.append([_button("🧠  Начать тестирование", "test:new")])
    else:
        rows.append([_button(f"▶️  Продолжить · {active_index + 1} / 20", "test:continue")])
        rows.append([_button("🔄  Начать заново", "test:reset")])
    if unmet_paid_test_id is not None:
        rows.append([_button("🔒  Открыть готовый отчёт", f"locked:{unmet_paid_test_id}")])
    if has_results:
        rows.append([_button("📊  Мои результаты", "results:list")])
    rows.append([_button("◆  О проекте", "about")])
    if is_admin:
        rows.append([_button("⚙️  Админ-панель", "admin:home")])
    return _markup(rows)


def question_keyboard(question: Question, test_id: int) -> InlineKeyboardMarkup:
    prefix = f"ans:{test_id}:{question.index}"
    options = [
        _button(f"{letter}  ·  {text}", f"{prefix}:{index}")
        for index, (letter, text) in enumerate(zip("ABCD", question.options))
    ]
    if max(len(option) for option in question.options) <= 15:
        rows = [options[0:2], options[2:4]]
    else:
        rows = [[option] for option in options]
    rows.append([_button("⏸  Сохранить и выйти", "test:pause")])
    return _markup(rows)


def reset_confirm(test_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("Да, начать заново", f"test:reset:yes:{test_id}")],
            [_button("←  Оставить прогресс", "test:continue")],
        ]
    )


def locked_report_for(test_id: int, price: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button(f"🔓  Открыть результат · {price} ⭐", f"pay:{test_id}")],
            [_button("◆  Что входит в отчёт", f"details:{test_id}")],
            [_button("📊  Мои результаты", "results:list")],
            [_button("🏠  В меню", "menu:home")],
        ]
    )


def details_keyboard(test_id: int, price: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button(f"🔓  Открыть отчёт · {price} ⭐", f"pay:{test_id}")],
            [_button("←  Назад к отчёту", f"locked:{test_id}")],
        ]
    )


def about_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("🧠  Начать тестирование", "test:new")],
            [_button("🏠  В меню", "menu:home")],
        ]
    )


def results_list(results: list, price: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for test in results[:8]:
        if test.paid:
            rows.append(
                [
                    _button(
                        f"№{test.id:04d} · {test.correct_count}/20 · открыть",
                        f"resend:{test.id}",
                    )
                ]
            )
        else:
            rows.append(
                [_button(f"№{test.id:04d} · оплатить {price} ⭐", f"pay:{test.id}")]
            )
    rows.append([_button("🏠  В меню", "menu:home")])
    return _markup(rows)


def report_final() -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("🔄  Пройти тест заново", "test:new")],
            [_button("📊  Мои результаты", "results:list")],
            [_button("🏠  В меню", "menu:home")],
        ]
    )


def pause_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("▶️  Продолжить тест", "test:continue")],
            [_button("🏠  В меню", "menu:home")],
        ]
    )


def admin_keyboard() -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("🔄  Обновить", "admin:home"), _button("👥  Пользователи", "admin:users")],
            [_button("🧪  Результаты", "admin:results"), _button("📣  Рассылка", "admin:broadcast")],
            [_button("🏠  В меню", "menu:home")],
        ]
    )


def admin_results_keyboard(results: list) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    pair: list[InlineKeyboardButton] = []
    for test, _user in results[:10]:
        pair.append(
            _button(f"№{test.id:04d} · {test.correct_count}/20", f"admin:test:{test.id}")
        )
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([_button("←  В админ-панель", "admin:home")])
    return _markup(rows)


def admin_back() -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("🧪  К результатам", "admin:results")],
            [_button("←  В админ-панель", "admin:home")],
        ]
    )


def broadcast_confirm() -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("✅  Отправить всем", "admin:broadcast:confirm")],
            [_button("✕  Отмена", "admin:broadcast:cancel")],
        ]
    )


def broadcast_cancel() -> InlineKeyboardMarkup:
    return _markup([[_button("✕  Отмена", "admin:broadcast:cancel")]])


def payment_problem() -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("📊  Мои результаты", "results:list")],
            [_button("🏠  В меню", "menu:home")],
        ]
    )


def open_paid_result(test_id: int) -> InlineKeyboardMarkup:
    return _markup(
        [
            [_button("📖  Открыть оплаченный отчёт", f"resend:{test_id}")],
            [_button("📊  Мои результаты", "results:list")],
        ]
    )
