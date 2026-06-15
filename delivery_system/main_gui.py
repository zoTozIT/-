"""GUI-точка входа (Tkinter) системы учёта заказов «Быстрая доставка».

Главное окно: список заказов (Treeview), кнопки «Добавить»,
«Редактировать», «Удалить», фильтр по статусу, кнопка «Показать отчёт»
и выпадающий список формата экспорта (XML/JSON).
"""
import os
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from data_export import export_data, import_data
from database import Database, get_database
from logger_config import setup_logger
from models import VALID_STATUSES, Customer, Order, OrderItem

logger = setup_logger("delivery.gui")


class OrderDialog(tk.Toplevel):
    """Модальное окно создания/редактирования заказа."""

    def __init__(self, parent, db: Database, order: Order = None):
        super().__init__(parent)
        self.db = db
        self.order = order
        self.result = None
        self.title("Редактирование заказа" if order else "Новый заказ")
        self.geometry("520x520")
        self.transient(parent)
        self.grab_set()

        self.customers = db.get_customers()
        self._build_ui()
        if order:
            self._load_order(order)

    def _build_ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        # Клиент
        ttk.Label(frm, text="Клиент:").grid(row=0, column=0, sticky="w", pady=4)
        self.customer_var = tk.StringVar()
        self.customer_cb = ttk.Combobox(
            frm, textvariable=self.customer_var, state="readonly", width=40,
            values=[f"{c.id}: {c.name}" for c in self.customers],
        )
        self.customer_cb.grid(row=0, column=1, sticky="w", pady=4)

        # Дата
        ttk.Label(frm, text="Дата (YYYY-MM-DD):").grid(row=1, column=0, sticky="w", pady=4)
        self.date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(frm, textvariable=self.date_var, width=42).grid(
            row=1, column=1, sticky="w", pady=4)

        # Статус
        ttk.Label(frm, text="Статус:").grid(row=2, column=0, sticky="w", pady=4)
        self.status_var = tk.StringVar(value=VALID_STATUSES[0])
        ttk.Combobox(frm, textvariable=self.status_var, state="readonly",
                     values=list(VALID_STATUSES), width=40).grid(
            row=2, column=1, sticky="w", pady=4)

        # Позиции заказа
        ttk.Label(frm, text="Позиции заказа:").grid(row=3, column=0, sticky="nw", pady=4)
        items_frame = ttk.Frame(frm)
        items_frame.grid(row=3, column=1, sticky="w", pady=4)

        self.items_tree = ttk.Treeview(
            items_frame, columns=("name", "qty", "price"), show="headings", height=6)
        self.items_tree.heading("name", text="Товар")
        self.items_tree.heading("qty", text="Кол-во")
        self.items_tree.heading("price", text="Цена")
        self.items_tree.column("name", width=180)
        self.items_tree.column("qty", width=70, anchor="center")
        self.items_tree.column("price", width=80, anchor="e")
        self.items_tree.pack()

        # Поля добавления позиции
        add_frame = ttk.Frame(frm)
        add_frame.grid(row=4, column=1, sticky="w", pady=4)
        self.item_name = ttk.Entry(add_frame, width=20)
        self.item_name.grid(row=0, column=0, padx=2)
        self.item_qty = ttk.Entry(add_frame, width=6)
        self.item_qty.grid(row=0, column=1, padx=2)
        self.item_price = ttk.Entry(add_frame, width=8)
        self.item_price.grid(row=0, column=2, padx=2)
        ttk.Button(add_frame, text="+ позиция", command=self._add_item).grid(
            row=0, column=3, padx=2)
        ttk.Button(add_frame, text="− удалить", command=self._remove_item).grid(
            row=0, column=4, padx=2)

        # Кнопки
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=5, column=1, sticky="e", pady=16)
        ttk.Button(btn_frame, text="Сохранить", command=self._save).pack(
            side="left", padx=4)
        ttk.Button(btn_frame, text="Отмена", command=self.destroy).pack(
            side="left", padx=4)

    def _add_item(self):
        name = self.item_name.get().strip()
        try:
            qty = int(self.item_qty.get())
            price = float(self.item_price.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Количество и цена должны быть числами",
                                 parent=self)
            return
        if not name:
            messagebox.showerror("Ошибка", "Введите название товара", parent=self)
            return
        self.items_tree.insert("", "end", values=(name, qty, price))
        self.item_name.delete(0, "end")
        self.item_qty.delete(0, "end")
        self.item_price.delete(0, "end")

    def _remove_item(self):
        for sel in self.items_tree.selection():
            self.items_tree.delete(sel)

    def _load_order(self, order: Order):
        for c in self.customers:
            if c.id == order.customer_id:
                self.customer_var.set(f"{c.id}: {c.name}")
                break
        self.date_var.set(order.order_date)
        self.status_var.set(order.status)
        for item in order.items:
            self.items_tree.insert(
                "", "end", values=(item.product_name, item.quantity, item.price))

    def _save(self):
        if not self.customer_var.get():
            messagebox.showerror("Ошибка", "Выберите клиента", parent=self)
            return
        customer_id = int(self.customer_var.get().split(":")[0])
        items = []
        for row_id in self.items_tree.get_children():
            name, qty, price = self.items_tree.item(row_id, "values")
            items.append(OrderItem(name, int(qty), float(price)))
        if not items:
            messagebox.showerror("Ошибка", "Добавьте хотя бы одну позицию",
                                 parent=self)
            return

        try:
            if self.order:  # редактирование
                self.order.customer_id = customer_id
                self.order.order_date = self.date_var.get().strip()
                self.order.status = self.status_var.get()
                self.order.items = items
                self.db.update_order(self.order)
            else:  # создание
                order = Order(
                    customer_id=customer_id,
                    order_date=self.date_var.get().strip(),
                    status=self.status_var.get(),
                    items=items,
                )
                self.db.add_order(order)
            self.result = True
            self.destroy()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка сохранения", str(exc), parent=self)


