"""Спільні константи для всіх демо майстер-класу."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Фіксована «сьогоднішня» дата: усі демо рахують відносно неї
TODAY = "04.11.2026"

# Курси валют до гривні (спрощені, лише для демо)
RATES_TO_UAH = {"UAH": 1.0, "USD": 41.5, "EUR": 48.0}

# Корінь проєкту = тека, в якій лежить папка common
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# База пожертв і набір питань для перевірки агента
DB_PATH = PROJECT_ROOT / "donations.sqlite"
EVAL_PATH = PROJECT_ROOT / "eval_set.json"

# Змінні з .env потрапляють у os.environ; далі код бере ключ лише звідти
load_dotenv(PROJECT_ROOT / ".env")

# Моделі: швидка (GPT-6 Luna) і розумна (GPT-6.1 Sol)
MODEL_FAST = os.getenv("MODEL_FAST") or "gpt-6-luna"
MODEL_SMART = os.getenv("MODEL_SMART") or "gpt-6.1-sol"

# Мінімальне «обдумування» для Responses API: reasoning={"effort": ...}
# Luna вміє "none", а Sol — щонайменше "low" (none/minimal повертають помилку)
EFFORT_FAST = "none"
EFFORT_SMART = "low"

# Ціна за 1M токенів у $: (вхід, вихід), станом на жовтень 2026
PRICES = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6.1-sol": (2.00, 10.00),
}


def require_api_key():
    """Зупиняє демо зі зрозумілою підказкою, якщо ключа немає."""
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("Немає OPENAI_API_KEY. Створи .env за зразком .env.example")
