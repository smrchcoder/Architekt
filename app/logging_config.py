"""Centralised logging configuration using Python stdlib logging.

Calling convention:
    from app.logging_config import get_logger
    log = get_logger(__name__)                    # module-level
    log = log.bind(run_id="abc", step="ingest")   # add structured context
    log.info("article ingested | words=%d", wc)    # structured keys auto-prepended

Stderr output:   HH:MM:SS.MMM | LEVEL    | run_id=abc step=ingest | article ingested | words=1400
File output:     YYYY-MM-DD HH:MM:SS.MMM | LEVEL | name:func:line | run_id=abc step=ingest | article ingested | words=1400
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class _ExtraFormatter(logging.Formatter):
    """Formatter that renders extra dict keys into the message prefix."""

    def format(self, record: logging.LogRecord) -> str:
        extras: list[str] = []
        for key in sorted(record.__dict__):
            if key in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName",
                "_bound_extra",
            }:
                continue
            value = record.__dict__[key]
            if value is not None:
                extras.append(f"{key}={value}")
        prefix = " | ".join(extras)
        record.extra_prefix = f"{prefix} | " if prefix else ""
        return super().format(record)


class BoundLogger(logging.LoggerAdapter):
    """LoggerAdapter that supports .bind() for injecting structured context.

    Usage:
        log = get_logger(__name__).bind(run_id="abc")
        log.info("step started | progress=%d%%", 45)
        → renders as: run_id=abc | step started | progress=45%
    """

    def __init__(self, logger: logging.Logger, extra: dict[str, Any] | None = None) -> None:
        super().__init__(logger, extra or {})

    def bind(self, **kwargs: Any) -> BoundLogger:
        merged = {**self.extra, **kwargs}
        return BoundLogger(self.logger, merged)

    def process(self, msg: Any, kwargs: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        kwargs["extra"] = {**self.extra, **kwargs.get("extra", {})}
        return msg, kwargs

    @property
    def opt(self) -> _ExceptionOpt:
        """log.opt(exception=True).error("msg") — logs traceback.

        Stdlib equivalent of loguru's logger.opt(exception=True).
        """
        return _ExceptionOpt(self)


class _ExceptionOpt:
    def __init__(self, adapter: BoundLogger) -> None:
        self._adapter = adapter

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        kwargs["exc_info"] = True
        self._adapter.error(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        kwargs["exc_info"] = True
        self._adapter.warning(msg, *args, **kwargs)


_should_configure = True


def setup_logging(*, verbose: bool = False) -> None:
    """Configure stdlib logging globally. Called once at app startup."""
    global _should_configure
    if not _should_configure:
        return

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── stderr handler (colored, compact) ───────────────────────────
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.DEBUG)
    stderr_fmt = (
        "\033[32m%(asctime)s.%(msecs)03d\033[0m | "
        "%(levelname)-8s | "
        "%(extra_prefix)s%(message)s"
    ) if not verbose else (
        "\033[32m%(asctime)s.%(msecs)03d\033[0m | "
        "%(levelname)-8s | "
        "\033[36m%(name)s:%(funcName)s:%(lineno)d\033[0m | "
        "%(extra_prefix)s%(message)s"
    )
    stderr_handler.setFormatter(_ExtraFormatter(stderr_fmt, datefmt="%H:%M:%S"))
    root.addHandler(stderr_handler)

    # ── file handler (verbose, rotated) ──────────────────────────────
    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    file_handler = RotatingFileHandler(
        logs_dir / "orchestrator.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = (
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | "
        "%(name)s:%(funcName)s:%(lineno)d | "
        "%(extra_prefix)s%(message)s"
    )
    file_handler.setFormatter(_ExtraFormatter(file_fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(file_handler)

    _should_configure = False
    root.debug("logging configured | file=%s", str(logs_dir / "orchestrator.log"))


def get_logger(name: str) -> BoundLogger:
    """Return a BoundLogger for the given module name.

    Usage:
        log = get_logger(__name__)
        log = log.bind(run_id="abc123")
        log.info("started")
    """
    return BoundLogger(logging.getLogger(name))
