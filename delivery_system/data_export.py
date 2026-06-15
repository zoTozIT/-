"""Экспорт и импорт данных в форматах JSON и XML.

Поддерживаются оба формата (бонус ТЗ). Формат определяется по
расширению файла (.json / .xml). Экспортируются клиенты и заказы
вместе с позициями; при импорте выполняется проверка корректности.
"""
from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from typing import Tuple
from xml.dom import minidom

from logger_config import setup_logger
from models import VALID_STATUSES, Customer, Order, OrderItem

logger = setup_logger("delivery.export")


# ---------------------------------------------------------------------- #
# Определение формата
# ---------------------------------------------------------------------- #
def _detect_format(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".json":
        return "json"
    if ext == ".xml":
        return "xml"
    raise ValueError("Неподдерживаемый формат файла (нужно .json или .xml)")


# ---------------------------------------------------------------------- #
# Экспорт
# ---------------------------------------------------------------------- #
def export_data(db, filename: str) -> None:
    """Экспортировать клиентов и заказы из БД в файл (JSON или XML)."""
    fmt = _detect_format(filename)
    customers = db.get_customers()
    orders = db.get_orders()

    directory = os.path.dirname(os.path.abspath(filename))
    os.makedirs(directory, exist_ok=True)

    if fmt == "json":
        _export_json(customers, orders, filename)
    else:
        _export_xml(customers, orders, filename)

    logger.info(
        "Экспорт завершён: %s (клиентов=%d, заказов=%d, формат=%s)",
        filename, len(customers), len(orders), fmt,
    )


def _export_json(customers, orders, filename: str) -> None:
    data = {
        "customers": [c.to_dict() for c in customers],
        "orders": [o.to_dict() for o in orders],
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _export_xml(customers, orders, filename: str) -> None:
    root = ET.Element("delivery")

    customers_el = ET.SubElement(root, "customers")
    for c in customers:
        c_el = ET.SubElement(customers_el, "customer", id=str(c.id))
        ET.SubElement(c_el, "name").text = c.name
        ET.SubElement(c_el, "phone").text = c.phone or ""
        ET.SubElement(c_el, "address").text = c.address or ""

    orders_el = ET.SubElement(root, "orders")
    for o in orders:
        o_el = ET.SubElement(orders_el, "order", id=str(o.id))
        ET.SubElement(o_el, "customer_id").text = str(o.customer_id)
        ET.SubElement(o_el, "order_date").text = o.order_date
        ET.SubElement(o_el, "status").text = o.status
        ET.SubElement(o_el, "total").text = str(o.total)
        items_el = ET.SubElement(o_el, "items")
        for item in o.items:
            i_el = ET.SubElement(items_el, "item")
            ET.SubElement(i_el, "product_name").text = item.product_name
            ET.SubElement(i_el, "quantity").text = str(item.quantity)
            ET.SubElement(i_el, "price").text = str(item.price)

    # Красивый отступ в выводе
    rough = ET.tostring(root, encoding="utf-8")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ", encoding="utf-8")
    with open(filename, "wb") as f:
        f.write(pretty)


# ---------------------------------------------------------------------- #
# Импорт
# ---------------------------------------------------------------------- #
def import_data(db, filename: str) -> Tuple[int, int]:
    """Импортировать клиентов и заказы из файла.

    Возвращает кортеж (число клиентов, число заказов).
    Выполняется проверка корректности: статусы, обязательные поля,
    существование клиента для каждого заказа.
    """
    if not os.path.exists(filename):
        raise FileNotFoundError(f"Файл не найден: {filename}")

    fmt = _detect_format(filename)
    if fmt == "json":
        customers, orders = _parse_json(filename)
    else:
        customers, orders = _parse_xml(filename)

    # Сопоставление старых id клиентов с новыми после вставки
    id_map = {}
    imported_customers = 0
    for c in customers:
        old_id = c.id
        c.id = None
        new_id = db.add_customer(c)
        if old_id is not None:
            id_map[old_id] = new_id
        imported_customers += 1

    imported_orders = 0
    for o in orders:
        if o.status not in VALID_STATUSES:
            raise ValueError(
                f"Некорректный статус заказа при импорте: '{o.status}'"
            )
        # Переназначаем customer_id согласно карте новых id
        if o.customer_id in id_map:
            o.customer_id = id_map[o.customer_id]
        if db.get_customer(o.customer_id) is None:
            raise ValueError(
                f"Заказ ссылается на несуществующего клиента id={o.customer_id}"
            )
        o.id = None
        db.add_order(o)
        imported_orders += 1

    logger.info(
        "Импорт завершён: %s (клиентов=%d, заказов=%d)",
        filename, imported_customers, imported_orders,
    )
    return imported_customers, imported_orders


def _parse_json(filename: str):
    with open(filename, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Некорректный JSON: {e}")

    if not isinstance(data, dict):
        raise ValueError("Ожидался JSON-объект с полями customers/orders")

    customers = [Customer.from_dict(c) for c in data.get("customers", [])]
    orders = [Order.from_dict(o) for o in data.get("orders", [])]
    return customers, orders


def _parse_xml(filename: str):
    try:
        tree = ET.parse(filename)
    except ET.ParseError as e:
        raise ValueError(f"Некорректный XML: {e}")
    root = tree.getroot()

    customers = []
    for c_el in root.findall("./customers/customer"):
        customers.append(
            Customer(
                id=_to_int(c_el.get("id")),
                name=_text(c_el, "name"),
                phone=_text(c_el, "phone"),
                address=_text(c_el, "address"),
            )
        )

    orders = []
    for o_el in root.findall("./orders/order"):
        items = []
        for i_el in o_el.findall("./items/item"):
            items.append(
                OrderItem(
                    product_name=_text(i_el, "product_name"),
                    quantity=_to_int(_text(i_el, "quantity")) or 0,
                    price=_to_float(_text(i_el, "price")),
                )
            )
        order = Order(
            id=_to_int(o_el.get("id")),
            customer_id=_to_int(_text(o_el, "customer_id")),
            order_date=_text(o_el, "order_date"),
            status=_text(o_el, "status"),
            items=items,
            total=_to_float(_text(o_el, "total")),
        )
        orders.append(order)
    return customers, orders


# ---------------------------------------------------------------------- #
# Мелкие помощники парсинга XML
# ---------------------------------------------------------------------- #
def _text(parent: ET.Element, tag: str) -> str:
    el = parent.find(tag)
    return el.text if el is not None and el.text is not None else ""


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
