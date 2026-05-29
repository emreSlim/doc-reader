"""
pdf_tts/cleaner.py
------------------
Light text cleaning for Marker-extracted PDF content, preparing it for TTS narration.

This module performs:
    - optional References/Bibliography truncation
    - markdown syntax removal (headings, bold, italic, links, code blocks, etc.)
    - basic whitespace normalization
"""

import re

from .logger import log

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_REFERENCE_HEADERS = re.compile(
    r"^(#{1,6}\s*)?(references?|bibliography|works\s+cited|further\s+reading"
    r"|acknowledgements?|appendix|footnotes?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _remove_references_section(text: str) -> str:
    """Truncate at the first References/Bibliography/Acknowledgements heading."""
    match = _REFERENCE_HEADERS.search(text)
    if match:
        log.info("Section boundary '%s' found at char %d – truncating.", match.group().strip(), match.start())
        return text[: match.start()]
    return text


def _normalize_list_items_for_tts(text: str) -> str:
    """
    Convert markdown list items into sentence-like lines for better narration.

    Example:
      - Item A
      - Item B
    becomes:
      Item A.
      Item B.
    """
    out_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        m = re.match(r"^\s*(?:[-+*]|\d+[\.)])\s+(.+?)\s*$", line)
        if not m:
            out_lines.append(raw_line)
            continue

        item = m.group(1).strip()
        if not item:
            out_lines.append("")
            continue

        if not re.search(r"[.!?:;]$", item):
            item = f"{item}."
        out_lines.append(item)

    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_marker_text(text: str, remove_references: bool = True) -> str:
    """
    Light cleanup for Marker output.

    Keeps Marker's extracted content mostly intact, but removes Markdown syntax
    and other obvious narration artifacts so TTS doesn't read characters like
    `#`, `*`, backticks, or raw link markup aloud.
    """
    if remove_references:
        text = _remove_references_section(text)

    # Remove the most common Markdown syntax while preserving the words.
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)          # headings
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)      # hr rules
    text = re.sub(r"```[\s\S]*?```", "", text)                          # fenced code
    text = re.sub(r"`([^`\n]+)`", r"\1", text)                         # inline code
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)                     # images
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)         # markdown links
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)           # bold/italic
    text = re.sub(r"_{1,3}([^_\n]+)_{1,3}", r"\1", text)               # bold/italic

    # Add natural pauses for markdown list items.
    text = _normalize_list_items_for_tts(text)

    # Basic whitespace normalization.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)
    text = text.strip()

    if not text:
        raise ValueError("Text is empty after Marker cleanup.")

    log.info("Light-cleaned Marker text: %d characters remaining.", len(text))
    return text