class App(ttk.Frame):
    """Главное окно приложения (фрейм, размещаемый в корневом окне).

    App — это Frame, а не Tk, чтобы в одном процессе можно было создавать
    несколько окон (например, в тестах) без конфликтов интерпретатора Tcl.
    """

    def __init__(self, master, db: Database):
        super().__init__(master)
        self.db = db
        master.title("Быстрая доставка — учёт заказов")
        master.geometry("760x520")
        self.pack(fill="both", expand=True)
        self._build_ui()
        self.refresh_orders()

    def _build_ui(self):
        # Панель управления
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Фильтр по статусу:").pack(side="left")
        self.filter_var = tk.StringVar(value="все")
        ttk.Combobox(
            top, textvariable=self.filter_var, state="readonly", width=14,
            values=["все"] + list(VALID_STATUSES),
        ).pack(side="left", padx=4)
        ttk.Button(top, text="Применить", command=self.refresh_orders).pack(
            side="left", padx=4)

        ttk.Label(top, text="Формат:").pack(side="left", padx=(16, 2))
        self.format_var = tk.StringVar(value="JSON")
        ttk.Combobox(top, textvariable=self.format_var, state="readonly", width=6,
                     values=["JSON", "XML"]).pack(side="left")
        ttk.Button(top, text="Экспорт", command=self.export).pack(side="left", padx=4)
        ttk.Button(top, text="Импорт", command=self.do_import).pack(side="left", padx=4)

        # Таблица заказов
        columns = ("id", "date", "customer", "status", "total")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        for col, title, width, anchor in (
            ("id", "ID", 50, "center"),
            ("date", "Дата", 110, "center"),
            ("customer", "Клиент", 240, "w"),
            ("status", "Статус", 120, "center"),
            ("total", "Сумма", 110, "e"),
        ):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor=anchor)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        # Нижние кнопки
        bottom = ttk.Frame(self, padding=8)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Добавить", command=self.add_order).pack(side="left")
        ttk.Button(bottom, text="Редактировать", command=self.edit_order).pack(
            side="left", padx=4)
        ttk.Button(bottom, text="Удалить", command=self.delete_order).pack(side="left")
        ttk.Button(bottom, text="Клиенты", command=self.manage_customers).pack(
            side="left", padx=4)
        ttk.Button(bottom, text="Показать отчёт", command=self.show_report).pack(
            side="right")

    # ----------------------- действия с заказами ----------------------- #
    def _customer_name(self, customer_id: int) -> str:
        c = self.db.get_customer(customer_id)
        return c.name if c else f"id={customer_id}"

    def refresh_orders(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        status = None if self.filter_var.get() == "все" else self.filter_var.get()
        for o in self.db.get_orders(status=status):
            self.tree.insert("", "end", values=(
                o.id, o.order_date, self._customer_name(o.customer_id),
                o.status, f"{o.total:.2f}"))

    def _selected_order_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Внимание", "Выберите заказ в списке")
            return None
        return int(self.tree.item(sel[0], "values")[0])

    def add_order(self):
        if not self.db.get_customers():
            messagebox.showwarning(
                "Нет клиентов", "Сначала добавьте хотя бы одного клиента "
                "(кнопка «Клиенты»).")
            return
        dlg = OrderDialog(self, self.db)
        self.wait_window(dlg)
        if dlg.result:
            self.refresh_orders()

    def edit_order(self):
        order_id = self._selected_order_id()
        if order_id is None:
            return
        order = self.db.get_order(order_id)
        dlg = OrderDialog(self, self.db, order)
        self.wait_window(dlg)
        if dlg.result:
            self.refresh_orders()

    def delete_order(self):
        order_id = self._selected_order_id()
        if order_id is None:
            return
        if messagebox.askyesno("Подтверждение", f"Удалить заказ #{order_id}?"):
            self.db.delete_order(order_id)
            self.refresh_orders()

    # ----------------------- клиенты ----------------------- #
    def manage_customers(self):
        CustomerWindow(self, self.db)

    # ----------------------- экспорт/импорт ----------------------- #
    def export(self):
        ext = ".json" if self.format_var.get() == "JSON" else ".xml"
        filename = filedialog.asksaveasfilename(
            defaultextension=ext,
            filetypes=[("JSON", "*.json"), ("XML", "*.xml")],
            initialfile=f"orders_backup{ext}",
        )
        if not filename:
            return
        try:
            export_data(self.db, filename)
            messagebox.showinfo("Готово", f"Данные экспортированы:\n{filename}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка экспорта", str(exc))

    def do_import(self):
        filename = filedialog.askopenfilename(
            filetypes=[("JSON/XML", "*.json *.xml"), ("Все файлы", "*.*")])
        if not filename:
            return
        try:
            customers, orders = import_data(self.db, filename)
            self.refresh_orders()
            messagebox.showinfo(
                "Готово", f"Импортировано клиентов: {customers}, заказов: {orders}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка импорта", str(exc))

    # ----------------------- отчёт ----------------------- #
    def show_report(self):
        ReportWindow(self, self.db)


class CustomerWindow(tk.Toplevel):
    """Окно управления клиентами (CRUD)."""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.title("Клиенты")
        self.geometry("560x400")
        self.transient(parent)

        self.tree = ttk.Treeview(
            self, columns=("id", "name", "phone", "address"), show="headings")
        for col, title, width in (
            ("id", "ID", 40), ("name", "Имя", 160),
            ("phone", "Телефон", 130), ("address", "Адрес", 200)):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width)
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        form = ttk.Frame(self, padding=8)
        form.pack(fill="x")
        ttk.Label(form, text="Имя").grid(row=0, column=0)
        ttk.Label(form, text="Телефон").grid(row=0, column=1)
        ttk.Label(form, text="Адрес").grid(row=0, column=2)
        self.name_e = ttk.Entry(form, width=18)
        self.name_e.grid(row=1, column=0, padx=2)
        self.phone_e = ttk.Entry(form, width=16)
        self.phone_e.grid(row=1, column=1, padx=2)
        self.addr_e = ttk.Entry(form, width=22)
        self.addr_e.grid(row=1, column=2, padx=2)
        ttk.Button(form, text="Добавить", command=self.add).grid(row=1, column=3, padx=4)
        ttk.Button(form, text="Удалить выбранного", command=self.delete).grid(
            row=2, column=0, columnspan=2, pady=6, sticky="w")

        self.refresh()

    def refresh(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for c in self.db.get_customers():
            self.tree.insert("", "end", values=(c.id, c.name, c.phone, c.address))

    def add(self):
        name = self.name_e.get().strip()
        if not name:
            messagebox.showerror("Ошибка", "Введите имя", parent=self)
            return
        try:
            self.db.add_customer(Customer(
                name=name, phone=self.phone_e.get(), address=self.addr_e.get()))
            self.name_e.delete(0, "end")
            self.phone_e.delete(0, "end")
            self.addr_e.delete(0, "end")
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Ошибка", str(exc), parent=self)

    def delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        cid = int(self.tree.item(sel[0], "values")[0])
        try:
            self.db.delete_customer(cid)
            self.refresh()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Нельзя удалить", str(exc), parent=self)


class ReportWindow(tk.Toplevel):
    """Окно со статистикой и аналитикой."""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self.title("Отчёт")
        self.geometry("460x420")
        self.transient(parent)

        period_frame = ttk.Frame(self, padding=8)
        period_frame.pack(fill="x")
        ttk.Label(period_frame, text="Период выручки:").pack(side="left")
        self.period_var = tk.StringVar(value="month")
        ttk.Combobox(period_frame, textvariable=self.period_var, state="readonly",
                     width=8, values=["day", "week", "month"]).pack(side="left", padx=4)
        ttk.Button(period_frame, text="Обновить", command=self.refresh).pack(side="left")

        self.text = tk.Text(self, wrap="word", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True, padx=8, pady=8)
        self.refresh()

    def refresh(self):
        self.text.delete("1.0", "end")
        lines = ["=== ОТЧЁТ ПО ЗАКАЗАМ ===\n",
                 "\nКоличество заказов по статусам:"]
        for status, count in self.db.count_by_status().items():
            lines.append(f"  {status:<12}: {count}")

        lines.append("\nТоп-3 клиента по сумме заказов:")
        top = self.db.top_customers(3)
        if not top:
            lines.append("  (нет данных)")
        for i, c in enumerate(top, 1):
            lines.append(f"  {i}. {c['name']} — {c['total_sum']:.2f} руб. "
                         f"(заказов: {c['orders_count']})")

        rev = self.db.revenue_for_period(self.period_var.get())
        lines.append(f"\nВыручка за период '{rev['period']}'")
        lines.append(f"  ({rev['date_from']} — {rev['date_to']})")
        lines.append(f"  Итого: {rev['revenue']:.2f} руб. "
                     f"(заказов: {rev['orders_count']})")
        self.text.insert("1.0", "\n".join(lines))


def main():
    # Бэкенд можно переключить переменной окружения DELIVERY_BACKEND=tinydb
    backend = os.environ.get("DELIVERY_BACKEND", "sqlite")
    db = get_database(backend)
    root = tk.Tk()
    App(root, db)
    try:
        root.mainloop()
    finally:
        db.close()


if __name__ == "__main__":
    main()
