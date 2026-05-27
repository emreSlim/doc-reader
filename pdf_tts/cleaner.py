"""
pdf_tts/cleaner.py
------------------
Text cleaning pipeline for TTS-ready narration.

Takes raw Marker-extracted markdown and produces clean, natural-sounding
prose by removing:
  - Markdown formatting symbols
  - Inline citations  ([1], [Smith 2020], etc.)
  - Figure / Table captions
  - Standalone page numbers
  - Bare URLs and image tags
  - Optionally the entire References / Bibliography section
"""

import re
from .logger import log

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_REFERENCE_HEADERS = re.compile(
    r"^#+\s*(references?|bibliography|works\s+cited|further\s+reading)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _remove_references_section(text: str) -> str:
    """
    Truncate text at the first References / Bibliography heading so that
    boilerplate citation lists are never narrated.
    """
    match = _REFERENCE_HEADERS.search(text)
    if match:
        log.info("References section found at char %d – removing.", match.start())
        return text[: match.start()]
    return text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_text(text: str, remove_references: bool = True) -> str:
    """
    Clean *text* for clean TTS narration.

    Processing order:
      1. Optionally strip the References / Bibliography section.
      2. Remove ATX headings (keep words, drop # symbols).
      3. Remove horizontal rules.
      4. Remove markdown tables.
      5. Remove fenced and inline code blocks.
      6. Remove images and hyperlinks (keep link text).
      7. Remove bare URLs.
      8. Remove bold / italic markers.
      9. Remove numeric and author-year citations.
      10. Remove superscript footnote numbers.
      11. Remove Figure / Table / Equation captions.
      12. Remove standalone page-number lines.
      13. Normalise whitespace and blank lines.

    Args:
        text:              Raw markdown / extracted text.
        remove_references: If True, drop everything from the first
                           References heading onward.

    Returns:
        Cleaned plain-text string ready for sentence tokenisation.

    Raises:
        ValueError – if the result is empty after cleaning.
    """
    if remove_references:
        text = _remove_references_section(text)

    # ── Markdown structure ───────────────────────────────────────────────────
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)          # headings
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)      # hr rules
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)            # table rows
    text = re.sub(r"^\|[-| :]+\|$", "", text, flags=re.MULTILINE)       # table dividers
    text = re.sub(r"```[\s\S]*?```", "", text)                          # fenced code
    text = re.sub(r"`[^`\n]+`", "", text)                               # inline code

    # ── Links and media ──────────────────────────────────────────────────────
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)                         # images
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)               # [text](url) → text
    text = re.sub(r"https?://\S+", "", text)                            # bare URLs

    # ── Emphasis ─────────────────────────────────────────────────────────────
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_\n]+)_{1,3}", r"\1", text)

    # ── Citations ────────────────────────────────────────────────────────────
    text = re.sub(r"\[\d[\d,\s\-\u2013]*\]", "", text)                  # [1], [1,2], [1-4]
    text = re.sub(r"\[[A-Z][a-zA-Z\s,\.]+\d{4}[a-z]?\]", "", text)     # [Smith 2020]
    text = re.sub(r"(?<=\w)\^{?\d+}?", "", text)                        # superscripts

    # ── Captions ─────────────────────────────────────────────────────────────
    text = re.sub(
        r"^(fig(?:ure)?|table|equation|algorithm)\.?\s*\d+[.:–\-].*$",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # ── Page numbers ─────────────────────────────────────────────────────────
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)

    # ── Whitespace normalisation ─────────────────────────────────────────────
    text = re.sub(r"\n{3,}", "\n\n", text)                              # excess blank lines
    text = re.sub(r"[\u00a0\u200b\u200c\u200d\ufeff]", " ", text)       # unicode spaces
    text = re.sub(r"[ \t]{2,}", " ", text)                              # multiple spaces
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)               # blank-only lines

    text = text.strip()

    if not text:
        raise ValueError(
            "Text is empty after cleaning. "
            "Check the PDF extraction or try --keep-references."
        )

    log.info("Cleaned text: %d characters remaining.", len(text))
    return text
