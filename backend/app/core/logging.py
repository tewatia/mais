from __future__ import annotations

import logging
import logging.config
import sys
from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = request_id_ctx.get() or "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"request_id": {"()": RequestIdFilter}},
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s [%(name)s] [req=%(request_id)s] %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "default",
                "filters": ["request_id"],
            }
        },
        "root": {"handlers": ["console"], "level": level},
    }
    logging.config.dictConfig(logging_config)
