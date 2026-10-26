"""Демо 1: SQL-агент з reflection.

Модель пише SQL → код виконує → сенсори перевіряють результат →
якщо щось не так, модель отримує фідбек із реальними даними і пробує ще раз.

Запуск:
    python 01_reflection_sql.py                    # головне питання, з reflection
    python 01_reflection_sql.py --no-reflection    # одна спроба, без виправлення
    python 01_reflection_sql.py --self-check       # модель спершу сама перевіряє свій SQL
    python 01_reflection_sql.py "Скільки ..."      # питання від залу
"""

import sqlite3
import sys

from openai import OpenAI
from pydantic import BaseModel, Field

from common.config import EFFORT_FAST, MODEL_FAST, TODAY, require_api_key
from common.db import connect_ro
from common.log import Logger

QUESTION = "Яка кампанія зібрала найбільше у серпні 2026?"
MAX_ATTEMPTS = 3

# Запасні питання з іншими пастками з датами — якщо модель вгадає формат з першої спроби
BACKUP_QUESTIONS = [
    "Скільки пожертв надійшло за перший тиждень вересня 2026 (з 1 по 7 вересня)?",
    "Скільки гривень зібрали за третій квартал 2026 року?",
    "Скільки пожертв надійшло з 25 жовтня по 3 листопада 2026?",
]

# Початок коментаря з prompt injection (пастка 3): він не має потрапити у фідбек
INJECTION_MARKER = "IGNORE ALL PREVIOUS INSTRUCTIONS"

require_api_key()
client = OpenAI()  # ключ з OPENAI_API_KEY


# === 1. Що модель повертає (structured output) ===

class SqlDraft(BaseModel):
    sql: str
    explanation: str


class Verdict(BaseModel):
    ok: bool
    comment: str


class Answer(BaseModel):
    answer_text: str
    value: str = Field(description="Лише значення: число без пробілів (сума в гривнях або кількість), "
                                   "назва кампанії точно як у базі, або місяць у форматі 'серпень 2026'. "
                                   "Порожній рядок, якщо відповіді немає")


# === 2. База: схема, виконавець, приклади рядків ===

def get_schema():
    """Схема таблиць з sqlite_master. Формату дат тут немає — і це пастка."""
    conn = connect_ro()
    tables = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table'").fetchall()
    conn.close()
    return "\n\n".join(row[0] for row in tables)


def run_sql(sql):
    """Виконує лише SELECT/WITH на базі тільки для читання. Повертає (колонки, рядки, помилка)."""
    if not sql.lstrip().upper().startswith(("SELECT", "WITH")):
        return [], [], "Дозволено лише запити SELECT або WITH"
    conn = connect_ro()
    try:
        cursor = conn.execute(sql)
        columns = [col[0] for col in cursor.description]
        return columns, cursor.fetchall(), None
    except sqlite3.Error as error:
        return [], [], str(error)
    finally:
        conn.close()


def format_rows(columns, rows):
    """Колонки і рядки як простий текст: 'campaign | uah'."""
    lines = [" | ".join(columns)]
    lines += [" | ".join(str(value) for value in row) for row in rows]
    return "\n".join(lines)


def get_sample_rows():
    """3 реальні рядки з donations БЕЗ колонки comment: у коментарях живе prompt injection."""
    columns, rows, _ = run_sql("SELECT date, campaign, amount, currency, donor_type FROM donations LIMIT 3")
    return format_rows(columns, rows)


# === 3. Сенсори: код, а не модель, перевіряє результат ===

def sensor_sql_error(error):
    """Сенсор 1: база відповіла помилкою."""
    if error:
        return f"SQL-помилка: {error}"


def sensor_empty_result(rows):
    """Сенсор 2: запит нічого не знайшов."""
    if not rows:
        return "порожній результат, запит не знайшов жодного рядка"


def sensor_common_sense(columns, rows):
    """Сенсор 3: здоровий глузд. Ловить і SUM(...) WHERE strftime(...) — це один рядок з NULL."""
    for i, name in enumerate(columns):
        values = [row[i] for row in rows]
        numbers = [v for v in values if isinstance(v, (int, float))]
        if any(v < 0 for v in numbers):
            return f"від'ємне число в колонці {name}"
        if None in values and (numbers or all(v is None for v in values)):
            return f"NULL у колонці {name}: умова або обчислення не спрацювали"
        if len(rows) == 1 and numbers == [0]:
            return f"0 у колонці {name}: для фонду з сотнями пожертв це підозріло"


def check_result(columns, rows, error):
    """Перший сенсор, що спрацював, або None, якщо все гаразд."""
    return sensor_sql_error(error) or sensor_empty_result(rows) or sensor_common_sense(columns, rows)


