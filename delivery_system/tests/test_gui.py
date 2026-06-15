"""Тесты графического интерфейса (Tkinter).

Окна создаются по-настоящему, но все всплывающие диалоги (messagebox,
filedialog) подменяются заглушками, чтобы тесты не зависали в ожидании
кликов пользователя. Если графическая среда недоступна, тесты пропускаются.
"""
import tkinter as tk

import pytest

import main_gui
from models import Customer, Order, OrderItem


# --------------------------------------------------------------------- #
# Фикстуры
# --------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def tk_root():
    """Один корневой Tk на всю сессию — App создаётся как Frame внутри него.

    Создаём ровно один Tk() и не пересоздаём его: на Windows создание
    нового Tk() после уничтожения предыдущего ломает поиск init.tcl.
    Если графическая среда недоступна — все GUI-тесты пропускаются.
    """
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Графическая среда недоступна: {exc}")
    root.withdraw()  # не показывать пустое окно во время тестов
    yield root
    root.destroy()


@pytest.fixture(autouse=True)
def _silence_dialogs(monkeypatch):
    """Глушим всплывающие окна, чтобы тесты не открывали реальные диалоги."""
    for name in ("showinfo", "showerror", "showwarning"):
        monkeypatch.setattr(main_gui.messagebox, name, lambda *a, **k: None)
    monkeypatch.setattr(main_gui.messagebox, "askyesno", lambda *a, **k: True)


@pytest.fixture
def app(tk_root, db):
    """Главное окно приложения с тестовой БД (db — sqlite и tinydb)."""
    application = main_gui.App(tk_root, db)
    application.update_idletasks()
    yield application
    application.destroy()


def _add_customer(db, name="Иван"):
    return db.add_customer(Customer(name=name, phone="+7", address="адрес"))


def _add_order(db, customer_id, status="новый", date="2025-04-20"):
    return db.add_order(Order(customer_id=customer_id, order_date=date,
                              status=status, items=[OrderItem("Товар", 2, 500)]))


# --------------------------------------------------------------------- #
# Главное окно
# --------------------------------------------------------------------- #
def test_refresh_orders_shows_rows(tk_root, db):
    cid = _add_customer(db)
    _add_order(db, cid)
    app = main_gui.App(tk_root, db)
    try:
        rows = app.tree.get_children()
        assert len(rows) == 1
        values = app.tree.item(rows[0], "values")
        assert values[2] == "Иван"  # колонка «Клиент»
    finally:
        app.destroy()


def test_filter_by_status(app, db):
    cid = _add_customer(db)
    _add_order(db, cid, status="новый")
    _add_order(db, cid, status="выполнен")
    app.filter_var.set("выполнен")
    app.refresh_orders()
    assert len(app.tree.get_children()) == 1


def test_customer_name_helper(app, db):
    cid = _add_customer(db, "Мария")
    assert app._customer_name(cid) == "Мария"
    assert "id=" in app._customer_name(99999)  # несуществующий клиент


def test_delete_order(app, db):
    cid = _add_customer(db)
    _add_order(db, cid)
    app.refresh_orders()
    row = app.tree.get_children()[0]
    app.tree.selection_set(row)
    app.delete_order()  # askyesno замокан на True
    assert app.tree.get_children() == ()
    assert db.get_orders() == []


# --------------------------------------------------------------------- #
# Диалог заказа
# --------------------------------------------------------------------- #
def test_order_dialog_creates_order(app, db):
    cid = _add_customer(db)
    dlg = main_gui.OrderDialog(app, db)
    dlg.customer_var.set(f"{cid}: Иван")
    dlg.date_var.set("2025-05-01")
    dlg.status_var.set("новый")
    # Заполняем поля и добавляем позицию через кнопку «+ позиция»
    dlg.item_name.insert(0, "Пицца")
    dlg.item_qty.insert(0, "2")
    dlg.item_price.insert(0, "750")
    dlg._add_item()
    dlg._save()

    assert dlg.result is True
    orders = db.get_orders()
    assert len(orders) == 1
    assert orders[0].total == 1500.0


def test_order_dialog_requires_items(app, db):
    cid = _add_customer(db)
    dlg = main_gui.OrderDialog(app, db)
    dlg.customer_var.set(f"{cid}: Иван")
    dlg._save()  # позиций нет -> сохранение не должно пройти
    try:
        assert dlg.result is None
        assert db.get_orders() == []
    finally:
        dlg.destroy()


def test_order_dialog_edit(app, db):
    cid = _add_customer(db)
    oid = _add_order(db, cid, status="новый")
    order = db.get_order(oid)
    dlg = main_gui.OrderDialog(app, db, order)
    dlg.status_var.set("выполнен")
    dlg._save()
    assert db.get_order(oid).status == "выполнен"


# --------------------------------------------------------------------- #
# Окно клиентов
# --------------------------------------------------------------------- #
def test_customer_window_add(app, db):
    win = main_gui.CustomerWindow(app, db)
    try:
        win.name_e.insert(0, "Новый Клиент")
        win.phone_e.insert(0, "+700")
        win.add()
        names = [c.name for c in db.get_customers()]
        assert "Новый Клиент" in names
    finally:
        win.destroy()


def test_customer_window_delete_with_orders_blocked(app, db):
    cid = _add_customer(db)
    _add_order(db, cid)
    win = main_gui.CustomerWindow(app, db)
    try:
        row = win.tree.get_children()[0]
        win.tree.selection_set(row)
        win.delete()  # showerror замокан; клиент остаётся
        assert db.get_customer(cid) is not None
    finally:
        win.destroy()


# --------------------------------------------------------------------- #
# Окно отчёта
# --------------------------------------------------------------------- #
def test_report_window_text(app, db):
    cid = _add_customer(db, "Иван")
    _add_order(db, cid, status="новый")
    win = main_gui.ReportWindow(app, db)
    try:
        content = win.text.get("1.0", "end")
        assert "ОТЧЁТ ПО ЗАКАЗАМ" in content
        assert "Иван" in content
    finally:
        win.destroy()


# --------------------------------------------------------------------- #
# Экспорт / импорт через окно
# --------------------------------------------------------------------- #
def test_gui_export_and_import(app, db, tmp_path, monkeypatch):
    cid = _add_customer(db)
    _add_order(db, cid)

    target = tmp_path / "gui_export.json"
    monkeypatch.setattr(main_gui.filedialog, "asksaveasfilename",
                        lambda *a, **k: str(target))
    app.format_var.set("JSON")
    app.export()
    assert target.exists()

    # Импортируем тот же файл обратно — число заказов удвоится
    monkeypatch.setattr(main_gui.filedialog, "askopenfilename",
                        lambda *a, **k: str(target))
    app.do_import()
    assert len(db.get_orders()) == 2
