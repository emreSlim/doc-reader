"""
PDF to Audiobook Converter
==========================
Pipeline: PDF → Marker (markdown) → clean text → NLTK chunks → Piper TTS → FFmpeg merge

Usage:
    python main.py <path_to_pdf> [options]

    Options:
        --model       Path to Piper .onnx model file
        --piper       Path to piper.exe
        --output-dir  Root output directory (default: ./output)
        --no-mp3      Skip MP3 conversion (keep WAV only)
        --keep-chunks Keep intermediate chunk WAV files after merging
"""

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import json
from pathlib import Path

import nltk

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default paths  (override via CLI args)
# ---------------------------------------------------------------------------
DEFAULT_MODEL_PATH = Path("piper/models/en_US-amy-medium.onnx")
DEFAULT_PIPER_EXE = Path("piper/piper.exe")
DEFAULT_OUTPUT_DIR = Path("output")

# Chunk target size in characters (Piper works best with moderate chunks)
CHUNK_TARGET_CHARS = 400
CHUNK_MAX_CHARS = 600


# ---------------------------------------------------------------------------
# TASK 1 – Directory helpers
# ---------------------------------------------------------------------------
def ensure_dirs(output_dir: Path) -> dict:
    """Create and return all required output sub-directories."""
    dirs = {
        "markdown": output_dir / "markdown",
        "chunks": output_dir / "chunks",
        "audio": output_dir / "audio",
        "final": output_dir / "final",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    log.info("Output directories ready under: %s", output_dir)
    return dirs


# ---------------------------------------------------------------------------
# TASK 2 – PDF extraction via Marker
# ---------------------------------------------------------------------------
def extract_pdf(pdf_path: Path, markdown_dir: Path) -> Path:
    """
    Run Marker on *pdf_path* and return the path to the generated markdown file.

    Marker writes output into a sub-folder named after the PDF stem inside the
    provided output directory, e.g.:
        markdown_dir/<pdf_stem>/<pdf_stem>.md
    """
    pdf_path = pdf_path.resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pdf_stem = pdf_path.stem

    # If markdown was already extracted, skip re-running Marker (saves time).
    expected_md = markdown_dir / pdf_stem / f"{pdf_stem}.md"
    if expected_md.exists():
        log.info("Markdown already exists, skipping Marker extraction: %s", expected_md)
        return expected_md

    log.info("Starting Marker extraction for: %s", pdf_path.name)

    # NOTE:
    # Running "python -m marker.scripts.convert_single" does not execute the
    # click command in current Marker versions because the module has no
    # __main__ entrypoint. Use the installed console script instead.
    scripts_dir = Path(sys.executable).resolve().parent
    marker_candidates = [
        scripts_dir / "marker_single.exe",
        scripts_dir / "marker_single",
        Path("marker_single"),
    ]
    marker_cmd = None
    for candidate in marker_candidates:
        if candidate.exists() or shutil.which(str(candidate)):
            marker_cmd = str(candidate)
            break
    if marker_cmd is None:
        marker_cmd = shutil.which("marker_single")

    if not marker_cmd:
        raise FileNotFoundError(
            "Marker CLI 'marker_single' was not found in the active Python environment.\n"
            "Install/repair Marker in this environment: pip install -U marker-pdf"
        )

    cmd = [
        marker_cmd,
        str(pdf_path),
        "--output_dir", str(markdown_dir),
    ]

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
            "Check the log for details."
        )

    if result.stdout.strip():
        log.info("Marker output:\n%s", result.stdout.strip())

    # Marker places the .md file at: <output_dir>/<pdf_stem>/<pdf_stem>.md
    # (pdf_stem already defined above)
    expected_md = markdown_dir / pdf_stem / f"{pdf_stem}.md"

    if expected_md.exists():
        log.info("Markdown extracted to: %s", expected_md)
        return expected_md

    # Fallback: scan for any .md file inside markdown_dir/<pdf_stem>/
    search_root = markdown_dir / pdf_stem
    md_files = list(search_root.glob("**/*.md")) if search_root.exists() else []
    if not md_files:
        # Broader search – Marker version differences
        md_files = list(markdown_dir.glob(f"**/{pdf_stem}*.md"))
    if not md_files:
        raise FileNotFoundError(
            f"Marker ran successfully but no markdown file was found under {markdown_dir}. "
            "Please check Marker's output manually.\n"
            f"Marker stdout:\n{result.stdout[:1200]}\n"
            f"Marker stderr:\n{result.stderr[:1200]}"
        )

    md_path = md_files[0]
    log.info("Markdown found at: %s", md_path)
    return md_path


def read_markdown(md_path: Path) -> str:
    """Read markdown file safely, handling encoding edge cases."""
    try:
        text = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        log.warning("UTF-8 decode error – retrying with latin-1")
        text = md_path.read_text(encoding="latin-1")

    if not text.strip():
        raise ValueError(f"Extracted markdown is empty: {md_path}")

    log.info("Read %d characters from markdown.", len(text))
    return text


# ---------------------------------------------------------------------------
# TASK 3 – Text cleaning
# ---------------------------------------------------------------------------

# Section headings that signal the bibliography / references block.
_REFERENCE_HEADERS = re.compile(
    r"^#+\s*(references?|bibliography|works\s+cited|further\s+reading)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _remove_references_section(text: str) -> str:
    """
    Truncate text at the first reference/bibliography heading.
    This removes boilerplate citation lists that sound terrible as audio.
    """
    match = _REFERENCE_HEADERS.search(text)
    if match:
        log.info(
            "References section detected at char %d – removing it.", match.start()
        )
        return text[: match.start()]
    return text


def clean_text(text: str, remove_references: bool = True) -> str:
    """
    Clean extracted markdown/text for clean TTS narration.

    Steps:
      1. Optionally remove the References / Bibliography section.
      2. Remove markdown headings (keep the words, drop # symbols).
      3. Remove inline markdown: bold (**), italic (*/_), code (`), links.
      4. Remove citation patterns: [1], [12], [1,2], [Smith 2020].
      5. Remove figure / table captions that start with "Figure X" or "Table X".
      6. Remove page numbers (standalone digits on their own line).
      7. Collapse excessive whitespace and blank lines.
      8. Strip leading/trailing whitespace.
    """
    if remove_references:
        text = _remove_references_section(text)

    # --- Markdown structural cleanup ---
    # Remove ATX headings (## Heading) → keep the heading words
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Remove horizontal rules
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Remove markdown tables (lines containing | characters)
    text = re.sub(r"^\|.*\|$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\|[-| :]+\|$", "", text, flags=re.MULTILINE)

    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`\n]+`", "", text)  # inline code

    # Remove images: ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)

    # Remove hyperlinks but keep link text: [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

    # Remove bare URLs
    text = re.sub(r"https?://\S+", "", text)

    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*\n]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_\n]+)_{1,3}", r"\1", text)

    # --- Citation cleanup ---
    # Numeric: [1], [12], [1, 2, 3], [1-4]
    text = re.sub(r"\[\d[\d,\s\-\u2013]*\]", "", text)
    # Author-year: [Smith 2020], [Smith et al., 2020]
    text = re.sub(r"\[[A-Z][a-zA-Z\s,\.]+\d{4}[a-z]?\]", "", text)
    # Superscript-style footnote numbers (common in two-column PDFs)
    text = re.sub(r"(?<=\w)\^{?\d+}?", "", text)

    # --- Figure / Table captions ---
    text = re.sub(
        r"^(fig(?:ure)?|table|equation|algorithm)\.?\s*\d+[.:–\-].*$",
        "",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # --- Page numbers: standalone digit-only lines ---
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)

    # --- Whitespace normalisation ---
    # Replace multiple blank lines with a single blank line
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Replace non-breaking spaces and other unicode spaces
    text = re.sub(r"[\u00a0\u200b\u200c\u200d\ufeff]", " ", text)
    # Collapse multiple spaces on a single line
    text = re.sub(r"[ \t]{2,}", " ", text)
    # Clean up lines that are now empty after removals
    text = re.sub(r"^\s+$", "", text, flags=re.MULTILINE)

    text = text.strip()

    if not text:
        raise ValueError("Text is empty after cleaning. Check the PDF or extraction.")

    log.info("Cleaned text: %d characters remaining.", len(text))
    return text


# ---------------------------------------------------------------------------
# TASK 4 – Sentence chunking
# ---------------------------------------------------------------------------
def _ensure_nltk_punkt() -> None:
    """Download the NLTK punkt tokenizer data if not already present."""
    for resource in ("punkt", "punkt_tab"):
        try:
            nltk.data.find(f"tokenizers/{resource}")
        except LookupError:
            log.info("Downloading NLTK resource: %s", resource)
            nltk.download(resource, quiet=True)


def chunk_text(
    text: str,
    target_chars: int = CHUNK_TARGET_CHARS,
    max_chars: int = CHUNK_MAX_CHARS,
) -> list:
    """
    Split *text* into speech-friendly chunks using NLTK sentence tokenization.

    Strategy:
    - Tokenize into sentences with NLTK.
    - Greedily accumulate sentences until the chunk reaches *target_chars*.
    - Never exceed *max_chars* in a single chunk (force a split).
    - Sentences longer than *max_chars* are split at clause boundaries
      (semicolons, commas) rather than mid-word.

    Returns a list of non-empty string chunks.
    """
    _ensure_nltk_punkt()

    sentences = nltk.sent_tokenize(text)
    log.info("Tokenized into %d sentences.", len(sentences))

    chunks = []
    current = []
    current_len = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # If a single sentence is longer than max_chars, split it further.
        if len(sentence) > max_chars:
            # First flush current buffer
            if current:
                chunks.append(" ".join(current))
                current, current_len = [], 0
            # Split on clause boundaries
            sub_parts = re.split(r"(?<=[;,])\s+", sentence)
            sub_buf = []
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

    # Filter out whitespace-only chunks
    chunks = [c.strip() for c in chunks if c.strip()]

    log.info("Created %d text chunks.", len(chunks))
    return chunks


def save_chunks(chunks: list, chunks_dir: Path, pdf_stem: str) -> list:
    """Write each chunk to a numbered .txt file for inspection / debugging."""
    chunk_files = []
    for i, chunk in enumerate(chunks):
        p = chunks_dir / f"{pdf_stem}_chunk_{i:04d}.txt"
        p.write_text(chunk, encoding="utf-8")
        chunk_files.append(p)
    log.info("Saved %d chunk text files to: %s", len(chunks), chunks_dir)
    return chunk_files


# ---------------------------------------------------------------------------
# TASK 5 – Piper TTS audio generation
# ---------------------------------------------------------------------------
def generate_audio(
    chunks: list,
    audio_dir: Path,
    pdf_stem: str,
    piper_exe: Path,
    model_path: Path,
) -> list:
    """
    Call piper.exe for each text chunk and save a WAV file.

    Piper reads from stdin and writes WAV to --output_file.
    """
    piper_exe = piper_exe.resolve()
    model_path = model_path.resolve()

    if not piper_exe.exists():
        raise FileNotFoundError(
            f"piper.exe not found at: {piper_exe}\n"
            "Download it from https://github.com/rhasspy/piper/releases and place it "
            f"in: {piper_exe.parent}"
        )
    if not model_path.exists():
        raise FileNotFoundError(
            f"Piper model not found at: {model_path}\n"
            "Download a model from https://github.com/rhasspy/piper/releases and "
            f"place the .onnx and .onnx.json files in: {model_path.parent}"
        )

    total = len(chunks)
    audio_files = []

    log.info("Generating audio for %d chunks using Piper...", total)

    for i, chunk in enumerate(chunks):
        out_wav = audio_dir / f"{pdf_stem}_chunk_{i:04d}.wav"

        cmd = [
            str(piper_exe),
            "--model", str(model_path),
            "--output_file", str(out_wav),
        ]

        log.info("[%d/%d] Generating: %s  (%d chars)", i + 1, total, out_wav.name, len(chunk))

        try:
            result = subprocess.run(
                cmd,
                input=chunk,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Could not launch piper.exe: {piper_exe}. "
                "Make sure the path is correct and the binary is executable."
            )

        if result.returncode != 0:
            log.error("Piper stderr for chunk %d:\n%s", i, result.stderr)
            raise RuntimeError(
                f"Piper failed on chunk {i} (exit code {result.returncode})."
            )

        if not out_wav.exists() or out_wav.stat().st_size == 0:
            raise RuntimeError(
                f"Piper did not produce audio for chunk {i}: {out_wav}"
            )

        audio_files.append(out_wav)

    log.info("Audio generation complete. %d WAV files saved to: %s", len(audio_files), audio_dir)
    return audio_files


