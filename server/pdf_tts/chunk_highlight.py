"""
pdf_tts/chunk_highlight.py
--------------------------
Build per-chunk PDF highlight regions using text matching against PDF words.

This is intentionally independent from ASR/word-timestamp alignment. It maps
chunk text (from chunk_timing) to PDF word coordinates and produces one region
per matched chunk for stable UI highlighting.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .logger import log


def _normalize(token: str) -> str:
    token = token.lower().strip()
    token = token.replace("’", "'")
    token = re.sub(r"[^a-z0-9']+", "", token)
    return token


def _tokenize_words(text: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z0-9']+", text) if _normalize(t)]


def _order_page_words(raw_words: list[tuple], page_width: float) -> list[tuple]:
    """
    Return words in a reading order that handles multi-column layouts.

    For 2-column pages, read left column top->bottom first, then right column.
    For single-column pages, keep top->bottom, left->right ordering.
    """
    if not raw_words:
        return []

    # Group by text block to preserve line / word sequencing inside each block.
    blocks: dict[int, dict] = {}
    for w in raw_words:
        # x0, y0, x1, y1, word, block_no, line_no, word_no
        x0, y0, x1, y1, _, block_no, line_no, word_no = w
        b = blocks.setdefault(
            int(block_no),
            {
                "x0": float(x0),
                "y0": float(y0),
                "x1": float(x1),
                "y1": float(y1),
                "words": [],
            },
        )
        b["x0"] = min(b["x0"], float(x0))
        b["y0"] = min(b["y0"], float(y0))
        b["x1"] = max(b["x1"], float(x1))
        b["y1"] = max(b["y1"], float(y1))
        b["words"].append((int(line_no), int(word_no), w))

    block_list = list(blocks.values())

    # Heuristic 2-column detection from block centers around page midpoint.
    mid_x = page_width * 0.5
    gap = max(20.0, page_width * 0.04)

    left_blocks = [b for b in block_list if ((b["x0"] + b["x1"]) * 0.5) < (mid_x - gap)]
    right_blocks = [b for b in block_list if ((b["x0"] + b["x1"]) * 0.5) > (mid_x + gap)]
    is_two_column = bool(left_blocks and right_blocks)

    ordered_blocks: list[dict]
    if is_two_column:
        # Column-major reading order.
        left_sorted = sorted(left_blocks, key=lambda b: (b["y0"], b["x0"]))
        right_sorted = sorted(right_blocks, key=lambda b: (b["y0"], b["x0"]))

        # Blocks near the center/gutter are rare; place by visual flow.
        center_blocks = [
            b
            for b in block_list
            if (mid_x - gap) <= ((b["x0"] + b["x1"]) * 0.5) <= (mid_x + gap)
        ]
        center_sorted = sorted(center_blocks, key=lambda b: (b["y0"], b["x0"]))

        ordered_blocks = left_sorted + center_sorted + right_sorted
    else:
        ordered_blocks = sorted(block_list, key=lambda b: (b["y0"], b["x0"]))

    ordered_words: list[tuple] = []
    for b in ordered_blocks:
        for _, _, w in sorted(b["words"], key=lambda t: (t[0], t[1])):
            ordered_words.append(w)

    return ordered_words


def _extract_pdf_words(pdf_path: Path) -> tuple[list[dict], list[dict]]:
    """Return ordered PDF words and page dimensions."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ImportError("PyMuPDF is required for chunk highlights: pip install pymupdf") from exc

    doc = fitz.open(str(pdf_path))
    words_out: list[dict] = []
    pages_out: list[dict] = []

    try:
        for page_idx, page in enumerate(doc):
            width = float(page.rect.width)
            height = float(page.rect.height)
            pages_out.append(
                {
                    "page_index": page_idx,
                    "width": width,
                    "height": height,
                }
            )

            # tuples: x0, y0, x1, y1, "word", block_no, line_no, word_no
            # Read unsorted and apply column-aware ordering ourselves.
            words = page.get_text("words", sort=False)
            words = _order_page_words(words, width)
            for x0, y0, x1, y1, word, *_ in words:
                norm = _normalize(str(word))
                if not norm:
                    continue
                words_out.append(
                    {
                        "text": str(word),
                        "norm": norm,
                        "page_index": page_idx,
                        "bbox": [float(x0), float(y0), float(x1), float(y1)],
                        "bbox_norm": [
                            float(x0) / width if width else 0.0,
                            float(y0) / height if height else 0.0,
                            float(x1) / width if width else 0.0,
                            float(y1) / height if height else 0.0,
                        ],
                    }
                )
    finally:
        doc.close()

    return words_out, pages_out


