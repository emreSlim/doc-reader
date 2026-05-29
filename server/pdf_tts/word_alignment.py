"""
pdf_tts/word_alignment.py
-------------------------
Approximate word-level alignment between generated speech timing and PDF words.

Pipeline:
1) Build per-word timestamps from chunk-level timings.
2) Extract per-word PDF coordinates (bbox) using PyMuPDF.
3) Match spoken words to PDF words via tolerant sequence matching.
4) Write alignment JSON for UI highlighting.
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


def _build_spoken_words(chunk_timing: list[dict]) -> list[dict]:
    """Expand chunk-level timing into per-word timing (weighted by token length)."""
    spoken: list[dict] = []

    for chunk in chunk_timing:
        start = float(chunk.get("start", 0.0))
        end = float(chunk.get("end", start))
        text = str(chunk.get("text", ""))
        tokens = _tokenize_words(text)
        if not tokens:
            continue

        duration = max(end - start, 0.0)
        weights = [max(len(_normalize(tok)), 1) for tok in tokens]
        total_w = float(sum(weights))

        cursor = start
        for idx, tok in enumerate(tokens):
            share = duration * (weights[idx] / total_w) if total_w > 0 else 0.0
            w_start = cursor
            w_end = min(end, cursor + share)
            spoken.append(
                {
                    "text": tok,
                    "norm": _normalize(tok),
                    "start": round(w_start, 3),
                    "end": round(w_end, 3),
                }
            )
            cursor = w_end

    return spoken


def _build_spoken_words_forced(audio_path: Path) -> list[dict] | None:
    """
    Try to produce word timings using faster-whisper.

    Returns None if faster-whisper is unavailable or transcription fails.
    """
    try:
        from faster_whisper import WhisperModel
    except Exception:
        return None

    try:
        model = WhisperModel("small.en", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(
            str(audio_path),
            language="en",
            beam_size=1,
            word_timestamps=True,
            vad_filter=True,
        )

        spoken: list[dict] = []
        for seg in segments:
            for w in seg.words or []:
                token = (w.word or "").strip()
                norm = _normalize(token)
                if not norm:
                    continue
                spoken.append(
                    {
                        "text": token,
                        "norm": norm,
                        "start": round(float(w.start or 0.0), 3),
                        "end": round(float(w.end or 0.0), 3),
                    }
                )

        if not spoken:
            return None
        return spoken
    except Exception:
        log.exception("Forced alignment via faster-whisper failed; using fallback timing")
        return None


def _extract_pdf_words(pdf_path: Path) -> tuple[list[dict], list[dict]]:
    """Return ordered PDF words and page dimensions."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ImportError("PyMuPDF is required for word alignment: pip install pymupdf") from exc

    doc = fitz.open(str(pdf_path))
    pdf_words: list[dict] = []
    pages: list[dict] = []

    try:
        for page_idx, page in enumerate(doc):
            width = float(page.rect.width)
            height = float(page.rect.height)
            pages.append(
                {
                    "page_index": page_idx,
                    "width": width,
                    "height": height,
                }
            )

            # tuples: x0, y0, x1, y1, "word", block_no, line_no, word_no
            words = page.get_text("words", sort=True)
            for x0, y0, x1, y1, word, *_ in words:
                norm = _normalize(str(word))
                if not norm:
                    continue
                pdf_words.append(
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

    return pdf_words, pages


def _extract_words_from_metadata(metadata_path: Path, pdf_path: Path) -> tuple[list[dict], list[dict]]:
    """
    Build ordered words from extractor metadata kept blocks.

    This follows the same column-aware block order used by extraction while
    keeping real per-word bboxes from PyMuPDF.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise ImportError("PyMuPDF is required for word alignment: pip install pymupdf") from exc

    data = json.loads(metadata_path.read_text(encoding="utf-8"))
    pages_in = data.get("pages", [])
    words_out: list[dict] = []
    pages_out: list[dict] = []

    if not pdf_path.exists():
        # Fallback for older metadata schema where source path is embedded.
        pdf_path = Path(data.get("source_pdf", ""))
    if not pdf_path.exists():
        raise FileNotFoundError(f"Source PDF not found for metadata alignment: {pdf_path}")

    doc = fitz.open(str(pdf_path))

    def _overlap_ratio(a: list[float], b: list[float]) -> float:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        ix0 = max(ax0, bx0)
        iy0 = max(ay0, by0)
        ix1 = min(ax1, bx1)
        iy1 = min(ay1, by1)
        iw = max(0.0, ix1 - ix0)
        ih = max(0.0, iy1 - iy0)
        inter = iw * ih
        a_area = max(1.0, (ax1 - ax0) * (ay1 - ay0))
        return inter / a_area

    try:
        for page in pages_in:
            page_idx = int(page.get("page_index", 0))
            page_w = float(page.get("width", 1.0)) or 1.0
            page_h = float(page.get("height", 1.0)) or 1.0
            pages_out.append({"page_index": page_idx, "width": page_w, "height": page_h})

            fitz_page = doc[page_idx]
            # tuples: x0, y0, x1, y1, "word", block_no, line_no, word_no
            page_words_raw = fitz_page.get_text("words", sort=True)
            available: list[dict] = []
            for x0, y0, x1, y1, word, block_no, line_no, word_no in page_words_raw:
                norm = _normalize(str(word))
                if not norm:
                    continue
                available.append(
                    {
                        "text": str(word),
                        "norm": norm,
                        "bbox": [float(x0), float(y0), float(x1), float(y1)],
                        "sort_key": (int(block_no), int(line_no), int(word_no), float(y0), float(x0)),
                        "used": False,
                    }
                )

            for block in page.get("blocks", []):
                if not block.get("kept", False):
                    continue

                block_bbox = [float(v) for v in block.get("bbox", [0, 0, 0, 0])]
                in_block: list[dict] = []

                for w in available:
                    if w["used"]:
                        continue
                    ratio = _overlap_ratio(w["bbox"], block_bbox)
                    if ratio >= 0.5:
                        in_block.append(w)

                in_block.sort(key=lambda item: item["sort_key"])

                for w in in_block:
                    w["used"] = True
                    x0, y0, x1, y1 = w["bbox"]
                    words_out.append(
                        {
                            "text": w["text"],
                            "norm": w["norm"],
                            "page_index": page_idx,
                            "bbox": [x0, y0, x1, y1],
                            "bbox_norm": [
                                x0 / page_w,
                                y0 / page_h,
                                x1 / page_w,
                                y1 / page_h,
                            ],
                        }
                    )
    finally:
        doc.close()

    return words_out, pages_out


def _match_spoken_to_pdf(spoken_words: list[dict], pdf_words: list[dict], lookahead: int = 8) -> list[dict]:
    """
    Tolerant monotonic sequence matching.

    We keep order and allow small skips on either side to handle minor tokenizer
    differences and punctuation variance.
    """
    aligned: list[dict] = []
    i = 0  # spoken
    j = 0  # pdf

    while i < len(spoken_words) and j < len(pdf_words):
        s = spoken_words[i]
        p = pdf_words[j]

        if s["norm"] == p["norm"]:
            aligned.append(
                {
                    "text": p["text"],
                    "start": s["start"],
                    "end": s["end"],
                    "page_index": p["page_index"],
                    "bbox": p["bbox"],
                    "bbox_norm": p["bbox_norm"],
                }
            )
            i += 1
            j += 1
            continue

        # Try to find spoken token in upcoming PDF tokens.
        found_pdf = None
        for k in range(1, lookahead + 1):
            if j + k < len(pdf_words) and pdf_words[j + k]["norm"] == s["norm"]:
                found_pdf = j + k
                break

        if found_pdf is not None:
            j = found_pdf
            continue

        # Try to find PDF token in upcoming spoken tokens.
        found_spoken = None
        for k in range(1, lookahead + 1):
            if i + k < len(spoken_words) and spoken_words[i + k]["norm"] == p["norm"]:
                found_spoken = i + k
                break

        if found_spoken is not None:
            i = found_spoken
            continue

        # Substitute both if no near match.
        i += 1
        j += 1

    return aligned


def build_word_alignment(
    *,
    pdf_path: Path,
    chunk_timing: list[dict],
    output_dir: Path,
    audio_path: Path | None = None,
    extraction_metadata_path: Path | None = None,
) -> tuple[dict, Path]:
    """Build and persist word alignment JSON for UI use."""
    spoken_words = None
    timing_source = "estimated-chunk"

    if audio_path and audio_path.exists():
        spoken_words = _build_spoken_words_forced(audio_path)
        if spoken_words:
            timing_source = "forced-whisper"

    if not spoken_words:
        spoken_words = _build_spoken_words(chunk_timing)

    pdf_words: list[dict]
    pages: list[dict]
    if extraction_metadata_path and extraction_metadata_path.exists():
        try:
            pdf_words, pages = _extract_words_from_metadata(extraction_metadata_path, pdf_path)
            log.info("Using extraction metadata for alignment word source: %s", extraction_metadata_path)
        except Exception:
            log.exception("Failed to parse extraction metadata; falling back to PyMuPDF words")
            pdf_words, pages = _extract_pdf_words(pdf_path)
    else:
        pdf_words, pages = _extract_pdf_words(pdf_path)

    aligned_words = _match_spoken_to_pdf(spoken_words, pdf_words)

    payload = {
        "pdf_path": str(pdf_path),
        "timing_source": timing_source,
        "spoken_word_count": len(spoken_words),
        "pdf_word_count": len(pdf_words),
        "aligned_word_count": len(aligned_words),
        "coverage": round((len(aligned_words) / len(spoken_words)) * 100, 2) if spoken_words else 0.0,
        "pages": pages,
        "words": aligned_words,
    }

    align_dir = output_dir / "alignment"
    align_dir.mkdir(parents=True, exist_ok=True)
    out_path = align_dir / f"{pdf_path.stem}_word_alignment.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    log.info(
        "Word alignment complete: %d/%d words mapped (%.2f%%)",
        len(aligned_words),
        len(spoken_words),
        payload["coverage"],
    )

    return payload, out_path
