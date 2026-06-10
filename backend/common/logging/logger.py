"""
Unified logging for the Backuper application.

Two loggers are exposed:

* **tech_logger** — technical traces: errors, performance, debug.
* **biz_logger**  — business traces: audit, user actions.

Usage::

    from backend.common.logging import tech_logger, biz_logger

    tech_logger.info("Datastore client initialised")
    biz_logger.info("User registered: user@example.com")
"""

import logging
import sys


def _build_logger(name: str, fmt: str) -> logging.Logger:
    """Create (or retrieve) a named logger with a stdout handler."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


tech_logger = _build_logger(
    "backuper.tech",
    "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

biz_logger = _build_logger(
    "backuper.biz",
    "%(asctime)s [BIZ] %(message)s",
)