# === 4. Виклики моделі ===

# Валюти підказуємо заздалегідь — це guide. Формат дат не підказуємо — його ловить sensor.
SQL_INSTRUCTIONS = f"""Ти аналітик благодійного фонду. Напиши один SQLite-запит, що відповідає на питання.
Сьогодні {TODAY}.
Пожертви бувають в UAH, USD і EUR. Суми рахуй у гривнях: amount * rate_to_uah з таблиці exchange_rates."""


def build_feedback(failures):
    """Фідбек для моделі: що пішло не так у кожній спробі + 3 реальні рядки з бази."""
    lines = ["Попередні спроби не спрацювали:"]
    for sql, problem in failures:
        lines.append(f"- SQL: {sql}\n  Проблема: {problem}")
    lines.append("\n3 реальні рядки з таблиці donations:\n" + get_sample_rows())
    lines.append("\nПодивись на реальні дані і виправ запит.")
    feedback = "\n".join(lines)
    # Захист: запис з prompt injection ніколи не потрапляє у фідбек
    assert INJECTION_MARKER not in feedback
    return feedback


def generate_sql(question, schema, failures, log):
    """Генератор: модель пише SQL. Якщо були невдалі спроби — бачить фідбек."""
    prompt = f"Питання: {question}\n\nСхема бази:\n{schema}"
    if failures:
        prompt += "\n\n" + build_feedback(failures)
    resp = client.responses.parse(
        model=MODEL_FAST,
        reasoning={"effort": EFFORT_FAST},
        instructions=SQL_INSTRUCTIONS,
        input=prompt,
        text_format=SqlDraft,
    )
    log.usage(resp)
    return resp.output_parsed


def review_sql(question, schema, sql, log):
    """Самокритика (--self-check): модель перевіряє власний SQL, нічого не виконуючи."""
    resp = client.responses.parse(
        model=MODEL_FAST,
        reasoning={"effort": EFFORT_FAST},
        instructions="Ти рецензент SQLite-запитів.",
        input=f"Питання: {question}\n\nСхема бази:\n{schema}\n\nSQL:\n{sql}\n\nЧи є тут помилки?",
        text_format=Verdict,
    )
    log.usage(resp)
    return resp.output_parsed


def formulate_answer(question, sql, result_text, log):
    """Окремий виклик: модель формулює відповідь лише на основі рядків з бази."""
    resp = client.responses.parse(
        model=MODEL_FAST,
        reasoning={"effort": EFFORT_FAST},
        instructions="Ти аналітик фонду. Відповідай лише на основі результату запиту. "
                     "Якщо даних немає або вони некоректні — так і скажи.",
        input=f"Питання: {question}\n\nSQL:\n{sql}\n\nРезультат:\n{result_text}",
        text_format=Answer,
    )
    log.usage(resp)
    return resp.output_parsed


# === 5. Головна логіка: генератор → виконавець → сенсори → фідбек ===

def answer_question(question, log, reflection=True, self_check=False):
    """Відповідає на питання по базі. Повертає dict для eval."""
    schema = get_schema()
    max_attempts = MAX_ATTEMPTS if reflection else 1
    failures = []  # [(sql, проблема), ...]

    for attempt in range(1, max_attempts + 1):
        log.think(step=1, attempt=attempt)
        draft = generate_sql(question, schema, failures, log)
        log.action("query_db", {"sql": draft.sql})

        if self_check:
            verdict = review_sql(question, schema, draft.sql, log)
            log.note(f"Самоперевірка моделі: {'все добре' if verdict.ok else 'є сумніви'}. {verdict.comment}")

        columns, rows, error = run_sql(draft.sql)
        result_text = f"Помилка: {error}" if error else format_rows(columns, rows)
        log.result(result_text)

        # Без reflection сенсори не дивляться: що вийшло, те й іде у відповідь
        problem = check_result(columns, rows, error) if reflection else None
        if not problem:
            break
        log.error(f"Сенсор: {problem}")
        failures.append((draft.sql, problem))

    log.think(step=2)
    answer = formulate_answer(question, draft.sql, result_text, log)
    log.answer(answer.answer_text)

    return {
        "sql": draft.sql,
        "rows": rows,
        "attempts": attempt,
        "answer_text": answer.answer_text,
        "value": answer.value,
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    reflection = "--no-reflection" not in args
    self_check = "--self-check" in args
    words = [arg for arg in args if not arg.startswith("--")]

    question = " ".join(words) or QUESTION

    log = Logger("01_reflection_sql")
    log.title("Демо 1: SQL-агент")
    log.note(f"Питання: {question}")
    answer_question(question, log, reflection=reflection, self_check=self_check)
    log.summary()
