# Як побудувати AI-агента з нуля: від моделі до робочої системи

git remote -v

Підтримати збір на НРКастом: https://send.monobank.ua/jar/7x1CZfnK3E

## Що потрібно

- Python 3.12
- Ключ OpenAI API: https://platform.openai.com/api-keys

## Встановлення

**Windows (PowerShell):**

```powershell
git clone <посилання на репозиторій>
cd DOU_Live
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Якщо PowerShell не дає активувати середовище, спершу виконайте
`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

**macOS / Linux:**

```bash
git clone <посилання на репозиторій>
cd DOU_Live
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Відкрийте `.env` і вставте свій ключ після `OPENAI_API_KEY=`. Файл `.env` у git не потрапляє.

## Демо

Порядок як на лекції. Усі команди запускайте з кореня проєкту з активованим `.venv`.

| Файл | Що показує | Запуск |
|---|---|---|
| `00_bare_call.py` | Без інструментів модель не знає наших даних: спершу просто питаємо, потім даємо схему бази (між запусками натисніть Enter) | `python 00_bare_call.py` |
| `show_db.py` | Що лежить у базі: кожна таблиця, кількість рядків і перші 10 записів. Ключ не потрібен | `python show_db.py` |
| `01_reflection_sql.py` | SQL-агент з reflection: сенсори перевіряють результат запиту, і модель виправляє свою помилку | `python 01_reflection_sql.py`<br>`python 01_reflection_sql.py --no-reflection`<br>`python 01_reflection_sql.py --self-check`<br>`python 01_reflection_sql.py "Ваше питання"` |
| `02_agent_from_scratch.py` | Агентний цикл з інструментами без фреймворків: модель думає, обирає дію, код виконує, модель бачить результат. Звіт зберігає в `reports/` лише після вашого «y» | `python 02_agent_from_scratch.py`<br>`python 02_agent_from_scratch.py "Ваше питання"`<br>`python 02_agent_from_scratch.py --max-steps 2` |
| `03_multi_agent_sdk.py` | Та сама задача на OpenAI Agents SDK: менеджер, аналітик і автор подяки. В кінці друкується посилання на трейс у дашборді OpenAI | `python 03_multi_agent_sdk.py`<br>`python 03_multi_agent_sdk.py "Ваше питання"` |
| `04_eval.py` | Оцінка Демо 1 на 10 питаннях з еталонними відповідями: скільки агент розв'язує без reflection і з ним | `python 04_eval.py` |

Кожен запуск пише повний лог кроків у `traces/`. Трейс Демо 3 відкривається в дашборді
того акаунта OpenAI, чий ключ у `.env`.

## База даних

`donations.sqlite` — вигадані пожертви благодійного фонду, травень–листопад 2026. Усі дані
вигадані, збіги випадкові. «Сьогодні» в демо — 04.11.2026.

- `donations` — 400 пожертв: дата, кампанія, сума, валюта, тип донора, коментар
- `campaigns` — 5 кампаній: ціль у гривнях, дата старту, статус
- `exchange_rates` — курси USD і EUR до гривні

У даних три навмисні пастки, на яких помиляються агенти:

1. **Дати текстом** у форматі `DD.MM.YYYY`: `strftime()` у SQLite повертає для них NULL.
2. **Змішані валюти** UAH, USD і EUR: якщо додати суми «як є», лідер серпня буде не той, що в гривнях.
3. **Prompt injection** у коментарі одного жовтневого запису.

Базу і `eval_set.json` можна перестворити: `python seed_db.py`.

## Скільки коштує

Орієнтовна вартість одного прогону за нашими тестами:

| Демо | Вартість |
|---|---|
| 00, 01, 02 | менше $0.002 |
| 03 | ~$0.01–0.03 (менеджер працює на дорожчій моделі) |
| 04 | ~$0.005 |

Усі демо разом коштують кілька центів.

## Моделі

Демо використовують дві моделі: швидку `gpt-6-luna` і розумну `gpt-6.1-sol`.

Якщо у вас немає доступу до них, змініть назви в `.env` (`MODEL_FAST`, `MODEL_SMART`).
Значення за замовчуванням і ціни лежать у `common/config.py`. Там же `EFFORT_FAST` і
`EFFORT_SMART`, тобто рівень обдумування. Якщо ваша модель не підтримує `"none"`, поставте `"low"`.

## Структура

```
.
├── 00_bare_call.py           # Демо 0
├── 01_reflection_sql.py      # Демо 1
├── 02_agent_from_scratch.py  # Демо 2
├── 03_multi_agent_sdk.py     # Демо 3
├── 04_eval.py                
├── show_db.py                # подивитися базу
├── seed_db.py                # перестворити базу і eval_set.json
├── common/
│   ├── config.py             # моделі, ціни, дата «сьогодні»
│   ├── db.py                 # підключення до бази лише на читання
│   └── log.py                # логер агентного циклу
├── donations.sqlite          # база пожертв
├── eval_set.json             # питання для Демо 4
├── reports/                  # сюди Демо 2 зберігає звіти
├── requirements.txt
└── .env.example              # зразок .env
```
