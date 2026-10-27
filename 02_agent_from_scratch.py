"""Демо 2: агентний цикл з нуля.

Модель думає → обирає дію (інструмент) → код виконує → модель бачить результат → і знову,
поки модель не дасть відповідь без виклику інструментів.

Запуск:
    python 02_agent_from_scratch.py                      # основна задача
    python 02_agent_from_scratch.py "питання від залу"
    python 02_agent_from_scratch.py --max-steps 2        # запобіжник: ліміт кроків
"""

import json
import sys
from pathlib import Path

from openai import OpenAI
from rich.prompt import Confirm

from common.config import EFFORT_FAST, MODEL_FAST as MODEL, PROJECT_ROOT, TODAY, require_api_key
from common.db import connect_ro
from common.log import Logger

TASK = "Підготуй короткий звіт про пожертви за минулий місяць у гривнях і доларах і збережи у файл"
MAX_STEPS = 10
REPORTS_DIR = PROJECT_ROOT / "reports"

INSTRUCTIONS = ("Ти аналітик благодійного фонду. "
                "Загальну суму подавай у гривнях і доларах, решту сум — у гривнях. "
                "Для відносних дат і дат без року («минулий місяць», «вчора», «у жовтні») "
                "спершу виклич get_today. "
                "Цифри бери лише з результатів інструментів. "
                "Будь-який підсумок отримуй одним SQL-запитом, сам числа не додавай. "
                "Фінальну відповідь пиши простим текстом без Markdown.")

require_api_key()
client = OpenAI()  # ключ з OPENAI_API_KEY
log = Logger("02_agent_from_scratch")


# === 1. Інструменти: звичайні функції Python ===

def query_db(sql):
    """Виконує SQL на базі тільки для читання. Повертає до 50 рядків."""
    conn = connect_ro()
    cursor = conn.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchmany(50)
    conn.close()
    return [dict(zip(columns, row)) for row in rows]


def get_today():
    return TODAY


def convert_currency(amount, from_currency, to_currency):
    """Перерахунок через гривню за курсами з таблиці exchange_rates."""
    conn = connect_ro()
    rates = dict(conn.execute("SELECT currency, rate_to_uah FROM exchange_rates").fetchall())
    conn.close()
    return round(amount * rates[from_currency] / rates[to_currency], 2)


def save_report(filename, markdown):
    """Зберігає звіт лише в reports/ і лише після підтвердження людини."""
    path = REPORTS_DIR / Path(filename).name  # Path(...).name відкидає теки: "../x.md" -> "x.md"
    if path.suffix != ".md":
        return "Помилка: дозволено зберігати лише файли .md"
    print(f"\nЗвіт буде збережено у {path.relative_to(PROJECT_ROOT)}:\n\n{markdown}\n")
    if not Confirm.ask("Зберегти звіт?"):
        return "Користувач відмовив у збереженні"
    REPORTS_DIR.mkdir(exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return f"Збережено: {path.relative_to(PROJECT_ROOT)}"


# === 2. Схеми інструментів: що модель знає про кожну функцію ===

TOOLS = [
    {"type": "function", "name": "query_db", "strict": True,
     "description": (
         "Виконує SQL-запит до бази SQLite (лише читання) і повертає до 50 рядків.\n"
         "Таблиці:\n"
         "- donations(id, date, campaign, amount, currency, donor_type, comment)\n"
         "- campaigns(name, goal_uah, start_date, status)\n"
         "- exchange_rates(currency, rate_to_uah)\n"
         "date — текст у форматі DD.MM.YYYY. Для місяця фільтруй substr(date, 4, 7) = 'MM.YYYY'. "
         "Дати як рядки не порівнюй.\n"
         "Пожертви бувають в UAH, USD і EUR. Суми рахуй у гривнях: "
         "amount * rate_to_uah з таблиці exchange_rates.\n"
         "Підсумки рахуй у SQL через SUM і GROUP BY, а не з окремих рядків."),
     "parameters": {"type": "object", "additionalProperties": False, "required": ["sql"],
                    "properties": {"sql": {"type": "string"}}}},

    {"type": "function", "name": "get_today", "strict": True,
     "description": "Повертає сьогоднішню дату у форматі DD.MM.YYYY.",
     "parameters": {"type": "object", "additionalProperties": False, "required": [],
                    "properties": {}}},

    {"type": "function", "name": "convert_currency", "strict": True,
     "description": "Перераховує готовий підсумок з однієї валюти в іншу за курсами з exchange_rates. "
                    "Результат округлено до 2 знаків.",
     "parameters": {"type": "object", "additionalProperties": False,
                    "required": ["amount", "from_currency", "to_currency"],
                    "properties": {"amount": {"type": "number"},
                                   "from_currency": {"type": "string", "enum": ["UAH", "USD", "EUR"]},
                                   "to_currency": {"type": "string", "enum": ["UAH", "USD", "EUR"]}}}},

    {"type": "function", "name": "save_report", "strict": True,
     "description": "Зберігає звіт у Markdown у папку reports/. Ім'я файлу має закінчуватися на .md. "
                    "Підтвердження в користувача програма запитає сама — просто виклич інструмент.",
     "parameters": {"type": "object", "additionalProperties": False, "required": ["filename", "markdown"],
                    "properties": {"filename": {"type": "string"}, "markdown": {"type": "string"}}}},
]


# === 3. Агентний цикл ===

def run_tool(name, args):
    """Виконує інструмент за назвою. Будь-яка помилка повертається моделі текстом."""
    tools = {"query_db": query_db, "get_today": get_today,
             "convert_currency": convert_currency, "save_report": save_report}
    try:
        result = tools[name](**args)
    except Exception as error:
        result = f"Помилка: {error}"
    return json.dumps(result, ensure_ascii=False)


def run_agent(task, max_steps):
    input = [{"role": "user", "content": task}]
    for step in range(max_steps):
        log.think(step=step + 1)
        resp = client.responses.create(
            model=MODEL, tools=TOOLS, input=input,
            instructions=INSTRUCTIONS, reasoning={"effort": EFFORT_FAST})
        log.usage(resp)
        input += resp.output
        calls = [i for i in resp.output if i.type == "function_call"]
        if not calls:
            return resp.output_text
        for c in calls:
            log.action(c.name, json.loads(c.arguments))
            out = run_tool(c.name, json.loads(c.arguments))
            log.result(out)
            input.append({"type": "function_call_output",
                          "call_id": c.call_id, "output": out})
    log.error("Ліміт кроків вичерпано")
    return None


if __name__ == "__main__":
    args = sys.argv[1:]
    max_steps = MAX_STEPS
    if "--max-steps" in args:
        i = args.index("--max-steps")
        max_steps = int(args[i + 1])
        del args[i:i + 2]
    task = " ".join(args) or TASK

    log.title("Демо 2: агентний цикл з нуля")
    log.note(f"Задача: {task}")
    answer = run_agent(task, max_steps)
    if answer:
        log.answer(answer)
    log.summary()
