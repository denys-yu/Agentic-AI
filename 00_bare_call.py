"""Демо 0: голий виклик моделі. Без інструментів LLM не знає нашого світу."""

from openai import OpenAI

from common.config import MODEL_FAST as MODEL, require_api_key
from common.db import connect_ro
from common.log import Logger

require_api_key()
log = Logger("00_bare_call")

# --- Запуск А: код зі слайда --------------------------------------------------
log.title("Демо 0 · Запуск А: просто питаємо модель")

client = OpenAI()  # ключ з OPENAI_API_KEY
resp = client.responses.create(
    model=MODEL,  # назва моделі з .env
    instructions="Ти аналітик фонду",
    input="Яка кампанія нашого фонду зібрала найбільше у серпні?",
)
print(resp.output_text)
log.usage(resp)

input("\nНатисни Enter для другого запуску…")

# --- Запуск Б: те саме питання, але модель знає схему таблиць -----------------
log.title("Демо 0 · Запуск Б: даємо схему бази")
tables = connect_ro().execute("SELECT sql FROM sqlite_master WHERE type = 'table'")
schema = "\n".join(row[0] for row in tables)

resp = client.responses.create(
    model=MODEL,
    instructions="Ти аналітик фонду. Схема нашої бази SQLite:\n" + schema,
    input="Яка кампанія нашого фонду зібрала найбільше у серпні?",
)
print(resp.output_text)
log.usage(resp)

log.note("Знати — не те саме, що діяти")
log.summary()
