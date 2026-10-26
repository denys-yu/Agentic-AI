"""Демо 4: eval для Демо 1 — скільки питань агент розв'язує без reflection і з ним.

Запуск:
    python 04_eval.py              # один прогін eval_set.json
    python 04_eval.py --repeat 3   # 3 прогони, середня точність
"""

import importlib
import json
import re
import sys
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

MODES = [("no_reflection", False), ("reflection", True)]


# ---------------------------------------------------------------------------
# Порівняння відповіді з еталоном
# ---------------------------------------------------------------------------

def normalize(text):
    """Нижній регістр, без лапок і розділових знаків."""
    text = re.sub(r"[«»\"'“”„’.,!?:;()]", " ", str(text).lower())
    return text.split()


def month_number(text):
    """Номер місяця з «серпень 2026», «у серпні», «08.2026» або «2026-08»; інакше None."""
    for word in normalize(text):
        for stem, number in MONTH_STEMS.items():
            if word.startswith(stem):
                return number
    match = re.search(r"\b(\d{1,2})\.\d{4}\b", str(text)) or re.search(r"\b\d{4}-(\d{2})\b", str(text))
    return int(match.group(1)) if match else None


def parse_number(text):
    """«1 073 450 грн», «1073450.5», «416 082,5» -> число; інакше None."""
    digits = re.sub(r"[^\d,.\-]", "", str(text))
    if "," in digits and "." in digits or digits.count(",") > 1:
        digits = digits.replace(",", "")
    try:
        return float(digits.replace(",", "."))
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


# ---------------------------------------------------------------------------
# Прогін
# ---------------------------------------------------------------------------

def run_question(item, reflection, log):
    """Одне питання в одному режимі. Збій API не зупиняє весь eval."""
    try:
        result = demo.answer_question(item["question"], reflection=reflection, log=log)
    except Exception as error:
        result = {"sql": "", "rows": [], "attempts": 0, "answer_text": f"Збій: {error}", "value": ""}
    result["correct"] = is_correct(item, result["value"])
    return result


def run_once(items, run_index, repeats, log):
    """Один прогін усього набору в обох режимах."""
    results = []
    for i, item in enumerate(items, start=1):
        console.print(f"[повтор {run_index}/{repeats}] питання {i}/{len(items)}…", end=" ")
        row = {"question": item["question"], "trap": item["trap"], "expected": item["expected"]}
        for mode, reflection in MODES:
            row[mode] = run_question(item, reflection, log)
        marks = ["✓" if row[mode]["correct"] else "✗" for mode, _ in MODES]
        console.print(f"без reflection {marks[0]} · з reflection {marks[1]} "
                      f"(спроб: {row['reflection']['attempts']})")
        results.append(row)
    return results


def accuracy(results, mode):
    return sum(r[mode]["correct"] for r in results) / len(results)


# ---------------------------------------------------------------------------
# Звіт
# ---------------------------------------------------------------------------

def mark(correct_count, repeats):
    """✓/✗ для одного прогону, k/N для кількох."""
    if repeats == 1:
        return "[bold green]✓[/]" if correct_count else "[bold red]✗[/]"
    color = "green" if correct_count == repeats else "red" if correct_count == 0 else "yellow"
    return f"[{color}]{correct_count}/{repeats}[/]"


def print_table(items, runs):
    repeats = len(runs)
    table = Table(title="Eval Демо 1", width=100)
    table.add_column("#", justify="right")
    table.add_column("Питання", max_width=44)
    table.add_column("Пастка")
    table.add_column("Без refl.", justify="center")
    table.add_column("З refl.", justify="center")
    table.add_column("Спроби", justify="center")

    for i, item in enumerate(items):
        rows = [run[i] for run in runs]
        plain = sum(r["no_reflection"]["correct"] for r in rows)
        refl = sum(r["reflection"]["correct"] for r in rows)
        attempts = sum(r["reflection"]["attempts"] for r in rows) / repeats
        question = item["question"] if len(item["question"]) <= 44 else item["question"][:43] + "…"
        table.add_row(str(i + 1), question, item["trap"], mark(plain, repeats), mark(refl, repeats),
                      f"{attempts:g}")
    console.print()
    console.print(table)

    plain = sum(accuracy(run, "no_reflection") for run in runs) / repeats
    refl = sum(accuracy(run, "reflection") for run in runs) / repeats
    note = f" (середнє за {repeats} прогони)" if repeats > 1 else ""
    console.print(f"[bold]Точність{note}:[/] без reflection [bold]{plain:.0%}[/] · "
                  f"з reflection [bold]{refl:.0%}[/]")


def print_errors(runs):
    """Error analysis: де помилився агент навіть з reflection."""
    console.print("\n[bold red]Помилки з reflection[/]")
    found = False
    for run_index, run in enumerate(runs, start=1):
        for row in run:
            result = row["reflection"]
            if result["correct"]:
                continue
            found = True
            console.print(f"\n[bold]{row['question']}[/] [dim](прогін {run_index}, пастка {row['trap']})[/]")
            console.print(f"  очікувано: {row['expected']}")
            console.print(f"  отримано:  {result['value']!r} — {result['answer_text']}")
            console.print(f"  SQL: {' '.join(result['sql'].split())}")
    if not found:
        console.print("  немає")


def save_results(runs, log):
    path = TRACES_DIR / f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report = {
        "repeats": len(runs),
        "accuracy": {mode: [accuracy(run, mode) for run in runs] for mode, _ in MODES},
        "cost_usd": log.cost(),
        "runs": runs,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return path


if __name__ == "__main__":
    repeats = int(sys.argv[sys.argv.index("--repeat") + 1]) if "--repeat" in sys.argv else 1

    with open(EVAL_PATH, encoding="utf-8") as f:
        items = json.load(f)

    log = Logger("04_eval", quiet=True)  # повний трейс усіх викликів, на екран — лише прогрес
    runs = [run_once(items, r, repeats, log) for r in range(1, repeats + 1)]

    print_table(items, runs)
    print_errors(runs)
    path = save_results(runs, log)

    cost = log.cost()
    console.print(f"\nВикликів моделі: {log.calls} · час моделі: {log.model_seconds:.0f} с · "
                  f"вартість: {'ціна невідома' if cost is None else f'${cost:.4f}'}")
    console.print(f"[dim]Результат: {path.name}[/]")
