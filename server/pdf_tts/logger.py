"""
pdf_tts/logger.py
-----------------
Central logging configuration for the whole application.
Import `log` from here instead of creating per-module loggers.
"""

import logging
import os
import sys

_level_name = os.getenv("PDF_TTS_LOG_LEVEL", "INFO").upper()
_level = getattr(logging, _level_name, logging.DEBUG)

log = logging.getLogger("pdf_tts")
log.setLevel(_level)

# Add a handler only once — guard against re-imports adding duplicates.
if not log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(_handler)

# Do NOT propagate to the root logger; we handle our own output above.
log.propagate = False
