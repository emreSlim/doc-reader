"""
pdf_tts/config.py
-----------------
Shared constants and default path configuration.
Override any of these via CLI arguments in main.py.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------
DEFAULT_MODEL_PATH = Path("piper/models/en_US-amy-medium.onnx")
DEFAULT_PIPER_EXE  = Path("piper/piper.exe")
DEFAULT_OUTPUT_DIR = Path("output")

# ---------------------------------------------------------------------------
# Chunking parameters
# ---------------------------------------------------------------------------
# Target number of characters per TTS chunk.
# Piper works best with chunks in the 300-500 char range.
CHUNK_TARGET_CHARS = 400
# Hard upper limit – chunks are never allowed to exceed this.
CHUNK_MAX_CHARS    = 600
