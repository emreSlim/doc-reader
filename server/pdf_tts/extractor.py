"""
pdf_tts/extractor.py
--------------------
PDF → Markdown/text extraction.

This module uses Marker for extraction, layout detection, OCR, and reading
order reconstruction. It is slower than simple text extraction, but produces
better results for scanned PDFs and mixed-layout documents.
"""

import shutil
import subprocess
import sys
import time
import re
import json
import os
from pathlib import Path
from typing import List

from .layout_filter import block_is_kept_by_layout, detect_layout_regions
from .logger import log


# ---------------------------------------------------------------------------
# Marker performance tuning
# ---------------------------------------------------------------------------
# Disable OCR for faster text-only extraction on native PDFs.
# Maps to marker_single flag: --disable_ocr
MARKER_DISABLE_OCR = True


# ---------------------------------------------------------------------------
# Column-aware block sorting
# ---------------------------------------------------------------------------

TOP_MARGIN_PCT = 0.08
BOTTOM_MARGIN_PCT = 0.12
REPEATED_MARGIN_MIN_COUNT = 2


def _normalize_line_fingerprint(text: str) -> str:
    """Normalize text for repeated-header/footer detection."""
    t = text.lower()
    t = re.sub(r"\d+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _block_to_text(block: dict) -> str:
    """Flatten a pdftext block into plain text."""
    lines = block.get("lines", [])
    line_texts: List[str] = []
    for line in lines:
        span_texts = []
        for span in line.get("spans", []):
            t = span.get("text", "").strip()
            if t:
                span_texts.append(t)
        line_text = " ".join(span_texts).strip()
        if line_text:
            line_texts.append(line_text)
    return "\n".join(line_texts).strip()


def _metadata_path_for_text(text_path: Path) -> Path:
    """Return companion metadata path for an extracted text file."""
    return text_path.with_name(f"{text_path.stem}_meta.json")


def _collect_repeated_margin_fingerprints(pages: list) -> set[str]:
    """
    Collect repeated top/bottom margin texts across pages.

    This is content-agnostic and catches running headers/footers even when
    wording differs only by page number (numbers are stripped in fingerprint).
    """
    counts: dict[str, int] = {}
    for page in pages:
        page_height = page.get("height", 800) or 800
        for block in page.get("blocks", []):
            bbox = block.get("bbox", [0, 0, 0, 0])
            y_center_pct = ((bbox[1] + bbox[3]) / 2) / page_height
            in_margin = y_center_pct < TOP_MARGIN_PCT or y_center_pct > (1 - BOTTOM_MARGIN_PCT)
            if not in_margin:
                continue

            text = _block_to_text(block)
            if not text:
                continue

            fp = _normalize_line_fingerprint(text)
            if not fp:
                continue
            counts[fp] = counts.get(fp, 0) + 1

    repeated = {
        fp for fp, c in counts.items()
        if c >= REPEATED_MARGIN_MIN_COUNT
    }
    if repeated:
        log.info("Detected %d repeated margin fingerprints (headers/footers).", len(repeated))
    return repeated

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


def _extract_text_from_pages(
    pages: list,
    *,
    layout_regions_by_page: dict[int, list[dict]] | None = None,
) -> tuple[str, dict]:
    """
    Convert pdftext dictionary_output pages into a single plain-text string
    using column-aware block ordering.

    Each page is sorted independently, then pages are joined with double newlines.
    Returns both plain text and structured metadata for future UI use.
    """
    all_page_texts: List[str] = []
    repeated_margin_fps = _collect_repeated_margin_fingerprints(pages)
    metadata_pages: list[dict] = []

    for page_idx, page in enumerate(pages):
        page_width = page.get("width", 600)
        page_height = page.get("height", 800) or 800
        blocks = page.get("blocks", [])
        sorted_blocks = _sort_blocks_column_aware(blocks, page_width)
        page_layout_regions = (layout_regions_by_page or {}).get(page_idx, [])

        block_texts: List[str] = []
        metadata_blocks: list[dict] = []
        for block in sorted_blocks:
            text = _block_to_text(block)
            if not text:
                continue

            bbox = block.get("bbox", [0, 0, 0, 0])
            y_center_pct = ((bbox[1] + bbox[3]) / 2) / page_height
            word_count = len(text.split())
            keep_block = True
            drop_reason = None
            layout_matches: list[dict] = []

            if page_layout_regions:
                keep_block, layout_matches = block_is_kept_by_layout(bbox, page_layout_regions)
                if not keep_block:
                    drop_reason = "layout-filter"

            # 1) Remove repeated top/bottom margin boilerplate across pages.
            fp = _normalize_line_fingerprint(text)
            if keep_block and fp in repeated_margin_fps:
                keep_block = False
                drop_reason = "repeated-margin"

            # 2) Generic geometric suppression for short margin snippets.
            #    - top margin on pages after first: likely running header
            #    - bottom margin on any page: likely footer/page number/publisher note
            if keep_block and page_idx > 0 and y_center_pct < TOP_MARGIN_PCT and word_count <= 20:
                keep_block = False
                drop_reason = "top-margin"
            if keep_block and y_center_pct > (1 - BOTTOM_MARGIN_PCT) and word_count <= 35:
                keep_block = False
                drop_reason = "bottom-margin"

            metadata_blocks.append(
                {
                    "bbox": [float(v) for v in bbox],
                    "text": text,
                    "kept": keep_block,
                    "drop_reason": drop_reason,
                    "layout_matches": layout_matches,
                }
            )

            if not keep_block:
                continue

            block_texts.append(text)

        if block_texts:
            all_page_texts.append("\n\n".join(block_texts))

        metadata_pages.append(
            {
                "page_index": page_idx,
                "width": float(page_width),
                "height": float(page_height),
                "layout_regions": page_layout_regions,
                "blocks": metadata_blocks,
            }
        )

    return "\n\n".join(all_page_texts), {"pages": metadata_pages}


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
        "Install/repair Marker with: pip install -U marker-pdf"
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
        "NOTE: Marker loads heavy ML models. This may take 5–15 minutes on CPU."
    )

    marker_cmd = _find_marker_cmd()
    cmd = [marker_cmd, str(pdf_path), "--output_dir", str(markdown_dir)]
    if MARKER_DISABLE_OCR:
        cmd.append("--disable_ocr")
        log.info("Marker OCR disabled (--disable_ocr): text extraction only")
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

def extract_pdf(pdf_path: Path, markdown_dir: Path) -> Path:
    """
    Extract text from *pdf_path* using Marker.

    Args:
        pdf_path:     Path to the input PDF.
        markdown_dir: Root output directory for extracted text/markdown.

    Returns:
        Path to the extracted markdown file.
    """
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


def get_extraction_metadata_path(text_path: Path) -> Path:
    """Public helper returning the companion metadata path for extracted text."""
    return _metadata_path_for_text(text_path)

