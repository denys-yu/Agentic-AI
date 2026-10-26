"""Спільні константи для всіх демо майстер-класу."""

from pathlib import Path

# Фіксована «сьогоднішня» дата: усі демо рахують відносно неї
TODAY = "04.11.2026"

# Курси валют до гривні (спрощені, лише для демо)
RATES_TO_UAH = {"UAH": 1.0, "USD": 41.5, "EUR": 48.0}

# Корінь проєкту = тека, в якій лежить папка common
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# База пожертв і набір питань для перевірки агента
DB_PATH = PROJECT_ROOT / "donations.sqlite"
EVAL_PATH = PROJECT_ROOT / "eval_set.json"