# ---------------------------------------------------------------------------
# TASK 6 – FFmpeg audio merging
# ---------------------------------------------------------------------------
def merge_audio(
    audio_files: list,
    final_dir: Path,
    pdf_stem: str,
    generate_mp3: bool = True,
    keep_chunks: bool = False,
) -> Path:
    """
    Concatenate all chunk WAVs into a single final WAV (and optionally MP3)
    using FFmpeg's concat demuxer.

    Returns the path to the final WAV file.
    """
    if not audio_files:
        raise ValueError("No audio files to merge.")

    # Build concat list file
    merge_list = final_dir / f"{pdf_stem}_merge_list.txt"
    with merge_list.open("w", encoding="utf-8") as fh:
        for wav in audio_files:
            # FFmpeg concat format requires forward slashes or escaped backslashes
            safe_path = str(wav.resolve()).replace("\\", "/")
            fh.write(f"file '{safe_path}'\n")

    final_wav = final_dir / f"{pdf_stem}_audiobook.wav"

    log.info("Merging %d WAV files → %s", len(audio_files), final_wav.name)

    cmd_wav = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(merge_list),
        "-c", "copy",
        str(final_wav),
    ]

    result = subprocess.run(cmd_wav, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("FFmpeg stderr:\n%s", result.stderr)
        raise RuntimeError(
            f"FFmpeg merge failed (exit code {result.returncode}). "
            "Make sure ffmpeg is installed and available on PATH."
        )

    log.info("Final WAV saved: %s  (%.1f MB)", final_wav, final_wav.stat().st_size / 1e6)

    if generate_mp3:
        final_mp3 = final_dir / f"{pdf_stem}_audiobook.mp3"
        log.info("Converting to MP3: %s", final_mp3.name)
        cmd_mp3 = [
            "ffmpeg", "-y",
            "-i", str(final_wav),
            "-codec:a", "libmp3lame",
            "-qscale:a", "2",
            str(final_mp3),
        ]
        result_mp3 = subprocess.run(cmd_mp3, capture_output=True, text=True)
        if result_mp3.returncode != 0:
            log.warning("MP3 conversion failed – WAV is still available.\nFFmpeg: %s", result_mp3.stderr)
        else:
            log.info("MP3 saved: %s  (%.1f MB)", final_mp3, final_mp3.stat().st_size / 1e6)

    # Cleanup intermediate chunk WAVs if not keeping them
    if not keep_chunks:
        log.info("Cleaning up %d chunk WAV files...", len(audio_files))
        for wav in audio_files:
            try:
                wav.unlink()
            except OSError as exc:
                log.warning("Could not delete chunk file %s: %s", wav, exc)

    return final_wav


# ---------------------------------------------------------------------------
# TASK 7 + 8 – Validation helpers
# ---------------------------------------------------------------------------
def validate_dependencies(piper_exe: Path, model_path: Path) -> None:
    """
    Pre-flight check for required external tools and model files.
    Raises descriptive errors so the user knows exactly what is missing.
    """
    errors = []

    # Check FFmpeg – also probe known WinGet install location as fallback
    _WINGET_FFMPEG = Path(os.environ.get("LOCALAPPDATA", "")) / (
        "Microsoft/WinGet/Packages/"
        "Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe/"
        "ffmpeg-8.1.1-essentials_build/bin/ffmpeg.exe"
    )
    ffmpeg_found = False
    try:
        ffmpeg_check = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True
        )
        ffmpeg_found = ffmpeg_check.returncode == 0
    except FileNotFoundError:
        pass

    if not ffmpeg_found and _WINGET_FFMPEG.exists():
        # Add it to PATH for this process so all later subprocess calls work
        bin_dir = str(_WINGET_FFMPEG.parent)
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
        ffmpeg_found = True
        log.info("FFmpeg found via WinGet install, added to PATH: %s", bin_dir)

    if not ffmpeg_found:
        errors.append(
            "FFmpeg not found on PATH.\n"
            "  -> Download from https://ffmpeg.org/download.html\n"
            "  -> Extract and add the bin/ folder to your System PATH\n"
            "  -> Then open a new terminal and verify with: ffmpeg -version"
        )

    # Check piper.exe
    if not piper_exe.exists():
        errors.append(
            f"piper.exe not found at: {piper_exe}\n"
            "  -> Download from https://github.com/rhasspy/piper/releases"
        )

    # Check model
    if not model_path.exists():
        errors.append(
            f"Piper model not found at: {model_path}\n"
            "  -> Download a model from https://github.com/rhasspy/piper/releases\n"
            "  -> Place the .onnx and .onnx.json files in the models/ directory"
        )
    else:
        # Check for companion .json config
        json_path = model_path.with_suffix(".onnx.json")
        if not json_path.exists():
            errors.append(
                f"Piper model config not found: {json_path}\n"
                "  -> Download the .onnx.json file alongside the .onnx model"
            )

    if errors:
        msg = "\n".join(f"  x {e}" for e in errors)
        raise EnvironmentError(f"Dependency check failed:\n{msg}")

    log.info("All dependencies verified.")


