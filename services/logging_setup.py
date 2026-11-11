from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import logs_dir

_FMT = "%(asctime)s %(levelname)-7s [%(process)d %(threadName)s] %(name)s: %(message)s"


def setup_logging(name: str, debug: bool = False) -> logging.Logger:
    root = logging.getLogger()
    if getattr(root, "_spexron_configured", False):
        return root
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fh = RotatingFileHandler(logs_dir() / f"{name}.log", maxBytes=512_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FMT))
    root.addHandler(fh)
    # asyncio'nun proactor gürültüsünü sustur
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    root._spexron_configured = True  # type: ignore[attr-defined]
    return root


def set_debug(enabled: bool) -> None:
    logging.getLogger().setLevel(logging.DEBUG if enabled else logging.INFO)
