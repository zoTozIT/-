"""Тесты экспорта/импорта в JSON и XML."""
import pytest

from data_export import export_data, import_data
from database import get_database
from models import Customer, Order, OrderItem


def _populate(db):
    c1 = db.add_customer(Customer(name="Иван", phone="+71", address="ул. 1"))
    c2 = db.add_customer(Customer(name="Мария", phone="+72", address="ул. 2"))
    db.add_order(Order(customer_id=c1, order_date="2025-04-20", status="новый",
                       items=[OrderItem("Пицца", 2, 750)]))
    db.add_order(Order(customer_id=c2, order_date="2025-04-21", status="выполнен",
                       items=[OrderItem("Суши", 1, 1990), OrderItem("Кола", 2, 100)]))
    return db


@pytest.mark.parametrize("ext", [".json", ".xml"])
def test_export_creates_file(db, tmp_path, ext):
    _populate(db)
    target = tmp_path / f"orders{ext}"
    export_data(db, str(target))
    assert target.exists()
    assert target.stat().st_size > 0


@pytest.mark.parametrize("ext", [".json", ".xml"])
def test_export_import_roundtrip(db, tmp_path, ext):
    _populate(db)
    target = tmp_path / f"orders{ext}"
    export_data(db, str(target))

    # Импортируем в чистую БД
    new_db = get_database(db.backend, ":memory:")
    customers, orders = import_data(new_db, str(target))
    assert customers == 2
    assert orders == 2

    imported_orders = new_db.get_orders()
    assert len(imported_orders) == 2
    totals = sorted(o.total for o in imported_orders)
    assert totals == [1500.0, 2190.0]
    new_db.close()


def test_import_remaps_customer_ids(db, tmp_path):
    """После импорта заказы должны ссылаться на корректных клиентов."""
    _populate(db)
    target = tmp_path / "orders.json"
    export_data(db, str(target))

    new_db = get_database(db.backend, ":memory:")
    import_data(new_db, str(target))
    for order in new_db.get_orders():
        assert new_db.get_customer(order.customer_id) is not None
    new_db.close()


def test_import_unknown_format(db, tmp_path):
    bad = tmp_path / "data.txt"
    bad.write_text("nonsense", encoding="utf-8")
    with pytest.raises(ValueError):
        import_data(db, str(bad))


def test_import_missing_file(db):
    with pytest.raises(FileNotFoundError):
        import_data(db, "no_such_file.json")


def test_import_invalid_status(db, tmp_path):
    target = tmp_path / "bad.json"
    target.write_text(
        '{"customers": [{"id": 1, "name": "X"}], '
        '"orders": [{"id": 1, "customer_id": 1, "order_date": "2025-01-01", '
        '"status": "готово", "total": 10, "items": []}]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        import_data(db, str(target))


def test_import_invalid_json(db, tmp_path):
    target = tmp_path / "broken.json"
    target.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        import_data(db, str(target))
