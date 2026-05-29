"""
pdf_tts/chunker.py
------------------
Sentence-aware text chunking for TTS generation.

Uses NLTK's sentence tokeniser to split cleaned text into chunks that
are sized appropriately for Piper (300-600 characters).  Sentences are
never cut mid-way; over-long sentences are split at natural clause
boundaries (semicolons, commas) as a last resort.
"""

import re
from pathlib import Path

import nltk

from .config import CHUNK_TARGET_CHARS, CHUNK_MAX_CHARS
from .logger import log


# ---------------------------------------------------------------------------
# NLTK bootstrap
# ---------------------------------------------------------------------------

def _ensure_nltk_punkt() -> None:
    """Download NLTK punkt tokenizer data if not already present."""
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
        except LookupError:
            log.info("Downloading NLTK resource: %s", resource)
            nltk.download(resource, quiet=True)


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Split an over-long sentence at clause boundaries when possible."""
    sub_parts = re.split(r"(?<=[;,])\s+", sentence)
    sub_buf: list[str] = []
    sub_len = 0
    chunks: list[str] = []
    for part in sub_parts:
        if sub_len + len(part) + 1 > max_chars and sub_buf:
            chunks.append(" ".join(sub_buf))
            sub_buf, sub_len = [], 0
        sub_buf.append(part)
        sub_len += len(part) + 1
    if sub_buf:
        chunks.append(" ".join(sub_buf))
    return chunks


def _looks_like_heading(block: str) -> bool:
    """Heuristic: short standalone title-ish blocks should end with a pause."""
    words = block.split()
    if not words:
        return False
    if "\n" in block:
        return False
    if len(block) > 120 or len(words) > 14:
        return False
    return not re.search(r"[.!?:]$", block)


def _build_paragraph_units(text: str, max_chars: int) -> list[str]:
    """
    Convert text into paragraph-aware speech units.

    Blank-line-separated blocks remain distinct so headings and new paragraphs
    keep natural pauses even when they end up in the same Piper chunk.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n+", text) if b.strip()]
    units: list[str] = []

    for block in blocks:
        flat = " ".join(line.strip() for line in block.splitlines() if line.strip())
        if not flat:
            continue

        if _looks_like_heading(flat):
            flat = f"{flat}."

        sentences = [s.strip() for s in nltk.sent_tokenize(flat) if s.strip()]
        if not sentences:
            sentences = [flat]

        current: list[str] = []
        current_len = 0
        for sentence in sentences:
            if len(sentence) > max_chars:
                if current:
                    units.append(" ".join(current))
                    current, current_len = [], 0
                units.extend(_split_long_sentence(sentence, max_chars))
                continue

            if current_len + len(sentence) + 1 > max_chars and current:
                units.append(" ".join(current))
                current, current_len = [], 0

            current.append(sentence)
            current_len += len(sentence) + 1

        if current:
            units.append(" ".join(current))

    return units


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_text(
    text: str,
    target_chars: int = CHUNK_TARGET_CHARS,
    max_chars: int = CHUNK_MAX_CHARS,
) -> list:
    """
    Split *text* into speech-friendly chunks.

    Strategy:
    - Tokenize into sentences with NLTK.
    - Greedily accumulate sentences until the chunk reaches *target_chars*.
    - A sentence that would push a chunk over *max_chars* starts a new chunk.
    - A single sentence longer than *max_chars* is split at clause
      boundaries (semicolons/commas) rather than mid-word.

    Args:
        text:         Cleaned plain text (output of cleaner.clean_text).
        target_chars: Aim for chunks this long (default 400).
        max_chars:    Hard upper limit per chunk (default 600).

    Returns:
        List of non-empty string chunks, ready to feed to Piper.
    """
    _ensure_nltk_punkt()

    units = _build_paragraph_units(text, max_chars=max_chars)
    log.info("Prepared %d paragraph-aware speech units.", len(units))

    # Each blank-line-separated block in the markdown becomes its own chunk.
    chunks = [u.strip() for u in units if u.strip()]
    log.info("Created %d text chunks.", len(chunks))
    return chunks


def save_chunks(chunks: list, chunks_dir: Path, pdf_stem: str) -> list:
    """
    Write each chunk to a numbered .txt file under *chunks_dir*.

    These files are not used by the pipeline itself but are useful for
    inspecting exactly what text was sent to Piper.

    Returns:
        List of Path objects for the written files.
    """
    chunk_files: list[Path] = []
    for i, chunk in enumerate(chunks):
        p = chunks_dir / f"{pdf_stem}_chunk_{i:04d}.txt"
        p.write_text(chunk, encoding="utf-8")
        chunk_files.append(p)
    log.info("Saved %d chunk text files to: %s", len(chunks), chunks_dir)
    return chunk_files
