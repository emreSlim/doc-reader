"""
pdf_tts/logger.py
-----------------
Central logging configuration for the whole application.
Import `log` from here instead of creating per-module loggers.
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)

log = logging.getLogger("pdf_tts")
