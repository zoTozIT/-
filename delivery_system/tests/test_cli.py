"""Тесты CLI-интерфейса (main_cli.main с подменой пути к БД)."""
import main_cli


def _db_file(tmp_path):
    return str(tmp_path / "cli_test.db")


def test_cli_seed_and_report(tmp_path, capsys):
    dbfile = _db_file(tmp_path)
    assert main_cli.main(["--db", dbfile, "seed"]) == 0
    assert main_cli.main(["--db", dbfile, "report", "--period", "month"]) == 0
    out = capsys.readouterr().out
    assert "ОТЧЁТ ПО ЗАКАЗАМ" in out
    assert "Топ-3 клиента" in out


def test_cli_add_and_list_customers(tmp_path, capsys):
    dbfile = _db_file(tmp_path)
    assert main_cli.main(
        ["--db", dbfile, "add-customer", "--name", "Тест", "--phone", "+700"]) == 0
    assert main_cli.main(["--db", dbfile, "list-customers"]) == 0
    out = capsys.readouterr().out
    assert "Тест" in out


def test_cli_list_orders_filter(tmp_path, capsys):
    dbfile = _db_file(tmp_path)
    main_cli.main(["--db", dbfile, "seed"])
    capsys.readouterr()
    assert main_cli.main(["--db", dbfile, "list-orders", "--status", "новый"]) == 0
    out = capsys.readouterr().out
    assert "новый" in out


def test_cli_export_import(tmp_path):
    dbfile = _db_file(tmp_path)
    main_cli.main(["--db", dbfile, "seed"])

    backup = str(tmp_path / "backup.json")
    assert main_cli.main(["--db", dbfile, "export", "--file", backup]) == 0

    dbfile2 = str(tmp_path / "cli_test2.db")
    assert main_cli.main(["--db", dbfile2, "import", "--file", backup]) == 0


def test_cli_export_xml(tmp_path):
    dbfile = _db_file(tmp_path)
    main_cli.main(["--db", dbfile, "seed"])
    backup = str(tmp_path / "backup.xml")
    assert main_cli.main(["--db", dbfile, "export", "--file", backup]) == 0


def test_cli_import_missing_file_returns_error(tmp_path):
    dbfile = _db_file(tmp_path)
    # Несуществующий файл -> код возврата 1
    assert main_cli.main(["--db", dbfile, "import", "--file", "nope.json"]) == 1


def test_cli_no_command_shows_help(capsys):
    """Запуск без команды показывает подсказку и завершается без ошибки."""
    assert main_cli.main([]) == 0
    out = capsys.readouterr().out
    assert "report" in out and "export" in out


def test_cli_tinydb_backend(tmp_path, capsys):
    """CLI должен работать и на бэкенде TinyDB (--backend tinydb)."""
    dbfile = str(tmp_path / "cli.json")
    assert main_cli.main(["--backend", "tinydb", "--db", dbfile, "seed"]) == 0
    assert main_cli.main(
        ["--backend", "tinydb", "--db", dbfile, "report", "--period", "month"]) == 0
    out = capsys.readouterr().out
    assert "ОТЧЁТ ПО ЗАКАЗАМ" in out
