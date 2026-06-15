"""Настройка логирования для всего приложения.

Логи пишутся одновременно в файл (logs/delivery.log) и в консоль.
"""
import logging
import os

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "delivery.log")


def setup_logger(name: str = "delivery", level: int = logging.INFO) -> logging.Logger:
    """Создать и вернуть настроенный логгер.

    Повторные вызовы не добавляют дублирующие обработчики.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Защита от дублирования обработчиков при повторной инициализации
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger
