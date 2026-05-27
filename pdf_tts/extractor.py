"""
pdf_tts/extractor.py
--------------------
PDF → Markdown extraction using Marker.

Marker is invoked as a subprocess via its installed console script
`marker_single`.  The resulting .md file path is returned for the
next pipeline stage.
"""

import shutil
import subprocess
import sys
from pathlib import Path

from .logger import log


def _find_marker_cmd() -> str:
    """
    Locate the `marker_single` CLI installed in the active Python environment.

    Checks the venv Scripts/ directory first, then falls back to shutil.which.

    Raises:
        FileNotFoundError – if marker_single cannot be found anywhere.
    """
    scripts_dir = Path(sys.executable).resolve().parent
    candidates = [
        scripts_dir / "marker_single.exe",
        scripts_dir / "marker_single",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    on_path = shutil.which("marker_single")
    if on_path:
        return on_path

    raise FileNotFoundError(
        "Marker CLI 'marker_single' was not found in the active Python environment.\n"
        "Install/repair Marker with: pip install -U marker-pdf"
    )


def extract_pdf(pdf_path: Path, markdown_dir: Path) -> Path:
    """
    Run Marker on *pdf_path* and return the path to the generated .md file.

    Output layout produced by Marker:
        <markdown_dir>/<pdf_stem>/<pdf_stem>.md

    If the expected file already exists (from a previous run), Marker is
    skipped entirely to avoid the ~10-minute re-extraction cost.

    Args:
        pdf_path:     Absolute or relative path to the input PDF.
        markdown_dir: Root directory where Marker should write its output.

    Returns:
        Path to the extracted .md file.

    Raises:
        FileNotFoundError – PDF missing, marker_single missing, or no .md produced.
        RuntimeError      – Marker exited with a non-zero return code.
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pdf_stem = pdf_path.stem
    expected_md = markdown_dir / pdf_stem / f"{pdf_stem}.md"

    # Fast-path: already extracted
    if expected_md.exists():
        log.info("Markdown already exists, skipping Marker extraction: %s", expected_md)
        return expected_md

    log.info("Starting Marker extraction for: %s", pdf_path.name)

    marker_cmd = _find_marker_cmd()
    cmd = [marker_cmd, str(pdf_path), "--output_dir", str(markdown_dir)]
    log.info("Running Marker: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        log.error("Marker stderr:\n%s", result.stderr)
        raise RuntimeError(
            f"Marker extraction failed (exit code {result.returncode}). "
            "Check the log above for details."
        )

    if result.stdout.strip():
        log.info("Marker output:\n%s", result.stdout.strip())

    if expected_md.exists():
        log.info("Markdown extracted to: %s", expected_md)
        return expected_md

    # Fallback: search for any .md Marker may have placed elsewhere
    search_root = markdown_dir / pdf_stem
    md_files = list(search_root.glob("**/*.md")) if search_root.exists() else []
    if not md_files:
        md_files = list(markdown_dir.glob(f"**/{pdf_stem}*.md"))
    if not md_files:
        raise FileNotFoundError(
            f"Marker ran successfully but no markdown file was found under {markdown_dir}.\n"
            f"Marker stdout:\n{result.stdout[:1200]}\n"
            f"Marker stderr:\n{result.stderr[:1200]}"
        )

    md_path = md_files[0]
    log.info("Markdown found at: %s", md_path)
    return md_path


def read_markdown(md_path: Path) -> str:
    """
    Read *md_path* safely, falling back to latin-1 on UTF-8 decode errors.

    Returns:
        The full text content of the markdown file.

    Raises:
        ValueError – if the file is empty after reading.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        log.warning("UTF-8 decode error – retrying with latin-1")
        text = md_path.read_text(encoding="latin-1")

    if not text.strip():
        raise ValueError(f"Extracted markdown is empty: {md_path}")

    log.info("Read %d characters from markdown.", len(text))
    return text
