"""Слой работы с базой данных на TinyDB (альтернатива SQLite).

TinyDatabase предоставляет тот же публичный интерфейс, что и
database.Database, поэтому CLI и GUI работают с любым бэкендом без изменений.

Внешние ключи и JOIN в TinyDB отсутствуют, поэтому связи между
клиентами и заказами и агрегаты для отчётов эмулируются программно
(фильтрацией и обходом списков). Позиции заказа хранятся внутри
документа заказа (поле items), как в схеме TinyDB из ТЗ.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import List, Optional

from tinydb import Query, TinyDB
from tinydb.storages import MemoryStorage

from logger_config import setup_logger
from models import VALID_STATUSES, Customer, Order, OrderItem

logger = setup_logger("delivery.db")

DEFAULT_TINYDB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "tinydb.json"
)


class TinyDatabase:
    """Обёртка над TinyDB с интерфейсом, совместимым с Database (SQLite)."""

    backend = "tinydb"

    def __init__(self, db_path: str = DEFAULT_TINYDB_PATH):
        self.db_path = db_path
        if db_path == ":memory:":
            self.db = TinyDB(storage=MemoryStorage)
        else:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            self.db = TinyDB(
                db_path, create_dirs=True, encoding="utf-8",
                ensure_ascii=False, indent=2,
            )
        self.customers_t = self.db.table("customers")
        self.orders_t = self.db.table("orders")
        self.meta_t = self.db.table("_meta")  # счётчики автоинкремента
        logger.info("Подключение к БД (TinyDB): %s", db_path)

    # ------------------------------------------------------------------ #
    # Служебное
    # ------------------------------------------------------------------ #
    def _next_id(self, name: str) -> int:
        """Выдать следующий id (эмуляция AUTOINCREMENT, без переиспользования)."""
        Meta = Query()
        rec = self.meta_t.get(Meta.name == name)
        next_id = rec["next_id"] if rec else 1
        self.meta_t.upsert({"name": name, "next_id": next_id + 1}, Meta.name == name)
        return next_id

    def clear_all(self) -> None:
        """Полностью очистить базу и сбросить счётчики id (с 1)."""
        self.customers_t.truncate()
        self.orders_t.truncate()
        self.meta_t.truncate()
        logger.info("База очищена, счётчики id сброшены")

    def close(self) -> None:
        self.db.close()
        logger.info("Соединение с БД закрыто")

    def __enter__(self) -> "TinyDatabase":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # CRUD: клиенты
    # ------------------------------------------------------------------ #
    def add_customer(self, customer: Customer) -> int:
        customer.validate()
        customer.id = self._next_id("customers")
        self.customers_t.insert({
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "address": customer.address,
        })
        logger.info("Добавлен клиент id=%s (%s)", customer.id, customer.name)
        return customer.id

    def get_customer(self, customer_id: int) -> Optional[Customer]:
        rec = self.customers_t.get(Query().id == customer_id)
        return self._dict_to_customer(rec) if rec else None

    def get_customers(self) -> List[Customer]:
        rows = sorted(self.customers_t.all(), key=lambda r: r.get("name", ""))
        return [self._dict_to_customer(r) for r in rows]

    def update_customer(self, customer: Customer) -> None:
        if customer.id is None:
            raise ValueError("Для обновления нужен id клиента")
        customer.validate()
        self.customers_t.update(
            {"name": customer.name, "phone": customer.phone,
             "address": customer.address},
            Query().id == customer.id,
        )
        logger.info("Обновлён клиент id=%s", customer.id)

    def delete_customer(self, customer_id: int) -> None:
        count = self.orders_t.count(Query().customer_id == customer_id)
        if count > 0:
            logger.warning(
                "Попытка удалить клиента id=%s с %s заказами — отклонено",
                customer_id, count,
            )
            raise ValueError(
                "Нельзя удалить клиента: у него есть заказы (%d шт.)" % count
            )
        self.customers_t.remove(Query().id == customer_id)
        logger.info("Удалён клиент id=%s", customer_id)

    # ------------------------------------------------------------------ #
    # CRUD: заказы
    # ------------------------------------------------------------------ #
    def add_order(self, order: Order) -> int:
        order.calculate_total()
        order.validate()
        if self.get_customer(order.customer_id) is None:
            raise ValueError(f"Клиент id={order.customer_id} не найден")
        order.id = self._next_id("orders")
        self.orders_t.insert(self._order_to_dict(order))
        logger.info(
            "Добавлен заказ id=%s (клиент=%s, сумма=%.2f)",
            order.id, order.customer_id, order.total,
        )
        return order.id

    def get_order(self, order_id: int) -> Optional[Order]:
        rec = self.orders_t.get(Query().id == order_id)
        return self._dict_to_order(rec) if rec else None

    def get_orders(
        self,
        status: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> List[Order]:
        rows = self.orders_t.all()
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if date_from:
            rows = [r for r in rows if r.get("order_date", "") >= date_from]
        if date_to:
            rows = [r for r in rows if r.get("order_date", "") <= date_to]
        # Сортировка как в SQLite: по дате убыв., затем по id убыв.
        rows.sort(key=lambda r: (r.get("order_date", ""), r.get("id", 0)), reverse=True)
        return [self._dict_to_order(r) for r in rows]

    def update_order(self, order: Order) -> None:
        if order.id is None:
            raise ValueError("Для обновления нужен id заказа")
        order.calculate_total()
        order.validate()
        self.orders_t.update(self._order_to_dict(order), Query().id == order.id)
        logger.info("Обновлён заказ id=%s", order.id)

    def update_order_status(self, order_id: int, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"Недопустимый статус: {status}")
        self.orders_t.update({"status": status}, Query().id == order_id)
        logger.info("Заказ id=%s — статус изменён на '%s'", order_id, status)

    def delete_order(self, order_id: int) -> None:
        self.orders_t.remove(Query().id == order_id)
        logger.info("Удалён заказ id=%s", order_id)

    # ------------------------------------------------------------------ #
    # Отчёты и аналитика (эмуляция агрегатов программно)
    # ------------------------------------------------------------------ #
    def count_by_status(self) -> dict:
        result = {status: 0 for status in VALID_STATUSES}
        for r in self.orders_t.all():
            st = r.get("status")
            if st in result:
                result[st] += 1
        return result

    def top_customers(self, limit: int = 3) -> List[dict]:
        sums: dict = {}
        for r in self.orders_t.all():
            cid = r.get("customer_id")
            entry = sums.setdefault(cid, {"total_sum": 0.0, "orders_count": 0})
            entry["total_sum"] += r.get("total", 0.0)
            entry["orders_count"] += 1

        result = []
        for cid, agg in sums.items():
            customer = self.get_customer(cid)
            result.append({
                "id": cid,
                "name": customer.name if customer else f"id={cid}",
                "total_sum": round(agg["total_sum"], 2),
                "orders_count": agg["orders_count"],
            })
        result.sort(key=lambda x: x["total_sum"], reverse=True)
        return result[:limit]

    def revenue_for_period(self, period: str = "month") -> dict:
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
        revenue = 0.0
        count = 0
        for r in self.orders_t.all():
            od = r.get("order_date", "")
            if start_str <= od <= end_str and r.get("status") != "отменён":
                revenue += r.get("total", 0.0)
                count += 1
        return {
            "period": period,
            "date_from": start_str,
            "date_to": end_str,
            "revenue": round(revenue, 2),
            "orders_count": count,
        }

    # ------------------------------------------------------------------ #
    # Преобразование словарь <-> модель
    # ------------------------------------------------------------------ #
    @staticmethod
    def _dict_to_customer(rec: dict) -> Customer:
        return Customer(
            id=rec["id"],
            name=rec["name"],
            phone=rec.get("phone", "") or "",
            address=rec.get("address", "") or "",
        )

    @staticmethod
    def _order_to_dict(order: Order) -> dict:
        return {
            "id": order.id,
            "customer_id": order.customer_id,
            "order_date": order.order_date,
            "status": order.status,
            "total": order.total,
            "items": [
                {"product_name": i.product_name, "quantity": i.quantity,
                 "price": i.price}
                for i in order.items
            ],
        }

    @staticmethod
    def _dict_to_order(rec: dict) -> Order:
        items = [
            OrderItem(
                product_name=i.get("product_name", ""),
                quantity=i.get("quantity", 0),
                price=i.get("price", 0.0),
                order_id=rec.get("id"),
            )
            for i in rec.get("items", [])
        ]
        return Order(
            id=rec["id"],
            customer_id=rec["customer_id"],
            order_date=rec["order_date"],
            status=rec["status"],
            total=rec.get("total", 0.0),
            items=items,
        )
