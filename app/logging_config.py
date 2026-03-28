"""Centralised structlog configuration for AccessWave.

Call ``configure_logging()`` once at application start-up (in main.py) before
any logger is obtained.  After that, every module can simply do::

    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("event_name", key=value, ...)

Two output modes are supported, controlled by the ``LOG_FORMAT`` env var:

* ``console`` (default) – coloured, human-readable output for local dev.
* ``json`` – one JSON object per line; suitable for log-aggregation pipelines
  (Datadog, ELK, Cloud Logging, etc.).

The ``LOG_LEVEL`` env var (default ``INFO``) controls the minimum severity
that reaches the handler for *all* loggers, including third-party ones.
Noisy libraries (httpx, httpcore) are quieted to WARNING regardless.
"""

import logging
import sys

import structlog


def configure_logging(log_level: str = "INFO", log_format: str = "console") -> None:
    """Wire structlog to stdlib and configure the root handler.

    Args:
        log_level: Minimum log level string, e.g. ``"INFO"`` or ``"DEBUG"``.
        log_format: ``"console"`` for pretty output; ``"json"`` for JSON lines.
    """
    # Processors shared between structlog-native calls and stdlib-forwarded
    # records (e.g. from uvicorn or sqlalchemy).
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # The final renderer only runs on structlog-native records.
        processor=renderer,
        # foreign_pre_chain processes stdlib records before rendering.
        foreign_pre_chain=shared_processors + [
            structlog.processors.ExceptionRenderer(),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Quieten noisy third-party loggers that would otherwise flood the console
    # at INFO level even when AccessWave itself is at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)
