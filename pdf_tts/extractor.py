"""
pdf_tts/extractor.py
--------------------
PDF → Markdown/text extraction.

Two extraction modes are supported:

  Fast mode  (--fast, default for digital PDFs)
    Uses pdftext to pull text directly from the PDF's embedded character
    stream, with column-aware reading order.
    Typical speed: < 1 second per document.
    Use this for: born-digital PDFs, research papers, articles.

  Full mode  (default without --fast)
    Uses Marker (surya ML models) for layout detection, OCR, and ordering.
    Typical speed: 5–15 minutes on CPU per document.
    Use this for: scanned PDFs, complex tables, image-heavy documents.
"""

import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import List

from .logger import log


# ---------------------------------------------------------------------------
# Column-aware block sorting
# ---------------------------------------------------------------------------

def _detect_columns(blocks: list, page_width: float) -> int:
    """
    Estimate the number of columns on a page by looking at where text blocks start.

    Strategy: collect all block left-edges (x0), cluster them. If there are
    two clear clusters separated by a gap > 20% of page width, it's two-column.
    """
    if not blocks:
        return 1

    x0_values = sorted(set(round(b["bbox"][0]) for b in blocks))
    if len(x0_values) < 2:
        return 1

    # Find the largest gap between consecutive x0 values
    gaps = [(x0_values[i + 1] - x0_values[i], i) for i in range(len(x0_values) - 1)]
    max_gap, max_gap_idx = max(gaps)

    # If the largest gap is more than 15% of page width, treat as two-column
    if max_gap > page_width * 0.15:
        split_x = (x0_values[max_gap_idx] + x0_values[max_gap_idx + 1]) / 2
        return 2, split_x

    return 1, page_width / 2


def _sort_blocks_column_aware(blocks: list, page_width: float) -> list:
    """
    Sort text blocks in correct reading order, handling multi-column layouts.

    Algorithm:
    1. Detect whether the page is single-column or two-column by analysing
       the distribution of block left-edges (x0).
    2. For single-column: sort top-to-bottom.
    3. For two-column: split blocks into left and right columns by the
       detected column boundary. Sort each column top-to-bottom independently,
       then concatenate left column first, then right column.

    This avoids the interleaving problem that pdftext's built-in sort=True
    produces on two-column PDFs (it sorts by y-coordinate globally, mixing
    left and right column lines at the same y-position).
    """
    if not blocks:
        return blocks

    result = _detect_columns(blocks, page_width)
    num_cols = result[0] if isinstance(result, tuple) else result
    split_x = result[1] if isinstance(result, tuple) else page_width / 2

    if num_cols == 1:
        return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))

    # Two-column: split, sort each independently, left before right
    left  = [b for b in blocks if b["bbox"][0] < split_x]
    right = [b for b in blocks if b["bbox"][0] >= split_x]

    left_sorted  = sorted(left,  key=lambda b: b["bbox"][1])
    right_sorted = sorted(right, key=lambda b: b["bbox"][1])

    log.debug(
        "Two-column layout detected (split x=%.0f): %d left blocks, %d right blocks",
        split_x, len(left), len(right),
    )
    return left_sorted + right_sorted


def _extract_text_from_pages(pages: list) -> str:
    """
    Convert pdftext dictionary_output pages into a single plain-text string
    using column-aware block ordering.

    Each page is sorted independently, then pages are joined with double newlines.
    """
    all_page_texts: List[str] = []

    for page in pages:
        page_width = page.get("width", 600)
        blocks = page.get("blocks", [])
        sorted_blocks = _sort_blocks_column_aware(blocks, page_width)

        block_texts: List[str] = []
        for block in sorted_blocks:
            lines = block.get("lines", [])
            line_texts: List[str] = []
            for line in lines:
                # pdftext stores text in span["text"] (not per-char)
                span_texts = []
                for span in line.get("spans", []):
                    t = span.get("text", "").strip()
                    if t:
                        span_texts.append(t)
                line_text = " ".join(span_texts).strip()
                if line_text:
                    line_texts.append(line_text)
            if line_texts:
                block_texts.append("\n".join(line_texts))

        if block_texts:
            all_page_texts.append("\n\n".join(block_texts))

    return "\n\n".join(all_page_texts)


# ---------------------------------------------------------------------------
# Fast extraction via pdftext
# ---------------------------------------------------------------------------

