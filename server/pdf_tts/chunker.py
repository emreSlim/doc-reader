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

    sentences = nltk.sent_tokenize(text)
    log.info("Tokenized into %d sentences.", len(sentences))

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Single sentence exceeds max_chars → split at clause boundaries
        if len(sentence) > max_chars:
            if current:
                chunks.append(" ".join(current))
                current, current_len = [], 0
            sub_parts = re.split(r"(?<=[;,])\s+", sentence)
            sub_buf: list[str] = []
            sub_len = 0
            for part in sub_parts:
                if sub_len + len(part) + 1 > max_chars and sub_buf:
                    chunks.append(" ".join(sub_buf))
                    sub_buf, sub_len = [], 0
                sub_buf.append(part)
                sub_len += len(part) + 1
            if sub_buf:
                chunks.append(" ".join(sub_buf))
            continue

        # Normal accumulation
        if current_len + len(sentence) + 1 > target_chars and current:
            chunks.append(" ".join(current))
            current, current_len = [], 0

        current.append(sentence)
        current_len += len(sentence) + 1

    if current:
        chunks.append(" ".join(current))

    chunks = [c.strip() for c in chunks if c.strip()]
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
