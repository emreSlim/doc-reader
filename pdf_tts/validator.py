"""
pdf_tts/validator.py
--------------------
Pre-flight dependency checks.

Validates that all required external tools (FFmpeg, piper.exe) and
model files are present before the pipeline starts, giving the user
clear, actionable error messages instead of cryptic OS errors.
"""

import os
import subprocess
from pathlib import Path

from .logger import log


# Known WinGet install path for FFmpeg on Windows.
# Used as an automatic fallback when ffmpeg is not on PATH.
_WINGET_FFMPEG = Path(os.environ.get("LOCALAPPDATA", "")) / (
    "Microsoft/WinGet/Packages/"
    "Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe/"
    "ffmpeg-8.1.1-essentials_build/bin/ffmpeg.exe"
)


def _ensure_ffmpeg() -> bool:
    """
    Return True if FFmpeg is usable.

    First tries the system PATH. If not found, probes the standard WinGet
    install location and — if found there — injects the bin/ directory into
    os.environ["PATH"] so all subsequent subprocess calls can find it.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True
        )
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass

    if _WINGET_FFMPEG.exists():
        bin_dir = str(_WINGET_FFMPEG.parent)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        log.info("FFmpeg found via WinGet, added to PATH: %s", bin_dir)
        return True

    return False


def validate_dependencies(piper_exe: Path, model_path: Path) -> None:
    """
    Check all external dependencies before the pipeline runs.

    Raises:
        EnvironmentError – with a consolidated list of all missing items.
    """
    errors: list[str] = []

    # ── FFmpeg ───────────────────────────────────────────────────────────────
    if not _ensure_ffmpeg():
        errors.append(
            "FFmpeg not found on PATH.\n"
            "  -> Download from https://ffmpeg.org/download.html\n"
            "  -> Extract and add the bin/ folder to your System PATH\n"
            "  -> Then open a new terminal and verify with: ffmpeg -version"
        )

    # ── piper.exe ────────────────────────────────────────────────────────────
    if not piper_exe.exists():
        errors.append(
            f"piper.exe not found at: {piper_exe}\n"
            "  -> Download from https://github.com/rhasspy/piper/releases"
        )

    # ── Piper model ──────────────────────────────────────────────────────────
    if not model_path.exists():
        errors.append(
            f"Piper model not found at: {model_path}\n"
            "  -> Download a model from https://github.com/rhasspy/piper/releases\n"
            "  -> Place the .onnx and .onnx.json files in the models/ directory"
        )
    else:
        json_path = model_path.with_suffix(".onnx.json")
        if not json_path.exists():
            errors.append(
                f"Piper model config not found: {json_path}\n"
                "  -> Download the .onnx.json file alongside the .onnx model"
            )

    if errors:
        msg = "\n".join(f"  x {e}" for e in errors)
        raise EnvironmentError(f"Dependency check failed:\n{msg}")

    log.info("All dependencies verified.")