def extract_pdf_fast(pdf_path: Path, markdown_dir: Path) -> Path:
    """
    Extract text from a born-digital PDF using pdftext (no ML models).

    Uses column-aware block sorting to correctly handle single-column,
    two-column, and mixed-layout PDFs.

    Args:
        pdf_path:     Path to the input PDF.
        markdown_dir: Root directory for extracted text output.

    Returns:
        Path to the written .txt file.

    Raises:
        FileNotFoundError – PDF not found.
        ImportError       – pdftext not installed.
        ValueError        – Extracted text is empty.
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        from pdftext.extraction import dictionary_output
    except ImportError:
        raise ImportError(
            "pdftext is not installed.\n"
            "Install it with: pip install pdftext\n"
            "Or omit --fast to use Marker instead."
        )

    pdf_stem = pdf_path.stem
    out_dir = markdown_dir / pdf_stem
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{pdf_stem}.txt"

    # Fast-path: already extracted
    if out_file.exists():
        log.info("Text already exists, skipping fast extraction: %s", out_file)
        return out_file

    log.info("Fast extraction (pdftext, column-aware) for: %s", pdf_path.name)

    t0 = time.time()
    pages = dictionary_output(str(pdf_path), sort=False)  # we do our own sorting
    text = _extract_text_from_pages(pages)
    elapsed = time.time() - t0

    # Fix hyphenated line-breaks (e.g. "informa-\ntion" → "information")
    import re
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)

    if not text.strip():
        raise ValueError(
            f"pdftext extracted empty text from: {pdf_path}\n"
            "The PDF may be scanned or image-based. Try without --fast to use Marker with OCR."
        )

    out_file.write_text(text, encoding="utf-8")
    log.info(
        "Fast extraction complete in %.2fs – %d chars → %s",
        elapsed, len(text), out_file,
    )
    return out_file


# ---------------------------------------------------------------------------
# Full extraction via Marker
# ---------------------------------------------------------------------------

def _find_marker_cmd() -> str:
    """
    Locate the `marker_single` CLI installed in the active Python environment.

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
        "Install/repair Marker with: pip install -U marker-pdf\n"
        "Or use --fast mode for born-digital PDFs (much faster, no ML models)."
    )


def extract_pdf_marker(pdf_path: Path, markdown_dir: Path) -> Path:
    """
    Run Marker on *pdf_path* and return the path to the generated .md file.

    Output layout produced by Marker:
        <markdown_dir>/<pdf_stem>/<pdf_stem>.md

    Marker is skipped if the output file already exists (saves re-extraction
    time on repeated runs).

    Raises:
        FileNotFoundError – PDF missing, marker_single missing, or no .md produced.
        RuntimeError      – Marker exited with a non-zero return code.
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pdf_stem = pdf_path.stem
    expected_md = markdown_dir / pdf_stem / f"{pdf_stem}.md"

    if expected_md.exists():
        log.info("Markdown already exists, skipping Marker extraction: %s", expected_md)
        return expected_md

    log.info("Starting Marker extraction for: %s", pdf_path.name)
    log.info(
        "NOTE: Marker loads heavy ML models. This may take 5–15 minutes on CPU.\n"
        "      For born-digital PDFs, use --fast for near-instant extraction."
    )

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

    # Fallback search
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


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def extract_pdf(pdf_path: Path, markdown_dir: Path, fast: bool = False) -> Path:
    """
    Extract text from *pdf_path*.

    Args:
        pdf_path:     Path to the input PDF.
        markdown_dir: Root output directory for extracted text/markdown.
        fast:         If True, use pdftext (fast, no ML models).
                      If False, use Marker (slow, handles scanned PDFs).

    Returns:
        Path to the extracted text / markdown file.
    """
    if fast:
        return extract_pdf_fast(pdf_path, markdown_dir)
    return extract_pdf_marker(pdf_path, markdown_dir)


def read_markdown(md_path: Path) -> str:
    """
    Read *md_path* (or a plain .txt file) safely.
    Falls back to latin-1 on UTF-8 decode errors.

    Raises:
        ValueError – if the file is empty after reading.
    """
    try:
        text = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        log.warning("UTF-8 decode error – retrying with latin-1")
        text = md_path.read_text(encoding="latin-1")

    if not text.strip():
        raise ValueError(f"Extracted text is empty: {md_path}")

    log.info("Read %d characters from extracted file.", len(text))
    return text

