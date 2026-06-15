"""Тесты слоя базы данных."""
from datetime import date, timedelta

import pytest

from models import Customer, Order, OrderItem


def _make_customer(db, name="Иван"):
    return db.add_customer(Customer(name=name, phone="+7", address="адрес"))


def _make_order(db, customer_id, status="новый", days_ago=0, items=None):
    order_date = (date.today() - timedelta(days=days_ago)).isoformat()
    items = items or [OrderItem("Товар", 2, 500)]
    return db.add_order(Order(customer_id=customer_id, order_date=order_date,
                              status=status, items=items))


# ----------------------- клиенты ----------------------- #
def test_add_and_get_customer(db):
    cid = _make_customer(db, "Мария")
    customer = db.get_customer(cid)
    assert customer is not None
    assert customer.name == "Мария"


def test_update_customer(db):
    cid = _make_customer(db)
    c = db.get_customer(cid)
    c.name = "Пётр"
    db.update_customer(c)
    assert db.get_customer(cid).name == "Пётр"


def test_delete_customer_without_orders(db):
    cid = _make_customer(db)
    db.delete_customer(cid)
    assert db.get_customer(cid) is None


def test_delete_customer_with_orders_forbidden(db):
    cid = _make_customer(db)
    _make_order(db, cid)
    with pytest.raises(ValueError):
        db.delete_customer(cid)
    # клиент остаётся в базе
    assert db.get_customer(cid) is not None


# ----------------------- заказы ----------------------- #
def test_add_order_calculates_total(db):
    cid = _make_customer(db)
    oid = _make_order(db, cid, items=[OrderItem("A", 2, 750), OrderItem("B", 1, 100)])
    order = db.get_order(oid)
    assert order.total == 1600.0
    assert len(order.items) == 2


def test_add_order_unknown_customer(db):
    with pytest.raises(ValueError):
        _make_order(db, customer_id=999)


def test_update_order_status(db):
    cid = _make_customer(db)
    oid = _make_order(db, cid)
    db.update_order_status(oid, "выполнен")
    assert db.get_order(oid).status == "выполнен"


def test_update_order_status_invalid(db):
    cid = _make_customer(db)
    oid = _make_order(db, cid)
    with pytest.raises(ValueError):
        db.update_order_status(oid, "несуществующий")


def test_update_order_replaces_items(db):
    cid = _make_customer(db)
    oid = _make_order(db, cid)
    order = db.get_order(oid)
    order.items = [OrderItem("Новый", 1, 999)]
    db.update_order(order)
    updated = db.get_order(oid)
    assert len(updated.items) == 1
    assert updated.total == 999.0


def test_delete_order(db):
    cid = _make_customer(db)
    oid = _make_order(db, cid)
    db.delete_order(oid)
    assert db.get_order(oid) is None


def test_filter_orders_by_status(db):
    cid = _make_customer(db)
    _make_order(db, cid, status="новый")
    _make_order(db, cid, status="выполнен")
    assert len(db.get_orders(status="новый")) == 1
    assert len(db.get_orders(status="выполнен")) == 1
    assert len(db.get_orders()) == 2


def test_filter_orders_by_date(db):
    cid = _make_customer(db)
    _make_order(db, cid, days_ago=0)
    _make_order(db, cid, days_ago=40)
    recent = (date.today() - timedelta(days=10)).isoformat()
    result = db.get_orders(date_from=recent)
    assert len(result) == 1


# ----------------------- отчёты ----------------------- #
def test_count_by_status(db):
    cid = _make_customer(db)
    _make_order(db, cid, status="новый")
    _make_order(db, cid, status="новый")
    _make_order(db, cid, status="отменён")
    counts = db.count_by_status()
    assert counts["новый"] == 2
    assert counts["отменён"] == 1
    assert counts["выполнен"] == 0


def test_top_customers(db):
    c1 = _make_customer(db, "Богатый")
    c2 = _make_customer(db, "Средний")
    _make_order(db, c1, items=[OrderItem("X", 10, 1000)])  # 10000
    _make_order(db, c2, items=[OrderItem("Y", 1, 500)])    # 500
    top = db.top_customers(3)
    assert top[0]["name"] == "Богатый"
    assert top[0]["total_sum"] == 10000.0
    assert top[1]["name"] == "Средний"


def test_revenue_for_period_excludes_cancelled(db):
    cid = _make_customer(db)
    _make_order(db, cid, status="выполнен", days_ago=1,
                items=[OrderItem("X", 1, 1000)])
    _make_order(db, cid, status="отменён", days_ago=1,
                items=[OrderItem("Y", 1, 5000)])
    rev = db.revenue_for_period("week")
    assert rev["revenue"] == 1000.0
    assert rev["orders_count"] == 1


def test_revenue_period_day(db):
    cid = _make_customer(db)
    _make_order(db, cid, status="новый", days_ago=0,
                items=[OrderItem("X", 1, 300)])
    _make_order(db, cid, status="новый", days_ago=5,
                items=[OrderItem("Y", 1, 700)])
    rev = db.revenue_for_period("day")
    assert rev["revenue"] == 300.0


def test_revenue_invalid_period(db):
    with pytest.raises(ValueError):
        db.revenue_for_period("year")


# ----------------------- очистка базы и сброс id ----------------------- #
def test_clear_all_empties_and_resets_ids(db):
    cid = _make_customer(db)
    _make_order(db, cid)
    db.clear_all()
    assert db.get_customers() == []
    assert db.get_orders() == []
    # После очистки нумерация id начинается заново с 1
    new_id = _make_customer(db, "Первый")
    assert new_id == 1


# ----------------------- фабрика бэкендов ----------------------- #
def test_get_database_invalid_backend():
    from database import get_database
    with pytest.raises(ValueError):
        get_database("mongodb")
