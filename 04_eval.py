"""Демо 4: eval для Демо 1 — скільки питань агент розв'язує без reflection і з ним.

Запуск:  python 04_eval.py
"""

import importlib
import json
import re
from datetime import datetime

from rich.console import Console
from rich.table import Table

from common.config import EVAL_PATH
from common.log import TRACES_DIR, Logger

# Файл демо починається з цифри, тому звичайний import не спрацює
demo = importlib.import_module("01_reflection_sql")

console = Console(width=100, highlight=False)

# Основи назв місяців: «серпень», «серпні», «серпня» -> 8
MONTH_STEMS = {
    "січ": 1, "лют": 2, "берез": 3, "квіт": 4, "трав": 5, "черв": 6,
    "лип": 7, "серп": 8, "верес": 9, "жовт": 10, "листоп": 11, "груд": 12,
}


# === 1. Порівняння відповіді з еталоном ===

def normalize(text):
    """Нижній регістр, без лапок і розділових знаків."""
    text = re.sub(r"[«»\"'“”„’.,!?:;()]", " ", str(text).lower())
    return text.split()


def month_number(text):
    """Номер місяця з «серпень 2026», «у серпні» або «08.2026»; інакше None."""
    for word in normalize(text):
        for stem, number in MONTH_STEMS.items():
            if word.startswith(stem):
                return number
    match = re.search(r"\b(\d{1,2})\.\d{4}\b", str(text))
    return int(match.group(1)) if match else None


def parse_number(text):
    """«1073450.5» або «416 082,5» -> число; інакше None."""
    try:
        return float(str(text).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def same_words(expected, got):
    """Кожне слово еталона є у відповіді з точністю до закінчення: «Генератори» = «Генераторів»."""
    got_words = normalize(got)
    for word in normalize(expected):
        stem = word[: max(3, len(word) - 2)]
        if not any(g.startswith(stem) for g in got_words):
            return False
    return True


def is_correct(item, value):
    """Чи збігається value з expected з урахуванням типу і допуску."""
    expected = item["expected"]
    if item["type"] == "number":
        got = parse_number(value)
        return got is not None and abs(got - expected) <= item["tolerance"] * abs(expected)
    if month_number(expected):
        return month_number(value) == month_number(expected)
    return same_words(expected, value)


# === 2. Прогін ===

def run_question(item, reflection, log):
    """Одне питання в одному режимі."""
    result = demo.answer_question(item["question"], log, reflection=reflection)
    result["correct"] = is_correct(item, result["value"])
    return result


def run_all(items, log):
    """Усі питання в обох режимах, з прогресом на екрані."""
    results = []
    for i, item in enumerate(items, start=1):
        console.print(f"питання {i}/{len(items)}…", end=" ")
        row = {"question": item["question"], "trap": item["trap"], "expected": item["expected"]}
        row["no_reflection"] = run_question(item, False, log)
        row["reflection"] = run_question(item, True, log)
        marks = ["✓" if row[mode]["correct"] else "✗" for mode in ("no_reflection", "reflection")]
        console.print(f"без reflection {marks[0]} · з reflection {marks[1]} "
                      f"(спроб: {row['reflection']['attempts']})")
        results.append(row)
    return results


def accuracy(results, mode):
    return sum(r[mode]["correct"] for r in results) / len(results)


# === 3. Звіт ===

def mark(correct):
    return "[bold green]✓[/]" if correct else "[bold red]✗[/]"


def print_table(results):
    table = Table(title="Eval Демо 1", width=100)
    table.add_column("#", justify="right")
    table.add_column("Питання", max_width=44, no_wrap=True, overflow="ellipsis")
    table.add_column("Пастка")
    table.add_column("Без refl.", justify="center")
    table.add_column("З refl.", justify="center")
    table.add_column("Спроби", justify="center")

    for i, row in enumerate(results, start=1):
        table.add_row(str(i), row["question"], row["trap"], mark(row["no_reflection"]["correct"]),
                      mark(row["reflection"]["correct"]), str(row["reflection"]["attempts"]))
    console.print()
    console.print(table)
    console.print(f"[bold]Точність:[/] без reflection [bold]{accuracy(results, 'no_reflection'):.0%}[/] · "
                  f"з reflection [bold]{accuracy(results, 'reflection'):.0%}[/]")


def print_errors(results):
    """Error analysis: де помилився агент навіть з reflection."""
    console.print("\n[bold red]Помилки з reflection[/]")
    errors = [row for row in results if not row["reflection"]["correct"]]
    for row in errors:
        result = row["reflection"]
        console.print(f"\n[bold]{row['question']}[/] [dim](пастка {row['trap']})[/]")
        console.print(f"  очікувано: {row['expected']}")
        console.print(f"  отримано:  {result['value']!r} — {result['answer_text']}")
        console.print(f"  SQL: {' '.join(result['sql'].split())}")
    if not errors:
        console.print("  немає")


def save_results(results):
    path = TRACES_DIR / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "accuracy": {mode: accuracy(results, mode) for mode in ("no_reflection", "reflection")},
        "results": results,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    with open(EVAL_PATH, encoding="utf-8") as f:
        items = json.load(f)

    log = Logger("04_eval", quiet=True)  # повний трейс усіх викликів, на екран — лише прогрес
    results = run_all(items, log)

    print_table(results)
    print_errors(results)
    path = save_results(results)

    cost = log.cost()
    console.print(f"\nВикликів моделі: {log.calls} · час моделі: {log.model_seconds:.0f} с · "
                  f"вартість: {'ціна невідома' if cost is None else f'${cost:.4f}'}")
    console.print(f"[dim]Результат: {path.name}[/]")
