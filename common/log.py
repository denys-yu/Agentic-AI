"""Логер агентного циклу: говорить словами слайда і пише трейс у traces/.

Використання в демо:
    log = Logger("02_agent_from_scratch")
    log.title("Демо 2: агент з нуля")
    log.think(step=1)
    log.usage(resp)
    log.action("query_db", {"sql": "SELECT ..."})
    log.result("...")
    log.answer("...")
    log.summary()

Перевірити вигляд без API:  python -m common.log
"""

import json
import textwrap
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from common.config import PRICES, PROJECT_ROOT

WIDTH = 100          # ширина рядка для трансляції
RESULT_LINES = 6     # скільки рядків результату показувати
TRACES_DIR = PROJECT_ROOT / "traces"

# Мітки блоків. Якщо емодзі ламають рамки в терміналі — заміни на текстові
LABELS = {
    "think": "🧠 ",
    "action": "🔧 ",
    "result": "👁 ",
    "error": "✖",
    "note": "💡",
}


def shorten(text, limit=WIDTH - 6):
    """Обрізає рядок, щоб він вліз у ширину екрана."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def format_call(name, args):
    """query_db, {"sql": "SELECT 1"} -> query_db(sql="SELECT 1")."""
    parts = [f"{key}={json.dumps(value, ensure_ascii=False)}" for key, value in args.items()]
    return f"{name}({', '.join(parts)})"


class Logger:
    """Друкує кроки агента на екран і записує їх у traces/<демо>_<час>.jsonl.

    quiet=True — нічого не друкувати, лише писати трейс (для eval).
    """

    def __init__(self, demo_name, quiet=False):
        self.console = Console(width=WIDTH, highlight=False, quiet=quiet)
        TRACES_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.trace_path = TRACES_DIR / f"{demo_name}_{stamp}.jsonl"
        self.steps = 0
        self.calls = 0    # скільки разів викликали модель
        self.tokens = {}  # {модель: [вхідні, вихідні]}
        self.model_seconds = 0.0
        self.last_event = time.perf_counter()

    # --- запис у трейс -----------------------------------------------------

    def _trace(self, event, **data):
        """Одна подія = один рядок JSON у файлі трейсу. Дані повні, обрізаємо лише на екрані."""
        record = {"time": datetime.now().isoformat(timespec="seconds"), "event": event, **data}
        with open(self.trace_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.last_event = time.perf_counter()

    # --- блоки на екрані ---------------------------------------------------

    def title(self, text):
        """Заголовок демо."""
        self.console.print()
        self.console.rule(Text(f" {text} ", style="bold white on blue"), style="bright_blue")
        self._trace("title", text=text)

    def think(self, step, attempt=None):
        """Модель думає: перед кожним викликом моделі."""
        self.steps = max(self.steps, step)
        where = f"Крок {step}" + (f" · спроба {attempt}" if attempt else "")
        self.console.print()
        self.console.print(Text(f"{LABELS['think']} {where} — Модель думає…", style="bold bright_cyan"))
        self._trace("think", step=step, attempt=attempt)

    def action(self, name, args):
        """Модель обрала інструмент. Довгі аргументи (SQL) переносимо, а не обрізаємо."""
        header = Text(f"{LABELS['action']} Обирає дію: ", style="bold bright_yellow")
        call = format_call(name, args)
        if len(call) <= WIDTH - 16:
            self.console.print(header.append(call, style="bright_white"))
        else:
            self.console.print(header.append(f"{name}(", style="bright_white"))
            for key, value in args.items():
                if not isinstance(value, str):
                    value = json.dumps(value, ensure_ascii=False)
                # Багаторядковий SQL друкуємо рядок за рядком, як у редакторі
                self.console.print(Text(f"     {key}=", style="bright_white"))
                for line in value.strip().splitlines():
                    wrapped = textwrap.fill(line, width=WIDTH - 2, initial_indent="       ",
                                            subsequent_indent="         ")
                    self.console.print(Text(wrapped, style="bright_white"))
            self.console.print(Text("   )", style="bright_white"))
        self._trace("action", name=name, args=args)

    def result(self, text):
        """Код виконав інструмент, модель бачить результат (на екрані — кілька рядків)."""
        self.console.print(Text(f"{LABELS['result']} Код виконує → Бачить результат:", style="bold bright_green"))
        lines = str(text).splitlines() or [""]
        for line in lines[:RESULT_LINES]:
            self.console.print(Text("   " + shorten(line), style="green"))
        if len(lines) > RESULT_LINES:
            self.console.print(Text(f"   … ще рядків: {len(lines) - RESULT_LINES}", style="dim green"))
        self._trace("result", text=str(text))

    def error(self, text):
        """Помилка: червоним, щоб було видно з останнього ряду."""
        self.console.print(Text(f"{LABELS['error']} Помилка: ", style="bold bright_red").append(
            shorten(str(text), WIDTH - 12), style="red"))
        self._trace("error", text=str(text))

    def answer(self, text):
        """Фінальна відповідь агента в рамці."""
        self.console.print()
        self.console.print(Panel(Text(text, style="bold bright_white"), title="[bold] Відповідь [/]",
                                 title_align="left", border_style="bold bright_green", padding=(0, 1)))
        self._trace("answer", text=text)

    def note(self, text):
        """Коментар ведучого: пауза, висновок."""
        self.console.print()
        self.console.print(Text(f"{LABELS['note']} {text}", style="bold bright_magenta"))
        self._trace("note", text=text)

    # --- токени, час і вартість --------------------------------------------

    def usage(self, resp):
        """Додає токени з resp.usage і час виклику до загального рахунку.

        Тривалість виклику = час від попередньої події логера: у демо перед викликом моделі
        завжди стоїть think/title/action, тож таймери в коді демо не потрібні.
        """
        seconds = round(time.perf_counter() - self.last_event, 2)
        tokens_in = resp.usage.input_tokens if resp.usage else 0
        tokens_out = resp.usage.output_tokens if resp.usage else 0
        self.calls += 1
        self.model_seconds += seconds
        counts = self.tokens.setdefault(resp.model, [0, 0])
        counts[0] += tokens_in
        counts[1] += tokens_out
        self._trace("usage", model=resp.model, seconds=seconds,
                    input_tokens=tokens_in, output_tokens=tokens_out)

    def cost(self):
        """Вартість у $ за PRICES або None, якщо ціна якоїсь моделі невідома."""
        total = 0.0
        for model, (tokens_in, tokens_out) in self.tokens.items():
            # API повертає назву зі знімком, напр. gpt-6-luna-2026-09-22, тому шукаємо за початком
            price = next((p for name, p in PRICES.items() if model.startswith(name)), None)
            if price is None:
                return None
            total += tokens_in / 1_000_000 * price[0] + tokens_out / 1_000_000 * price[1]
        return total

    def summary(self):
        """Підсумок: кроки, виклики, час моделі, токени, вартість."""
        tokens_in = sum(t[0] for t in self.tokens.values())
        tokens_out = sum(t[1] for t in self.tokens.values())
        cost = self.cost()
        cost_text = "ціна невідома" if cost is None else f"${cost:.4f}"
        steps_text = f"кроків: {self.steps}   " if self.steps else ""

        self.console.print()
        self.console.rule(style="bright_blue")
        line = Text("Підсумок  ", style="bold bright_white")
        line.append(f"{steps_text}викликів моделі: {self.calls}   час моделі: {self.model_seconds:.1f} с",
                    style="bright_white")
        self.console.print(line)
        line = Text(f"          токени: вхід {tokens_in:,} / вихід {tokens_out:,}   ".replace(",", " "),
                    style="bright_white")
        line.append(f"вартість: {cost_text}", style="bold bright_yellow")
        self.console.print(line)
        self.console.print(Text(f"Трейс: {self.trace_path.relative_to(PROJECT_ROOT)}", style="dim"))
        self._trace("summary", steps=self.steps, calls=self.calls,
                    model_seconds=round(self.model_seconds, 2),
                    input_tokens=tokens_in, output_tokens=tokens_out, cost_usd=cost)


# ---------------------------------------------------------------------------
# Приклад усіх блоків без викликів API: python -m common.log
# ---------------------------------------------------------------------------

class FakeUsage:
    input_tokens = 1_250
    output_tokens = 180


class FakeResponse:
    model = "gpt-6-luna-2026-09-22"
    usage = FakeUsage()


if __name__ == "__main__":
    log = Logger("log_preview")
    log.title("Демо 1: SQL-агент з reflection")

    log.think(step=1, attempt=1)
    time.sleep(0.4)  # імітуємо виклик моделі
    log.usage(FakeResponse())
    log.action("query_db", {"sql": "SELECT campaign, SUM(amount) FROM donations "
                                   "WHERE strftime('%m', date) = '08' GROUP BY campaign"})
    log.result("[]")
    log.error("Сенсор: порожній результат. strftime() не розуміє дати у форматі DD.MM.YYYY")

    log.think(step=1, attempt=2)
    time.sleep(0.4)
    log.usage(FakeResponse())
    log.action("query_db", {"sql": "SELECT d.campaign, SUM(d.amount * r.rate_to_uah) AS uah "
                                   "FROM donations d JOIN exchange_rates r USING (currency) "
                                   "WHERE d.date LIKE '%.08.2026' GROUP BY d.campaign ORDER BY uah DESC"})
    log.result("campaign | uah\n" + "\n".join(f"{i:>2}. рядок довгого результату" for i in range(1, 9)))
    log.result("Дрони для бригади | 1073450.0\nМедикаменти | 491250.0\n"
               "Евакуаційне авто | 483080.0\nГенератори | 445950.0")

    log.answer("У серпні 2026 найбільше зібрала кампанія «Дрони для бригади» — 1 073 450 грн "
               "у гривневому еквіваленті.")
    log.note("Знати — не те саме, що діяти")
    log.summary()
