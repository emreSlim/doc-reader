"""
pdf_tts/utils.py
----------------
Shared filesystem helpers used across multiple modules.
"""

from pathlib import Path
from .logger import log


def ensure_dirs(output_dir: Path) -> dict:
    """
    Create all required output sub-directories under *output_dir* and
    return a dict mapping logical names to their resolved Path objects.

    Sub-directories created:
        markdown/   – Marker-extracted .md files
        chunks/     – Per-chunk .txt files (for inspection / debugging)
        audio/      – Intermediate per-chunk .wav files
        final/      – Merged audiobook output
    """
    dirs = {
        "markdown": output_dir / "markdown",
        "chunks":   output_dir / "chunks",
        "audio":    output_dir / "audio",
        "final":    output_dir / "final",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    log.info("Output directories ready under: %s", output_dir)
    return dirs
