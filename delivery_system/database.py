"""Слой работы с базой данных (SQLite).

Класс Database инкапсулирует подключение к SQLite, создание схемы,
CRUD-операции для клиентов и заказов, а также отчёты/аналитику.

Внешние ключи включены (PRAGMA foreign_keys = ON), удаление клиента
с существующими заказами запрещено (ON DELETE RESTRICT).
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from typing import List, Optional

from logger_config import setup_logger
from models import VALID_STATUSES, Customer, Order, OrderItem

logger = setup_logger("delivery.db")

# Путь к БД по умолчанию: data/delivery.db рядом с этим модулем
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "delivery.db"
)


class Database:
    """Обёртка над SQLite-базой системы доставки."""

    backend = "sqlite"

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        # Для in-memory БД (":memory:") каталог создавать не нужно
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()
        logger.info("Подключение к БД: %s", db_path)

    # ------------------------------------------------------------------ #
    # Инициализация / завершение
    # ------------------------------------------------------------------ #
    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                name    TEXT NOT NULL,
                phone   TEXT,
                address TEXT
            );

            CREATE TABLE IF NOT EXISTS orders (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
                order_date  TEXT NOT NULL,
                status      TEXT CHECK(status IN ('новый','в доставке','выполнен','отменён')),
                total       REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_name TEXT,
                quantity     INTEGER,
                price        REAL
            );
            """
        )
        self.conn.commit()

    def clear_all(self) -> None:
        """Полностью очистить базу и сбросить автоинкремент id (с 1)."""
        self.conn.execute("DELETE FROM order_items")
        self.conn.execute("DELETE FROM orders")
        self.conn.execute("DELETE FROM customers")
        # sqlite_sequence хранит счётчики AUTOINCREMENT; чистим, чтобы id шли с 1
        self.conn.execute(
            "DELETE FROM sqlite_sequence "
            "WHERE name IN ('customers', 'orders', 'order_items')"
        )
        self.conn.commit()
        logger.info("База очищена, счётчики id сброшены")

    def close(self) -> None:
        self.conn.close()
        logger.info("Соединение с БД закрыто")

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # CRUD: клиенты
    # ------------------------------------------------------------------ #
    def add_customer(self, customer: Customer) -> int:
        customer.validate()
        cur = self.conn.execute(
            "INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)",
            (customer.name, customer.phone, customer.address),
        )
        self.conn.commit()
        customer.id = cur.lastrowid
        logger.info("Добавлен клиент id=%s (%s)", customer.id, customer.name)
        return customer.id

    def get_customer(self, customer_id: int) -> Optional[Customer]:
        row = self.conn.execute(
            "SELECT * FROM customers WHERE id = ?", (customer_id,)
        ).fetchone()
        return self._row_to_customer(row) if row else None

    def get_customers(self) -> List[Customer]:
        rows = self.conn.execute("SELECT * FROM customers ORDER BY name").fetchall()
        return [self._row_to_customer(r) for r in rows]

    def update_customer(self, customer: Customer) -> None:
        if customer.id is None:
            raise ValueError("Для обновления нужен id клиента")
        customer.validate()
        self.conn.execute(
            "UPDATE customers SET name = ?, phone = ?, address = ? WHERE id = ?",
            (customer.name, customer.phone, customer.address, customer.id),
        )
        self.conn.commit()
        logger.info("Обновлён клиент id=%s", customer.id)

    def delete_customer(self, customer_id: int) -> None:
        """Удалить клиента. Запрещено, если у него есть заказы."""
        count = self.conn.execute(
            "SELECT COUNT(*) FROM orders WHERE customer_id = ?", (customer_id,)
        ).fetchone()[0]
        if count > 0:
            logger.warning(
                "Попытка удалить клиента id=%s с %s заказами — отклонено",
                customer_id, count,
            )
            raise ValueError(
                "Нельзя удалить клиента: у него есть заказы (%d шт.)" % count
            )
        self.conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        self.conn.commit()
        logger.info("Удалён клиент id=%s", customer_id)

    # ------------------------------------------------------------------ #
    # CRUD: заказы
    # ------------------------------------------------------------------ #
    def add_order(self, order: Order) -> int:
        order.calculate_total()
        order.validate()
        if self.get_customer(order.customer_id) is None:
            raise ValueError(f"Клиент id={order.customer_id} не найден")

        cur = self.conn.execute(
            "INSERT INTO orders (customer_id, order_date, status, total) "
            "VALUES (?, ?, ?, ?)",
            (order.customer_id, order.order_date, order.status, order.total),
        )
        order.id = cur.lastrowid
        self._insert_items(order.id, order.items)
        self.conn.commit()
        logger.info(
            "Добавлен заказ id=%s (клиент=%s, сумма=%.2f)",
            order.id, order.customer_id, order.total,
        )
        return order.id

    def get_order(self, order_id: int) -> Optional[Order]:
        row = self.conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()
        if not row:
            return None
        return self._row_to_order(row)

    def get_orders(
        self,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Order]:
        """Список заказов с фильтрацией по статусу и диапазону дат."""
        query = "SELECT * FROM orders WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if date_from:
            query += " AND order_date >= ?"
            params.append(date_from)
        if date_to:
            query += " AND order_date <= ?"
            params.append(date_to)
        query += " ORDER BY order_date DESC, id DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_order(r) for r in rows]

    def update_order(self, order: Order) -> None:
        if order.id is None:
            raise ValueError("Для обновления нужен id заказа")
        order.calculate_total()
        order.validate()
        self.conn.execute(
            "UPDATE orders SET customer_id = ?, order_date = ?, status = ?, "
            "total = ? WHERE id = ?",
            (order.customer_id, order.order_date, order.status, order.total, order.id),
        )
        # Перезаписываем позиции заказа
        self.conn.execute("DELETE FROM order_items WHERE order_id = ?", (order.id,))
        self._insert_items(order.id, order.items)
        self.conn.commit()
        logger.info("Обновлён заказ id=%s", order.id)

    def update_order_status(self, order_id: int, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Недопустимый статус: {status}")
        self.conn.execute(
            "UPDATE orders SET status = ? WHERE id = ?", (status, order_id)
        )
        self.conn.commit()
        logger.info("Заказ id=%s — статус изменён на '%s'", order_id, status)

    def delete_order(self, order_id: int) -> None:
        self.conn.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
        self.conn.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        self.conn.commit()
        logger.info("Удалён заказ id=%s", order_id)

    # ------------------------------------------------------------------ #
    # Отчёты и аналитика
    # ------------------------------------------------------------------ #
    def count_by_status(self) -> dict:
        """Количество заказов по каждому статусу."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM orders GROUP BY status"
        ).fetchall()
        result = {status: 0 for status in VALID_STATUSES}
        for r in rows:
            result[r["status"]] = r["cnt"]
        return result

    def top_customers(self, limit: int = 3) -> List[dict]:
        """Топ клиентов по суммарной стоимости заказов."""
        rows = self.conn.execute(
            """
            SELECT c.id, c.name, SUM(o.total) AS total_sum, COUNT(o.id) AS orders_count
            FROM customers c
            JOIN orders o ON o.customer_id = c.id
            GROUP BY c.id, c.name
            ORDER BY total_sum DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "total_sum": round(r["total_sum"] or 0, 2),
                "orders_count": r["orders_count"],
            }
            for r in rows
        ]

    def revenue_for_period(self, period: str = "month") -> dict:
        """Общая выручка за период: 'day', 'week' или 'month'.

        Учитываются только выполненные и доставляемые заказы
        (отменённые в выручку не входят).
        """
        period = period.lower()
        today = datetime.now().date()
        if period == "day":
            start = today
        elif period == "week":
            start = today - timedelta(days=7)
        elif period == "month":
            start = today - timedelta(days=30)
        else:
            raise ValueError("period должен быть day/week/month")

        start_str = start.isoformat()
        end_str = today.isoformat()
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(total), 0) AS revenue, COUNT(*) AS cnt
            FROM orders
            WHERE order_date >= ? AND order_date <= ?
              AND status != 'отменён'
            """,
            (start_str, end_str),
        ).fetchone()
        return {
            "period": period,
            "date_from": start_str,
            "date_to": end_str,
            "revenue": round(row["revenue"], 2),
            "orders_count": row["cnt"],
        }

    # ------------------------------------------------------------------ #
    # Вспомогательные методы
    # ------------------------------------------------------------------ #
    def _insert_items(self, order_id: int, items: List[OrderItem]) -> None:
        for item in items:
            self.conn.execute(
                "INSERT INTO order_items (order_id, product_name, quantity, price) "
                "VALUES (?, ?, ?, ?)",
                (order_id, item.product_name, item.quantity, item.price),
            )

    def _get_items(self, order_id: int) -> List[OrderItem]:
        rows = self.conn.execute(
            "SELECT * FROM order_items WHERE order_id = ?", (order_id,)
        ).fetchall()
        return [
            OrderItem(
                id=r["id"],
                order_id=r["order_id"],
                product_name=r["product_name"],
                quantity=r["quantity"],
                price=r["price"],
            )
            for r in rows
        ]

    @staticmethod
    def _row_to_customer(row: sqlite3.Row) -> Customer:
        return Customer(
            id=row["id"],
            name=row["name"],
            phone=row["phone"] or "",
            address=row["address"] or "",
        )

    def _row_to_order(self, row: sqlite3.Row) -> Order:
        return Order(
            id=row["id"],
            customer_id=row["customer_id"],
            order_date=row["order_date"],
            status=row["status"],
            total=row["total"],
            items=self._get_items(row["id"]),
        )


# ---------------------------------------------------------------------- #
# Фабрика: выбор бэкенда хранилища (SQLite или TinyDB)
# ---------------------------------------------------------------------- #
def get_database(backend: str = "sqlite", path: str = None):
    """Вернуть объект БД нужного типа с единым интерфейсом.

    backend : 'sqlite' (по умолчанию) или 'tinydb'.
    path    : путь к файлу БД. Значение ':memory:' создаёт БД в памяти
              (удобно для тестов). Если None — используется путь по умолчанию.
    """
    backend = (backend or "sqlite").lower()
    if backend == "sqlite":
        return Database(path or DEFAULT_DB_PATH)
    if backend == "tinydb":
        # Импорт здесь, чтобы tinydb требовался только при реальном использовании
        from database_tinydb import DEFAULT_TINYDB_PATH, TinyDatabase
        return TinyDatabase(path or DEFAULT_TINYDB_PATH)
    raise ValueError(f"Неизвестный бэкенд БД: {backend} (нужно sqlite или tinydb)")
