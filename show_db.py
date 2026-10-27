# show_db.py — друкує кожну таблицю бази: кількість рядків і перші 10 записів
from common.db import connect_ro

conn = connect_ro()
tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]

for table in tables:
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"\n=== {table} ({count} рядків) ===")
    cursor = conn.execute(f"SELECT * FROM {table} LIMIT 10")
    print(" | ".join(col[0] for col in cursor.description))
    for row in cursor:
        print(" | ".join(str(value) for value in row))