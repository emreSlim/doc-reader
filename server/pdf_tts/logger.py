"""
pdf_tts/logger.py
-----------------
Central logging configuration for the whole application.
Import `log` from here instead of creating per-module loggers.
"""

import logging
import os
import sys

_level_name = os.getenv("PDF_TTS_LOG_LEVEL", "DEBUG").upper()
_level = getattr(logging, _level_name, logging.DEBUG)

logging.basicConfig(
    level=_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)

log = logging.getLogger("pdf_tts")
log.setLevel(_level)
if not log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(_handler)
log.propagate = True
