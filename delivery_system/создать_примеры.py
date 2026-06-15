"""Очистить базу и добавить демонстрационные данные одним кликом.

Просто запусти этот файл в PyCharm: правый клик -> Run 'создать_примеры'.
Скрипт полностью очищает базу, сбрасывает нумерацию id с единицы и
добавляет примеры. После этого открой main_gui.py — увидишь заказы.

Бэкенд по умолчанию — SQLite. Чтобы заполнить базу TinyDB, задай
переменную окружения DELIVERY_BACKEND=tinydb перед запуском.
"""
import os

from database import get_database
from main_cli import cmd_seed


def main():
    backend = os.environ.get("DELIVERY_BACKEND", "sqlite")
    db = get_database(backend)
    try:
        db.clear_all()               # чистая база, id с единицы
        cmd_seed(db, None)           # добавляет несколько клиентов и заказов
        print("\nГотово! База очищена, id начинаются с 1.")
        print("Теперь запусти main_gui.py — увидишь примеры заказов.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
