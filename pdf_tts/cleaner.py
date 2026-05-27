"""
pdf_tts/cleaner.py
------------------
Text cleaning pipeline for TTS-ready narration.

Takes raw extracted text/markdown and produces clean, natural-sounding
prose by removing:
  - Markdown formatting symbols
  - Inline citations  ([1], [Smith 2020], etc.)
  - Figure / Table captions
  - Standalone page numbers
  - Bare URLs and image tags
  - Author affiliation blocks and email addresses
  - JSTOR / publisher download notices (per-page footers)
  - Running page headers (ALL-CAPS repeated journal/paper titles)
  - Journal volume/issue/page footer lines
  - Optionally the entire References / Bibliography section
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

# JSTOR / publisher per-page download notice (spans 2-3 lines)
_JSTOR_NOTICE = re.compile(
    r"This content downloaded from[\s\S]{0,200}?(?:All use subject to\s+\S+|jstor\.org/terms[^\n]*)",
    re.IGNORECASE,
)

# Journal header/footer lines:
# e.g. "MIS Quarterly Vol. 40 No. 4, pp. 807-818/December 2016 807"
# e.g. "Journal of Information Systems Vol. 12 No. 3"
_JOURNAL_LINE = re.compile(
    r"^.{0,120}(?:vol(?:ume)?[\s.]\s*\d+|no[\s.]\s*\d+|pp?\.\s*\d+[-/\d]*"
    r"|\bissn\b|\bdoi\b[:\s]|\bceur\b|workshop\s+proceedings"
    r"|copyright\s+\d{4}|creative\s+commons|ceur-ws\.org"
    r"|quarterly|journal\s+of\s+\w+|proceedings\s+of|transactions\s+on).{0,120}$",
    re.IGNORECASE | re.MULTILINE,
)

# Author affiliation blocks: lines that are just an institution / city / country,
# typically appearing at the top of a paper (1-2 lines per author, no sentence structure).
# Detected as short lines (< 80 chars) containing known affiliation keywords.
_AFFILIATION_LINE = re.compile(
    r"^.{0,80}(?:university|school\s+of|department\s+of|institute\s+of"
    r"|college\s+of|faculty\s+of|leuven|carlson|polytechnic"
    r"|u\.s\.a\.|u\.k\.|china|belgium|germany|france|italy|japan|canada|australia).{0,80}$",
    re.IGNORECASE | re.MULTILINE,
)

# Email addresses in curly braces: {name@domain.com}
_CURLY_EMAIL = re.compile(r"\{[^}]*@[^}]*\}")

# Bare email addresses
_BARE_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}\b")

# ALL-CAPS lines that are likely running page headers (≥ 4 words, all caps/spaces/&)
# Must be a whole line, short enough to be a header (< 80 chars)
_ALLCAPS_HEADER = re.compile(
    r"^(?:[A-Z0-9][A-Z0-9\s&:,'\-–/]{10,78})$",
    re.MULTILINE,
)

# IP address lines (from JSTOR download notices)
_IP_ADDRESS_LINE = re.compile(
    r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}.*$",
    re.MULTILINE,
)

# Lines that are just a number with optional surrounding text that look like
# journal page numbers at end of lines: "... 807" or "807" standalone
_JOURNAL_PAGE_NUM = re.compile(r"(?<!\d)\b[89]\d{2}\b\s*$", re.MULTILINE)


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_text(text: str, remove_references: bool = True) -> str:
    """
    Clean *text* for clean TTS narration.

    Processing order:
      1.  Optionally strip from the References/Bibliography/Acknowledgements heading.
      2.  Remove JSTOR and publisher per-page download notices.
      3.  Remove journal volume/issue/page header and footer lines.
      4.  Remove IP address lines.
      5.  Remove ALL-CAPS running page headers.
      6.  Remove email addresses (curly-brace and bare forms).
      7.  Remove ATX markdown headings (keep words, drop # symbols).
      8.  Remove horizontal rules.
      9.  Remove markdown tables.
      10. Remove fenced and inline code blocks.
      11. Remove images and hyperlinks (keep link text).
      12. Remove bare URLs.
      13. Remove bold / italic markers.
      14. Remove numeric and author-year citations.
      15. Remove superscript footnote numbers.
      16. Remove Figure / Table / Equation captions.
      17. Remove standalone page-number lines.
      18. Normalise whitespace and blank lines.

    Raises:
        ValueError – if the result is empty after cleaning.
    """
    if remove_references:
        text = _remove_references_section(text)

    # ── Publisher boilerplate ────────────────────────────────────────────────
    text = _JSTOR_NOTICE.sub("", text)
    text = _JOURNAL_LINE.sub("", text)
    text = _IP_ADDRESS_LINE.sub("", text)
    text = _ALLCAPS_HEADER.sub("", text)

    # ── Author affiliation blocks ─────────────────────────────────────────────
    text = _AFFILIATION_LINE.sub("", text)

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
