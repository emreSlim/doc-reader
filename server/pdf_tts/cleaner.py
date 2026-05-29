"""
pdf_tts/cleaner.py
------------------
Text cleaning pipeline for TTS-ready narration.

Design note:
    Header/footer suppression is handled upstream in `extractor.py` using
    geometry + repeated-margin detection (content-agnostic).

This module performs:
    - optional References/Bibliography truncation
    - library-assisted boilerplate cleanup via `trafilatura`
    - markdown/text normalization and citation cleanup
"""

import re
from html import escape

try:
        from trafilatura import extract as trafilatura_extract
except Exception:  # pragma: no cover - optional dependency fallback
        trafilatura_extract = None

from .logger import log

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_REFERENCE_HEADERS = re.compile(
    r"^(#{1,6}\s*)?(references?|bibliography|works\s+cited|further\s+reading"
    r"|acknowledgements?|appendix|footnotes?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)

# Email addresses in curly braces: {name@domain.com}
_CURLY_EMAIL = re.compile(r"\{[^}]*@[^}]*\}")

# Bare email addresses
_BARE_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")


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


def _library_boilerplate_cleanup(text: str) -> str:
    """
    Use trafilatura to normalize and de-noise plain text without
    document-specific hardcoded rules.

    If trafilatura is unavailable or returns empty output, fall back to the
    original text unchanged.
    """
    if trafilatura_extract is None:
        return text

    html_doc = "<html><body>" + "".join(
        f"<p>{escape(line)}</p>" for line in text.splitlines()
    ) + "</body></html>"

    try:
        cleaned = trafilatura_extract(
            html_doc,
            output_format="txt",
            favor_precision=True,
            include_comments=False,
            include_tables=False,
        )
    except Exception as exc:
        log.debug("trafilatura cleanup failed, falling back to raw text: %s", exc)
        return text

    if cleaned and cleaned.strip():
        return cleaned
    return text


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

    # Basic whitespace normalization.
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)
    text = text.strip()

    if not text:
        raise ValueError("Text is empty after Marker cleanup.")

    log.info("Light-cleaned Marker text: %d characters remaining.", len(text))
    return text

def clean_text(text: str, remove_references: bool = True) -> str:
    """
    Clean *text* for clean TTS narration.

        Processing order:
            1.  Optionally strip from the References/Bibliography/Acknowledgements heading.
            2.  Library-assisted boilerplate cleanup (`trafilatura`).
            3.  Remove email addresses (curly-brace and bare forms).
            4.  Remove ATX markdown headings (keep words, drop # symbols).
            5.  Remove horizontal rules.
            6.  Remove markdown tables.
            7.  Remove fenced and inline code blocks.
            8.  Remove images and hyperlinks (keep link text).
            9.  Remove bare URLs.
            10. Remove bold / italic markers.
            11. Remove numeric and author-year citations.
            12. Remove superscript footnote numbers.
            13. Remove Figure / Table / Equation captions.
            14. Remove standalone page-number lines.
            15. Normalise whitespace and blank lines.

    Raises:
        ValueError - if the result is empty after cleaning.
    """
    if remove_references:
        text = _remove_references_section(text)

    # ── Library-assisted boilerplate cleanup ────────────────────────────────
    text = _library_boilerplate_cleanup(text)

    # ── Email addresses ──────────────────────────────────────────────────────
    text = _CURLY_EMAIL.sub("", text)
    text = _BARE_EMAIL.sub("", text)

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

    # ── Standalone page numbers ───────────────────────────────────────────────
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
