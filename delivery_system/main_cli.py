"""CLI-точка входа системы учёта заказов «Быстрая доставка».

Примеры запуска:
    python main_cli.py report --period month
    python main_cli.py export --file orders_backup.xml
    python main_cli.py export --file orders_backup.json
    python main_cli.py import --file orders_new.xml
    python main_cli.py import --file orders_new.json

Дополнительные команды для удобства работы из консоли:
    python main_cli.py list-orders --status новый
    python main_cli.py add-customer --name "Иван" --phone "+7..." --address "..."
    python main_cli.py seed            # заполнить БД демонстрационными данными
"""
import argparse
import sys

from data_export import export_data, import_data
from database import Database, get_database  # Database — для аннотаций типов
from logger_config import setup_logger
from models import Customer, Order, OrderItem

logger = setup_logger("delivery.cli")


def cmd_report(db: Database, args) -> None:
    print("=" * 50)
    print("ОТЧЁТ ПО ЗАКАЗАМ")
    print("=" * 50)

    print("\nКоличество заказов по статусам:")
    for status, count in db.count_by_status().items():
        print(f"  {status:<12} : {count}")

    print("\nТоп-3 клиента по сумме заказов:")
    top = db.top_customers(3)
    if not top:
        print("  (нет данных)")
    for i, c in enumerate(top, 1):
        print(f"  {i}. {c['name']:<20} — {c['total_sum']:.2f} руб. "
              f"(заказов: {c['orders_count']})")

    rev = db.revenue_for_period(args.period)
    print(f"\nВыручка за период '{rev['period']}' "
          f"({rev['date_from']} — {rev['date_to']}):")
    print(f"  {rev['revenue']:.2f} руб. (заказов: {rev['orders_count']})")
    print("=" * 50)


def cmd_export(db: Database, args) -> None:
    export_data(db, args.file)
    print(f"Данные экспортированы в файл: {args.file}")


def cmd_import(db: Database, args) -> None:
    customers, orders = import_data(db, args.file)
    print(f"Импортировано клиентов: {customers}, заказов: {orders}")


def cmd_list_orders(db: Database, args) -> None:
    orders = db.get_orders(
        status=args.status, date_from=args.date_from, date_to=args.date_to
    )
    if not orders:
        print("Заказы не найдены.")
        return
    print(f"{'ID':<5}{'Дата':<12}{'Клиент':<8}{'Статус':<14}{'Сумма':>10}")
    print("-" * 50)
    for o in orders:
        print(f"{o.id:<5}{o.order_date:<12}{o.customer_id:<8}"
              f"{o.status:<14}{o.total:>10.2f}")


def cmd_list_customers(db: Database, args) -> None:
    customers = db.get_customers()
    if not customers:
        print("Клиенты не найдены.")
        return
    for c in customers:
        print(f"{c.id}: {c.name} | {c.phone} | {c.address}")


def cmd_add_customer(db: Database, args) -> None:
    cid = db.add_customer(Customer(name=args.name, phone=args.phone or "",
                                   address=args.address or ""))
    print(f"Добавлен клиент с id={cid}")


def cmd_seed(db: Database, args) -> None:
    """Заполнить БД демонстрационными данными."""
    from datetime import date, timedelta

    today = date.today()
    c1 = db.add_customer(Customer(name="Иван Петров", phone="+79001112233",
                                  address="ул. Ленина, 1"))
    c2 = db.add_customer(Customer(name="Мария Сидорова", phone="+79004445566",
                                  address="ул. Мира, 5"))
    c3 = db.add_customer(Customer(name="ООО Ромашка", phone="+74951234567",
                                  address="пр. Победы, 10"))

    db.add_order(Order(customer_id=c1, order_date=today.isoformat(),
                       status="новый",
                       items=[OrderItem("Пицца Маргарита", 2, 750),
                              OrderItem("Кола", 1, 120)]))
    db.add_order(Order(customer_id=c2,
                       order_date=(today - timedelta(days=3)).isoformat(),
                       status="выполнен",
                       items=[OrderItem("Суши-сет", 1, 1990)]))
    db.add_order(Order(customer_id=c3,
                       order_date=(today - timedelta(days=10)).isoformat(),
                       status="в доставке",
                       items=[OrderItem("Бизнес-ланч", 15, 350)]))
    db.add_order(Order(customer_id=c1,
                       order_date=(today - timedelta(days=20)).isoformat(),
                       status="отменён",
                       items=[OrderItem("Бургер", 3, 290)]))
    print("Демонстрационные данные добавлены.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="delivery",
        description="Система учёта заказов «Быстрая доставка» (CLI)",
    )
    parser.add_argument("--db", default=None, help="Путь к файлу БД")
    parser.add_argument("--backend", choices=["sqlite", "tinydb"], default="sqlite",
                        help="Тип хранилища: sqlite (по умолчанию) или tinydb")
    # required=False: при запуске без команды показываем подсказку, а не ошибку
    sub = parser.add_subparsers(dest="command")

    p_report = sub.add_parser("report", help="Отчёты и аналитика")
    p_report.add_argument("--period", choices=["day", "week", "month"],
                          default="month", help="Период для расчёта выручки")
    p_report.set_defaults(func=cmd_report)

    p_export = sub.add_parser("export", help="Экспорт заказов в XML/JSON")
    p_export.add_argument("--file", required=True, help="Имя файла (.xml или .json)")
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser("import", help="Импорт заказов из XML/JSON")
    p_import.add_argument("--file", required=True, help="Имя файла (.xml или .json)")
    p_import.set_defaults(func=cmd_import)

    p_lo = sub.add_parser("list-orders", help="Список заказов с фильтрацией")
    p_lo.add_argument("--status", default=None, help="Фильтр по статусу")
    p_lo.add_argument("--date-from", dest="date_from", default=None,
                      help="Дата с (YYYY-MM-DD)")
    p_lo.add_argument("--date-to", dest="date_to", default=None,
                      help="Дата по (YYYY-MM-DD)")
    p_lo.set_defaults(func=cmd_list_orders)

    p_lc = sub.add_parser("list-customers", help="Список клиентов")
    p_lc.set_defaults(func=cmd_list_customers)

    p_ac = sub.add_parser("add-customer", help="Добавить клиента")
    p_ac.add_argument("--name", required=True)
    p_ac.add_argument("--phone", default="")
    p_ac.add_argument("--address", default="")
    p_ac.set_defaults(func=cmd_add_customer)

    p_seed = sub.add_parser("seed", help="Заполнить БД демо-данными")
    p_seed.set_defaults(func=cmd_seed)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Запуск без команды (например, по кнопке Run) — показываем список команд
    if not args.command:
        parser.print_help()
        return 0

    db = get_database(args.backend, args.db)
    try:
        args.func(db, args)
        return 0
    except Exception as exc:  # noqa: BLE001 — выводим ошибку пользователю
        logger.error("Ошибка выполнения команды '%s': %s", args.command, exc)
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
