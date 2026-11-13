"""Авторский банк заданий NOEMA.

Каждый вопрос имеет ровно четыре варианта и один однозначно верный ответ.
Порядок вопросов выстроен по возрастанию сложности: от простых
закономерностей к многошаговым аналитическим задачам.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Category:
    key: str
    title: str
    short: str
    strength: str


CATEGORIES: dict[str, Category] = {
    "numerical": Category(
        key="numerical",
        title="Числовые закономерности",
        short="Числа",
        strength="умение видеть числовые связи и удерживать алгоритм",
    ),
    "logic": Category(
        key="logic",
        title="Логическое мышление",
        short="Логика",
        strength="последовательность рассуждений и работа с условиями",
    ),
    "spatial": Category(
        key="spatial",
        title="Пространственное мышление",
        short="Пространство",
        strength="мысленное моделирование форм и пространственных операций",
    ),
    "abstract": Category(
        key="abstract",
        title="Абстрактные закономерности",
        short="Абстракция",
        strength="распознавание структуры без опоры на привычные признаки",
    ),
    "analytical": Category(
        key="analytical",
        title="Аналитические задачи",
        short="Аналитика",
        strength="декомпозиция задач и проверка гипотез",
    ),
    "pattern": Category(
        key="pattern",
        title="Поиск закономерностей",
        short="Паттерны",
        strength="чувствительность к повторяющимся правилам и ритму",
    ),
    "math": Category(
        key="math",
        title="Математическая логика",
        short="Математика",
        strength="точность вычислений и математическая интуиция",
    ),
}


@dataclass(frozen=True, slots=True)
class Question:
    index: int
    text: str
    options: tuple[str, str, str, str]
    correct_index: int
    explanation: str
    difficulty: int
    category: str
    image: str | None = None

    @property
    def category_title(self) -> str:
        return CATEGORIES[self.category].title

    @property
    def correct_option(self) -> str:
        return self.options[self.correct_index]

    @property
    def letter(self) -> str:
        return "ABCD"[self.correct_index]

    def difficulty_dots(self) -> str:
        return "●" * self.difficulty + "○" * (5 - self.difficulty)


QUESTIONS: tuple[Question, ...] = (
    Question(
        index=1,
        text="Продолжи последовательность:\n<b>2 · 4 · 8 · 16 · ?</b>",
        options=("24", "30", "32", "36"),
        correct_index=2,
        explanation="Каждое следующее число вдвое больше предыдущего: 2 → 4 → 8 → 16 → 32.",
        difficulty=1,
        category="numerical",
    ),
    Question(
        index=2,
        text="Найди лишнее:\n<b>круг · квадрат · треугольник · ромб</b>",
        options=("Круг", "Квадрат", "Треугольник", "Ромб"),
        correct_index=0,
        explanation="У круга нет углов. Остальные фигуры - многоугольники, и их форма задаётся прямыми сторонами.",
        difficulty=1,
        category="abstract",
    ),
    Question(
        index=3,
        text="Продолжи последовательность:\n<b>3 · 6 · 11 · 18 · 27 · ?</b>",
        options=("36", "38", "40", "42"),
        correct_index=1,
        explanation="Разности растут на 2: 3 → 6 (+3), 6 → 11 (+5), 11 → 18 (+7), 18 → 27 (+9). Следующая разность 11, значит 27 + 11 = 38.",
        difficulty=2,
        category="numerical",
    ),
    Question(
        index=4,
        text="Все инженеры логичны. Ни один логичный человек не импульсивен.\n\n<b>Какой вывод следует из этих утверждений?</b>",
        options=(
            "Все инженеры не импульсивны",
            "Некоторые инженеры импульсивны",
            "Все импульсивные люди - инженеры",
            "Ни один инженер не является логичным",
        ),
        correct_index=0,
        explanation="Инженер → логичен → не импульсивен.\n\nЗначит, любой инженер не импульсивен. Обратный вывод «все импульсивные люди являются инженерами» из условия не следует.",
        difficulty=2,
        category="logic",
    ),
    Question(
        index=5,
        text="Продолжи последовательность:\n<b>1 · 1 · 2 · 3 · 5 · 8 · ?</b>",
        options=("11", "12", "13", "15"),
        correct_index=2,
        explanation="Каждое число равно сумме двух предыдущих: 1 + 1 = 2, 1 + 2 = 3, 2 + 3 = 5, 3 + 5 = 8, 5 + 8 = 13. Это ряд Фибоначчи.",
        difficulty=2,
        category="pattern",
    ),
    Question(
        index=6,
        text="У фермера было 17 овец. <b>Все, кроме 9</b>, убежали.\n\nСколько овец осталось?",
        options=("8", "9", "17", "0"),
        correct_index=1,
        explanation="Фраза «все, кроме 9» означает, что убежали все, кроме девяти. Следовательно, осталось ровно 9 овец.",
        difficulty=2,
        category="math",
    ),
    Question(
        index=7,
        text="Куб <b>3 × 3 × 3</b> окрасили снаружи и распилили на 27 маленьких кубов.\n\nСколько маленьких кубов имеют <b>ровно две</b> окрашенные грани?",
        options=("6", "8", "12", "24"),
        correct_index=2,
        explanation="Ровно две окрашенные грани имеют кубы на рёбрах, но не в углах.\n\nУ куба 12 рёбер, и на каждом ребре такой куб один: 12 × 1 = 12.\n\nУгловые кубы имеют три окрашенные грани. Центральные не имеют окрашенных граней вовсе.",
        difficulty=3,
        category="spatial",
    ),
    Question(
        index=8,
        text="Продолжи последовательность:\n<b>2 · 5 · 10 · 17 · 26 · ?</b>",
        options=("35", "36", "37", "38"),
        correct_index=2,
        explanation="Разности: +3, +5, +7, +9. Следующая разность +11, поэтому 26 + 11 = 37. Тот же ряд можно записать как n² + 1.",
        difficulty=3,
        category="numerical",
    ),
    Question(
        index=9,
        text="Какая фигура должна стоять вместо знака вопроса?",
        options=("Круг", "Квадрат", "Треугольник", "Ромб"),
        correct_index=0,
        explanation="В каждой строке и каждом столбце встречается ровно по одной фигуре каждого вида.\n\nВ нижней строке уже есть квадрат и треугольник. В правом столбце тоже есть треугольник и квадрат. Значит, пропущен круг.",
        difficulty=3,
        category="abstract",
        image="q09.jpg",
    ),
    Question(
        index=10,
        text="Продолжи последовательность:\n<b>5 · 11 · 8 · 14 · 11 · 17 · ?</b>",
        options=("13", "14", "15", "20"),
        correct_index=1,
        explanation="Действия чередуются: +6, −3, +6, −3, +6, −3. После 17 идёт 17 − 3 = 14.",
        difficulty=3,
        category="pattern",
    ),
    Question(
        index=11,
        text="В комнате три выключателя, а в соседней комнате - лампа. Изначально лампа выключена. <b>Зайти в комнату с лампой можно только один раз.</b>\n\nКак точно определить нужный выключатель?",
        options=(
            "Включить все три и войти",
            "Первый нагреть, выключить; включить второй",
            "Включить второй и третий",
            "Без приборов невозможно",
        ),
        correct_index=1,
        explanation="Если лампа горит, работает второй выключатель.\n\nЕсли лампа не горит, но колба тёплая, работает первый: он успел нагреть лампу, пока был включён.\n\nЕсли колба холодная, остаётся третий. Нагрев даёт вторую независимую подсказку.",
        difficulty=3,
        category="analytical",
    ),
    Question(
        index=12,
        text="Известно, что <b>2 → 6</b>, <b>3 → 12</b>, <b>4 → 20</b>.\n\nЧему равно <b>5 → ?</b>",
        options=("25", "28", "30", "35"),
        correct_index=2,
        explanation="Правило: число умножается на следующее за ним: 2 × 3 = 6, 3 × 4 = 12, 4 × 5 = 20. Значит, 5 × 6 = 30.",
        difficulty=3,
        category="pattern",
    ),
    Question(
        index=13,
        text="На столе лежат карточки: <b>A · K · 4 · 7</b>. Известно правило: <b>если на одной стороне гласная, то на другой - чётное число.</b>\n\nКакие карточки нужно перевернуть, чтобы проверить правило?",
        options=(
            "Только A",
            "A и 4",
            "A и 7",
            "Все четыре карточки",
        ),
        correct_index=2,
        explanation="Проверить нужно две карточки.\n\nA: на обороте должно быть чётное число, иначе правило нарушено.\n\n7: на обороте не должно быть гласной, иначе правило тоже нарушено.\n\nK: это согласная, правило к ней не применяется.\n\n4: чётное число. Правило не требует гласной на обороте, поэтому карточку можно не переворачивать.",
        difficulty=4,
        category="logic",
    ),
    Question(
        index=14,
        text="Сколько раз цифра <b>9</b> встречается в записи всех чисел от 1 до 100 включительно?",
        options=("10", "18", "19", "20"),
        correct_index=3,
        explanation="В разряде единиц: 9, 19, 29, …, 99. Это 10 раз.\n\nВ разряде десятков: 90, 91, …, 99. Ещё 10 раз.\n\nВ числе 99 цифра 9 стоит дважды, и это уже учтено. Итого: 10 + 10 = 20.",
        difficulty=4,
        category="math",
    ),
    Question(
        index=15,
        text="В турнире участвуют <b>6 команд</b>. Каждая играет с каждой ровно один раз.\n\nСколько всего матчей будет проведено?",
        options=("12", "15", "18", "30"),
        correct_index=1,
        explanation="Первую команду можно выбрать 6 способами, вторую 5 способами. Но порядок команд в паре не важен, поэтому делим на 2.\n\n6 × 5 / 2 = 15 матчей.",
        difficulty=4,
        category="analytical",
    ),
    Question(
        index=16,
        text="В семье четверо детей. <b>У каждого ребёнка есть хотя бы один брат и хотя бы одна сестра.</b>\n\nСколько в семье мальчиков и сколько девочек?",
        options=(
            "1 мальчик и 3 девочки",
            "2 мальчика и 2 девочки",
            "3 мальчика и 1 девочка",
            "Определить невозможно",
        ),
        correct_index=1,
        explanation="Если мальчик один, у него нет брата. Если девочка одна, у неё нет сестры.\n\nЗначит, детей каждого пола должно быть минимум двое. При четверых детях возможен только вариант 2 мальчика и 2 девочки.",
        difficulty=4,
        category="logic",
    ),
    Question(
        index=17,
        text="Лист бумаги сложили пополам <b>три раза</b>, затем пробили одно отверстие насквозь. Отверстие не попало на линию сгиба.\n\nСколько отверстий будет на листе после разворота?",
        options=("3", "6", "8", "9"),
        correct_index=2,
        explanation="Каждое складывание удваивает число слоёв. После трёх сложений их 2³ = 8.\n\nОдно отверстие проходит через все восемь слоёв. После разворота будет 8 отверстий.",
        difficulty=4,
        category="spatial",
    ),
    Question(
        index=18,
        text="Продолжи последовательность:\n<b>3 · 7 · 16 · 35 · 74 · ?</b>",
        options=("145", "148", "153", "160"),
        correct_index=2,
        explanation="Правило: умножить на 2 и прибавить возрастающее число.\n\n3 × 2 + 1 = 7\n7 × 2 + 2 = 16\n16 × 2 + 3 = 35\n35 × 2 + 4 = 74\n74 × 2 + 5 = 153",
        difficulty=5,
        category="numerical",
    ),
    Question(
        index=19,
        text="Ровно один из трёх подозреваемых говорит правду.\n\n<b>Алекс:</b> «Это сделал не я».\n<b>Борис:</b> «Это сделал Алекс».\n<b>Виктор:</b> «Это сделал не Борис».\n\nКто виновен?",
        options=("Алекс", "Борис", "Виктор", "Невозможно определить"),
        correct_index=1,
        explanation="Если виновен Борис: Алекс говорит правду, Борис лжёт, Виктор лжёт. Ровно один правдивый: условие выполнено.\n\nПроверим других. При виновном Алексе правы Борис и Виктор. При виновном Викторе правы Алекс и Виктор.\n\nЗначит, виновен Борис.",
        difficulty=5,
        category="analytical",
    ),
    Question(
        index=20,
        text="Часы отстают на <b>2 минуты за каждый реальный час</b>. В 12:00 они показывали точное время.\n\nЧто покажут часы в <b>18:00</b> реального времени?",
        options=("17:48", "17:52", "17:56", "18:00"),
        correct_index=0,
        explanation="С 12:00 до 18:00 проходит 6 реальных часов. Часы отстают на 6 × 2 = 12 минут. Значит, в 18:00 они покажут 17:48.",
        difficulty=5,
        category="math",
    ),
)

TOTAL_QUESTIONS = len(QUESTIONS)


def validate_questions() -> None:
    """Жёсткая проверка целостности банка заданий."""
    if len(QUESTIONS) != 20:
        raise ValueError(f"Ожидалось 20 вопросов, найдено {len(QUESTIONS)}")
    if [q.index for q in QUESTIONS] != list(range(1, 21)):
        raise ValueError("Индексы вопросов должны идти непрерывно от 1 до 20")
    seen: set[str] = set()
    for q in QUESTIONS:
        if len(q.options) != 4:
            raise ValueError(f"Вопрос {q.index}: должно быть 4 варианта")
        if len(set(q.options)) != 4:
            raise ValueError(f"Вопрос {q.index}: варианты не уникальны")
        if not 0 <= q.correct_index < 4:
            raise ValueError(f"Вопрос {q.index}: некорректный правильный ответ")
        if q.category not in CATEGORIES:
            raise ValueError(f"Вопрос {q.index}: неизвестная категория")
        if q.difficulty not in range(1, 6):
            raise ValueError(f"Вопрос {q.index}: сложность вне диапазона")
        if not q.explanation.strip():
            raise ValueError(f"Вопрос {q.index}: нет объяснения")
        if q.text in seen:
            raise ValueError(f"Вопрос {q.index}: повтор текста")
        seen.add(q.text)
    difficulties = [q.difficulty for q in QUESTIONS]
    if difficulties != sorted(difficulties):
        raise ValueError("Сложность вопросов должна неубывать")


def get_question(index: int) -> Question:
    """Возвращает вопрос по человеческому индексу 1..20."""
    if not 1 <= index <= TOTAL_QUESTIONS:
        raise IndexError(f"Нет вопроса с индексом {index}")
    return QUESTIONS[index - 1]


def get_question_by_zero_based(index: int) -> Question:
    return get_question(index + 1)