# ---------------------------------------------------------------------------
# TASK 9 – CLI / configurable paths
# ---------------------------------------------------------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a PDF into a natural-sounding audiobook using Marker + Piper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("pdf", type=Path, help="Path to the input PDF file.")
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help=f"Path to Piper .onnx model (default: {DEFAULT_MODEL_PATH})",
    )
    parser.add_argument(
        "--piper",
        type=Path,
        default=DEFAULT_PIPER_EXE,
        dest="piper_exe",
        help=f"Path to piper.exe (default: {DEFAULT_PIPER_EXE})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        dest="output_dir",
        help=f"Root output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--no-mp3",
        action="store_true",
        default=False,
        help="Skip MP3 conversion, keep WAV only.",
    )
    parser.add_argument(
        "--keep-chunks",
        action="store_true",
        default=False,
        help="Keep intermediate chunk WAV files after merging.",
    )
    parser.add_argument(
        "--keep-references",
        action="store_true",
        default=False,
        help="Do NOT remove the References / Bibliography section.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=CHUNK_TARGET_CHARS,
        dest="chunk_size",
        help=f"Target chunk size in characters (default: {CHUNK_TARGET_CHARS})",
    )
    return parser


# ---------------------------------------------------------------------------
# TASK 10 – Main orchestration
# ---------------------------------------------------------------------------
def run_pipeline(
    pdf_path: Path,
    model_path: Path,
    piper_exe: Path,
    output_dir: Path,
    generate_mp3: bool = True,
    keep_chunks: bool = False,
    remove_references: bool = True,
    chunk_size: int = CHUNK_TARGET_CHARS,
) -> None:
    """
    End-to-end pipeline:
        PDF -> Marker extraction -> clean text -> chunks -> Piper audio -> FFmpeg merge
    """
    pdf_stem = pdf_path.stem

    log.info("=" * 60)
    log.info("PDF to Audiobook Pipeline")
    log.info("=" * 60)
    log.info("Input PDF  : %s", pdf_path)
    log.info("Piper model: %s", model_path)
    log.info("Output dir : %s", output_dir)
    log.info("=" * 60)

    # 1. Validate dependencies
    validate_dependencies(piper_exe=piper_exe, model_path=model_path)

    # 2. Create output directories
    dirs = ensure_dirs(output_dir)

    # 3. Extract PDF to markdown
    md_path = extract_pdf(pdf_path, dirs["markdown"])
    raw_text = read_markdown(md_path)

    # 4. Clean text
    clean = clean_text(raw_text, remove_references=remove_references)

    # 5. Chunk text
    chunks = chunk_text(clean, target_chars=chunk_size, max_chars=chunk_size + 200)
    save_chunks(chunks, dirs["chunks"], pdf_stem)

    # 6. Generate audio
    audio_files = generate_audio(
        chunks=chunks,
        audio_dir=dirs["audio"],
        pdf_stem=pdf_stem,
        piper_exe=piper_exe,
        model_path=model_path,
    )

    # 7. Merge audio
    final_wav = merge_audio(
        audio_files=audio_files,
        final_dir=dirs["final"],
        pdf_stem=pdf_stem,
        generate_mp3=generate_mp3,
        keep_chunks=keep_chunks,
    )

    log.info("=" * 60)
    log.info("Pipeline complete!")
    log.info("Final audio: %s", final_wav)
    log.info("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        run_pipeline(
            pdf_path=args.pdf,
            model_path=args.model,
            piper_exe=args.piper_exe,
            output_dir=args.output_dir,
            generate_mp3=not args.no_mp3,
            keep_chunks=args.keep_chunks,
            remove_references=not args.keep_references,
            chunk_size=args.chunk_size,
        )
    except FileNotFoundError as exc:
        log.error("File not found: %s", exc)
        sys.exit(1)
    except EnvironmentError as exc:
        log.error("Environment error:\n%s", exc)
        sys.exit(1)
    except ValueError as exc:
        log.error("Value error: %s", exc)
        sys.exit(1)
    except RuntimeError as exc:
        log.error("Runtime error: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        log.warning("Interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()