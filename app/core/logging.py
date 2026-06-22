import logging
import logging.handlers
import sys

from app.core.config import settings


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("app")
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    try:
        syslog_handler = logging.handlers.SysLogHandler(
            address=(settings.SYSLOG_HOST, settings.SYSLOG_PORT)
        )
        syslog_handler.setFormatter(formatter)
        logger.addHandler(syslog_handler)
    except Exception as e:
        logger.warning(f"Syslog handler could not be initialized: {e}")

    return logger


logger = setup_logging()
