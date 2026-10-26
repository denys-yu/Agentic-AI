"""Підключення до бази пожертв."""

import sqlite3

from common.config import DB_PATH


def connect_ro():
    """Відкриває базу ТІЛЬКИ на читання: агент не зможе нічого змінити."""
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True)
