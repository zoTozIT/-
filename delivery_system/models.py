"""Модели предметной области: Customer, Order, OrderItem.

Классы реализованы через dataclasses и содержат базовую валидацию,
вычисление итоговой суммы и удобную (де)сериализацию в словари.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Допустимые статусы заказа (согласно ТЗ)
VALID_STATUSES = ("новый", "в доставке", "выполнен", "отменён")


@dataclass
class OrderItem:
    """Позиция заказа: товар, количество и цена за единицу."""

    product_name: str
    quantity: int
    price: float
    id: Optional[int] = None
    order_id: Optional[int] = None

    @property
    def subtotal(self) -> float:
        """Стоимость позиции = количество * цена."""
        return round(self.quantity * self.price, 2)

    def validate(self) -> None:
        if not self.product_name or not str(self.product_name).strip():
            raise ValueError("Название товара не может быть пустым")
        if self.quantity is None or int(self.quantity) <= 0:
            raise ValueError("Количество товара должно быть положительным")
        if self.price is None or float(self.price) < 0:
            raise ValueError("Цена товара не может быть отрицательной")

    def to_dict(self) -> dict:
        return {
            "product_name": self.product_name,
            "quantity": int(self.quantity),
            "price": float(self.price),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrderItem":
        return cls(
            product_name=data["product_name"],
            quantity=int(data["quantity"]),
            price=float(data["price"]),
            id=data.get("id"),
            order_id=data.get("order_id"),
        )


@dataclass
class Customer:
    """Клиент компании: имя, телефон, адрес."""

    name: str
    phone: str = ""
    address: str = ""
    id: Optional[int] = None

    def validate(self) -> None:
        if not self.name or not str(self.name).strip():
            raise ValueError("Имя клиента не может быть пустым")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "phone": self.phone,
            "address": self.address,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Customer":
        return cls(
            id=data.get("id"),
            name=data["name"],
            phone=data.get("phone", ""),
            address=data.get("address", ""),
        )


@dataclass
class Order:
    """Заказ: дата, клиент, список товаров, статус и итоговая сумма."""

    customer_id: int
    order_date: str
    status: str = "новый"
    items: List[OrderItem] = field(default_factory=list)
    total: float = 0.0
    id: Optional[int] = None

    def calculate_total(self) -> float:
        """Пересчитать итоговую сумму по позициям заказа."""
        self.total = round(sum(item.subtotal for item in self.items), 2)
        return self.total

    def validate(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"Недопустимый статус '{self.status}'. "
                f"Разрешены: {', '.join(VALID_STATUSES)}"
            )
        if not self.order_date or not str(self.order_date).strip():
            raise ValueError("Дата заказа обязательна")
        if self.customer_id is None:
            raise ValueError("Заказ должен быть привязан к клиенту")
        for item in self.items:
            item.validate()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "customer_id": self.customer_id,
            "order_date": self.order_date,
            "status": self.status,
            "total": float(self.total),
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Order":
        items = [OrderItem.from_dict(i) for i in data.get("items", [])]
        order = cls(
            id=data.get("id"),
            customer_id=int(data["customer_id"]),
            order_date=data["order_date"],
            status=data.get("status", "новый"),
            items=items,
            total=float(data.get("total", 0.0)),
        )
        # Если сумма не задана явно — вычисляем по позициям
        if not data.get("total") and items:
            order.calculate_total()
        return order
