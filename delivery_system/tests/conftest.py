"""Общие фикстуры для тестов и настройка путей импорта.

Добавляем корень проекта (delivery_system/) в sys.path, чтобы тесты
могли импортировать модули database, models, data_export напрямую.
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database import get_database  # noqa: E402


@pytest.fixture(params=["sqlite", "tinydb"])
def db(request):
    """Свежая БД в памяти для каждого теста — по очереди оба бэкенда.

    Благодаря параметризации все тесты, использующие фикстуру db,
    автоматически прогоняются и на SQLite, и на TinyDB.
    """
    database = get_database(request.param, ":memory:")
    yield database
    database.close()
