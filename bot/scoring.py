"""Расчёт персонального аналитического профиля.

Важно: это не клиническая шкала IQ. Мы показываем объективное число
верных ответов и распределение по категориям авторского теста.
"""

from __future__ import annotations

from dataclasses import dataclass

from .database import AnswerRecord, TestRecord
from .questions import CATEGORIES, QUESTIONS, Question


@dataclass(frozen=True, slots=True)
class CategoryStat:
    key: str
    title: str
    correct: int
    total: int

    @property
    def percent(self) -> int:
        return round(self.correct / self.total * 100) if self.total else 0

    @property
    def bar(self) -> str:
        filled = round(self.percent / 10)
        return "▰" * filled + "▱" * (10 - filled)


@dataclass(frozen=True, slots=True)
class ProfileBand:
    title: str
    subtitle: str
    description: str


@dataclass(frozen=True, slots=True)
class Analysis:
    test: TestRecord
    correct: int
    total: int
    accuracy: int
    categories: tuple[CategoryStat, ...]
    strengths: tuple[CategoryStat, ...]
    growth: tuple[CategoryStat, ...]
    wrong: tuple[tuple[AnswerRecord, Question], ...]
    band: ProfileBand

    @property
    def score_bar(self) -> str:
        filled = round(self.accuracy / 5)
        return "▰" * filled + "▱" * (20 - filled)


BANDS: tuple[tuple[int, ProfileBand], ...] = (
    (
        20,
        ProfileBand(
            "Исключительный результат",
            "Все задания решены",
            "Ты прошёл весь тест без ошибок. Это редкий результат: он требует не только точности, но и устойчивости внимания на двадцати разных типах задач.",
        ),
    ),
    (
        18,
        ProfileBand(
            "Высокий уровень",
            "Очень сильный профиль",
            "Ты уверенно работаешь с закономерностями и сложными условиями. Даже там, где решение требует нескольких шагов, ты удерживаешь структуру задачи.",
        ),
    ),
    (
        15,
        ProfileBand(
            "Сильный профиль",
            "Выше среднего по тесту",
            "Логика и аналитика - твои рабочие инструменты. Отдельные ошибки чаще связаны с невнимательностью или необычной формулировкой, а не с отсутствием метода.",
        ),
    ),
    (
        12,
        ProfileBand(
            "Уверенный уровень",
            "Хорошая база",
            "Ты справляешься с большинством типовых закономерностей. Потенциал роста - в многошаговых задачах, где важно проверять все условия, а не только очевидные.",
        ),
    ),
    (
        8,
        ProfileBand(
            "Рабочий профиль",
            "Есть заметные сильные стороны",
            "Базовые закономерности тебе доступны, но часть задач требует более системного разбора. Навык декомпозиции условий заметно улучшается с практикой.",
        ),
    ),
    (
        4,
        ProfileBand(
            "Формирующийся профиль",
            "Точка роста",
            "Часть заданий оказалась непривычной. Это не оценка интеллекта, а снимок конкретного навыка: умение искать правило там, где его не подсказывают.",
        ),
    ),
    (
        0,
        ProfileBand(
            "Стартовая точка",
            "Первое прохождение",
            "Тест оказался сложным вызовом. Полезно разобрать объяснения к заданиям: большинство из них решается через один-два чётких шага, а не через догадку.",
        ),
    ),
)


def _band_for(correct: int) -> ProfileBand:
    for threshold, band in BANDS:
        if correct >= threshold:
            return band
    return BANDS[-1][1]


def analyze(test: TestRecord, answers: list[AnswerRecord]) -> Analysis:
    answers_by_index = {a.question_index: a for a in answers}

    category_correct: dict[str, int] = {key: 0 for key in CATEGORIES}
    category_total: dict[str, int] = {key: 0 for key in CATEGORIES}

    wrong: list[tuple[AnswerRecord, Question]] = []
    for question in QUESTIONS:
        category_total[question.category] += 1
        answer = answers_by_index.get(question.index)
        if answer and answer.is_correct:
            category_correct[question.category] += 1
        elif answer:
            wrong.append((answer, question))

    stats = tuple(
        CategoryStat(
            key=category.key,
            title=category.title,
            correct=category_correct[category.key],
            total=category_total[category.key],
        )
        for category in CATEGORIES.values()
        if category_total[category.key] > 0
    )

    ranked = sorted(
        stats,
        key=lambda item: (item.percent, item.correct, item.total),
        reverse=True,
    )
    strengths = tuple(ranked[:2])
    growth = tuple(sorted(stats, key=lambda item: (item.percent, item.correct))[:2])

    correct = sum(1 for a in answers if a.is_correct)
    accuracy = round(correct / len(QUESTIONS) * 100)

    return Analysis(
        test=test,
        correct=correct,
        total=len(QUESTIONS),
        accuracy=accuracy,
        categories=stats,
        strengths=strengths,
        growth=growth,
        wrong=tuple(sorted(wrong, key=lambda pair: pair[1].index)),
        band=_band_for(correct),
    )


def answer_letter(option_index: int) -> str:
    return "ABCD"[option_index] if 0 <= option_index <= 3 else "-"


def correct_letter(question: Question) -> str:
    return answer_letter(question.correct_index)
