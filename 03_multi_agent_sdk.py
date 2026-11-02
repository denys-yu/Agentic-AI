"""Демо 3: команда агентів на OpenAI Agents SDK.

Та сама задача, що в Демо 2, але цикл крутить фреймворк, а роботу ділять три агенти:
менеджер бере цифри в аналітика, а текст подяки — в автора.

Запуск:
    python 03_multi_agent_sdk.py                      # основна задача
    python 03_multi_agent_sdk.py "питання від залу"
"""

import sys
import time
from typing import Literal

from agents import Agent, ModelSettings, Runner, function_tool, gen_trace_id, trace
from openai.types.shared import Reasoning

from common.config import EFFORT_FAST, EFFORT_SMART, MODEL_FAST, MODEL_SMART, TODAY, require_api_key
from common.db import connect_ro
from common.log import Logger

TASK = "Підготуй подяку донорам за минулий місяць з підсумками збору"
MAX_TURNS = 10  # той самий запобіжник, що MAX_STEPS у Демо 2

INSTRUCTIONS = ("Ти аналітик благодійного фонду. "
                "Загальну суму подавай у гривнях і доларах, решту сум — у гривнях. "
                "Для відносних дат і дат без року («минулий місяць», «вчора», «у жовтні») "
                "спершу виклич get_today. "
                "Цифри бери лише з результатів інструментів. "
                "Будь-який підсумок отримуй одним SQL-запитом, сам числа не додавай. "
                "Фінальну відповідь пиши простим текстом без Markdown.")

require_api_key()
log = Logger("03_multi_agent_sdk")


# === 1. Інструменти: ті самі функції, але замість схеми — декоратор і docstring ===

@function_tool
def query_db(sql: str):
    """Виконує SQL-запит до бази SQLite (лише читання) і повертає до 50 рядків.
    Таблиці:
    - donations(id, date, campaign, amount, currency, donor_type, comment)
    - campaigns(name, goal_uah, start_date, status)
    - exchange_rates(currency, rate_to_uah)
    date — текст у форматі DD.MM.YYYY. Для місяця фільтруй substr(date, 4, 7) = 'MM.YYYY'. Дати як рядки не порівнюй.
    Пожертви бувають в UAH, USD і EUR. Суми рахуй у гривнях: amount * rate_to_uah з таблиці exchange_rates.
    Підсумки рахуй у SQL через SUM і GROUP BY, а не з окремих рядків."""
    log.action("query_db", {"sql": sql})  # щоб зал бачив прогрес
    conn = connect_ro()
    cursor = conn.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchmany(50)
    conn.close()
    return [dict(zip(columns, row)) for row in rows]


@function_tool
def get_today():
    """Повертає сьогоднішню дату у форматі DD.MM.YYYY."""
    log.action("get_today", {})
    return TODAY


@function_tool
def convert_currency(amount: float, from_currency: Literal["UAH", "USD", "EUR"],
                     to_currency: Literal["UAH", "USD", "EUR"]):
    """Перераховує готовий підсумок з однієї валюти в іншу за курсами з exchange_rates. Результат округлено до 2 знаків."""
    log.action("convert_currency", {"amount": amount, "from_currency": from_currency,
                                    "to_currency": to_currency})
    conn = connect_ro()
    rates = dict(conn.execute("SELECT currency, rate_to_uah FROM exchange_rates").fetchall())
    conn.close()
    return round(amount * rates[from_currency] / rates[to_currency], 2)


# === 2. Команда агентів ===

analyst = Agent(
    name="Аналітик", instructions=INSTRUCTIONS, model=MODEL_FAST,
    model_settings=ModelSettings(reasoning=Reasoning(effort=EFFORT_FAST)),
    tools=[query_db, get_today, convert_currency])

writer = Agent(
    name="Автор", model=MODEL_FAST,
    model_settings=ModelSettings(reasoning=Reasoning(effort=EFFORT_FAST)),
    instructions="Пиши теплу подяку донорам українською, до 150 слів. Використовуй лише цифри, "
                 "які тобі передали, нових не вигадуй. Кількість пожертв не називай кількістю донорів. "
                 "Простий текст без Markdown.")

# Менеджер кличе інших агентів як звичайні інструменти
manager = Agent(
    name="Менеджер", model=MODEL_SMART,
    model_settings=ModelSettings(reasoning=Reasoning(effort=EFFORT_SMART)),
    instructions="Ти координатор фонду. Цифри отримуй лише в аналітика, текст подяки — лише в автора. "
                 "Сам не рахуй і не пиши подяку. Передай автору цифри від аналітика і поверни його текст.",
    tools=[analyst.as_tool("analyst", "Рахує підсумки пожертв за даними з бази"),
           writer.as_tool("writer", "Пише текст подяки донорам за переданими цифрами")])


# === 3. Запуск: цикл тепер усередині Runner ===

if __name__ == "__main__":
    task = " ".join(sys.argv[1:]) or TASK
    log.title("Демо 3: команда агентів")
    log.note(f"Задача: {task}")

    trace_id = gen_trace_id()
    start = time.perf_counter()
    with trace("Демо 3: команда агентів", trace_id=trace_id):
        result = Runner.run_sync(manager, task, max_turns=MAX_TURNS)

    log.answer(result.final_output)
    tokens = result.context_wrapper.usage.total_tokens
    log.note(f"Час: {time.perf_counter() - start:.1f} с   токени: {tokens:,}".replace(",", " "))
    log.note(f"Трейс: https://platform.openai.com/logs/trace?trace_id={trace_id}")
