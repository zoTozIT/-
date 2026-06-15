"""Тесты моделей предметной области."""
import pytest

from models import VALID_STATUSES, Customer, Order, OrderItem


def test_order_item_subtotal():
    item = OrderItem("Пицца", 2, 750)
    assert item.subtotal == 1500.0


def test_order_item_validate_ok():
    OrderItem("Кола", 1, 120).validate()  # не должно бросать исключение


@pytest.mark.parametrize("qty,price", [(0, 100), (-1, 100), (1, -5)])
def test_order_item_validate_bad(qty, price):
    with pytest.raises(ValueError):
        OrderItem("Товар", qty, price).validate()


def test_customer_validate_empty_name():
    with pytest.raises(ValueError):
        Customer(name="   ").validate()


def test_order_calculate_total():
    order = Order(
        customer_id=1,
        order_date="2025-04-20",
        items=[OrderItem("Пицца", 2, 750), OrderItem("Кола", 3, 100)],
    )
    assert order.calculate_total() == 1800.0
    assert order.total == 1800.0


def test_order_invalid_status():
    order = Order(customer_id=1, order_date="2025-04-20", status="готов")
    with pytest.raises(ValueError):
        order.validate()


def test_order_valid_statuses():
    for status in VALID_STATUSES:
        order = Order(customer_id=1, order_date="2025-04-20", status=status,
                      items=[OrderItem("X", 1, 10)])
        order.validate()  # не бросает


def test_order_roundtrip_dict():
    order = Order(
        customer_id=5,
        order_date="2025-01-01",
        status="новый",
        items=[OrderItem("Товар", 2, 50)],
    )
    order.calculate_total()
    restored = Order.from_dict(order.to_dict())
    assert restored.customer_id == 5
    assert restored.total == 100.0
    assert restored.items[0].product_name == "Товар"


def test_customer_roundtrip_dict():
    c = Customer(id=1, name="Иван", phone="+7", address="ул. Мира")
    restored = Customer.from_dict(c.to_dict())
    assert restored.name == "Иван"
    assert restored.phone == "+7"