def _match_chunk_tokens_to_pdf_words(chunk_tokens: list[str], pdf_words: list[dict], lookahead: int = 6) -> dict | None:
    """
    Find best local monotonic match for one chunk against ordered PDF words.

    Returns dict with matched word indexes and score, or None if weak match.
    """
    if not chunk_tokens or not pdf_words:
        return None

    pdf_norm = [w["norm"] for w in pdf_words]
    n = len(pdf_norm)
    m = len(chunk_tokens)

    best: dict | None = None

    # Try each possible starting point; constrain scan window for speed.
    for start in range(n):
        i = 0
        j = start
        max_j = min(n, start + max(m * 3, 24))
        matched_idxs: list[int] = []

        while i < m and j < max_j:
            if chunk_tokens[i] == pdf_norm[j]:
                matched_idxs.append(j)
                i += 1
                j += 1
                continue

            found = False
            for k in range(1, lookahead + 1):
                cand = j + k
                if cand < max_j and chunk_tokens[i] == pdf_norm[cand]:
                    j = cand
                    found = True
                    break

            if found:
                continue

            # Skip one chunk token when no local PDF match.
            i += 1

        if not matched_idxs:
            continue

        score = len(matched_idxs) / max(m, 1)
        span = matched_idxs[-1] - matched_idxs[0] + 1

        cand = {
            "score": score,
            "span": span,
            "matched_word_indexes": matched_idxs,
            "matched_tokens": len(matched_idxs),
            "query_tokens": m,
        }

        if best is None:
            best = cand
        else:
            # Higher score first, then tighter span.
            if cand["score"] > best["score"] or (
                cand["score"] == best["score"] and cand["span"] < best["span"]
            ):
                best = cand

    if not best:
        return None

    min_token_matches = min(4, max(1, len(chunk_tokens)))
    if best["matched_tokens"] < min_token_matches or best["score"] < 0.33:
        return None

    return best


def build_chunk_highlights(
    *,
    pdf_path: Path,
    chunk_timing: list[dict],
    output_dir: Path,
) -> tuple[dict, Path]:
    """Build and persist chunk highlight regions for UI use."""
    log.debug("[chunk-highlight] Starting | pdf=%s chunks=%d", pdf_path.name, len(chunk_timing))

    pdf_words, pages = _extract_pdf_words(pdf_path)
    log.debug("[chunk-highlight] Extracted %d PDF words across %d pages", len(pdf_words), len(pages))

    highlights: list[dict] = []

    for chunk in chunk_timing:
        chunk_idx = int(chunk.get("index", -1))
        text = str(chunk.get("text", ""))
        if chunk_idx < 0 or not text.strip():
            continue

        chunk_tokens = [_normalize(t) for t in _tokenize_words(text)]
        chunk_tokens = [t for t in chunk_tokens if t]
        if not chunk_tokens:
            continue

        match = _match_chunk_tokens_to_pdf_words(chunk_tokens, pdf_words)
        if not match:
            continue

        words = [pdf_words[i] for i in match["matched_word_indexes"]]
        page_ids = {int(w["page_index"]) for w in words}
        if len(page_ids) != 1:
            # For per-page jobs this should not happen; skip ambiguous result.
            continue

        page_index = next(iter(page_ids))
        x0 = min(w["bbox_norm"][0] for w in words)
        y0 = min(w["bbox_norm"][1] for w in words)
        x1 = max(w["bbox_norm"][2] for w in words)
        y1 = max(w["bbox_norm"][3] for w in words)

        highlights.append(
            {
                "chunk_index": chunk_idx,
                "page_index": page_index,
                "bbox_norm": [x0, y0, x1, y1],
                "polygon_norm": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                "match_score": round(float(match["score"]), 4),
                "matched_tokens": int(match["matched_tokens"]),
                "query_tokens": int(match["query_tokens"]),
            }
        )

    payload = {
        "pdf_path": str(pdf_path),
        "chunk_count": len(chunk_timing),
        "highlight_count": len(highlights),
        "coverage": round((len(highlights) / len(chunk_timing)) * 100, 2) if chunk_timing else 0.0,
        "pages": pages,
        "highlights": highlights,
    }

    out_dir = output_dir / "alignment"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pdf_path.stem}_chunk_highlights.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(
        "Chunk highlight mapping complete: %d/%d chunks mapped (%.2f%%)",
        len(highlights),
        len(chunk_timing),
        payload["coverage"],
    )

    return payload, out_path
