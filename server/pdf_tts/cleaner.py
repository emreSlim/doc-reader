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


def _is_markdown_table_delim_row(cells: list[str]) -> bool:
    """True for markdown alignment rows like: |---|:---:|---:|"""
    if not cells:
        return False
    return all(bool(re.fullmatch(r":?-{3,}:?", c.strip())) for c in cells)


def _parse_table_row(line: str) -> list[str]:
    """Parse a markdown table row into cell texts."""
    body = line.strip().strip("|").strip()
    if not body:
        return []
    return [c.strip() for c in body.split("|")]


def _ensure_sentence_end(text: str) -> str:
    t = text.strip()
    if not t:
        return t
    if re.search(r"[.!?:;]$", t):
        return t
    return f"{t}."


def _convert_markdown_tables_for_tts(text: str) -> str:
    """
    Convert markdown tables into sentence-like lines for clearer narration.

    Example row output:
      Traditional IT model: Capital budget required; Cloud computing model: Part of operating expense.
    """
    lines = text.splitlines()
    out: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        is_table_line = bool(re.match(r"^\s*\|.*\|\s*$", line))
        if not is_table_line:
            out.append(line)
            i += 1
            continue

        start = i
        block: list[str] = []
        while i < len(lines) and re.match(r"^\s*\|.*\|\s*$", lines[i]):
            block.append(lines[i])
            i += 1

        parsed_rows = [_parse_table_row(r) for r in block]
        parsed_rows = [r for r in parsed_rows if r]
        if len(parsed_rows) < 2:
            out.extend(lines[start:i])
            continue

        header_sep_idx = -1
        for ridx, row in enumerate(parsed_rows):
            if _is_markdown_table_delim_row(row):
                header_sep_idx = ridx
                break

        non_delim_rows = [r for r in parsed_rows if not _is_markdown_table_delim_row(r)]
        if len(non_delim_rows) < 2:
            out.extend(lines[start:i])
            continue

        if header_sep_idx == 1 and len(non_delim_rows[0]) >= 2:
            headers = non_delim_rows[0]
            data_rows = non_delim_rows[1:]
        else:
            headers = []
            data_rows = non_delim_rows

        out.append("Table:")
        for row in data_rows:
            cells = [c for c in row if c]
            if not cells:
                continue

            if headers:
                pairs = []
                for col_idx in range(min(len(headers), len(cells))):
                    h = headers[col_idx].strip()
                    v = cells[col_idx].strip()
                    if not h or not v:
                        continue
                    pairs.append(f"{h}: {v}")

                if pairs:
                    out.append(_ensure_sentence_end("; ".join(pairs)))
                    continue

            out.append(_ensure_sentence_end(", ".join(cells)))

        # Keep paragraph break where table existed.
        out.append("")

    return "\n".join(out)


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
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)  # html <br>
    text = re.sub(r"</?[^>]+>", "", text)                                 # other html tags

    # Convert markdown tables into pause-friendly narration lines.
    text = _convert_markdown_tables_for_tts(text)

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

