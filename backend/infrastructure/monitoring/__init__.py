"""Structured logging (Fig 25 Observability Stack): one JSON object per line on stdout."""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("lingopath")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "event": record.getMessage(),
        }
        data.update(getattr(record, "fields", {}))
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str, ensure_ascii=False)


def log_event(event: str, *, level: int = logging.INFO, exc_info: bool = False, **fields) -> None:
    logger.log(level, event, extra={"fields": fields}, exc_info=exc_info)
