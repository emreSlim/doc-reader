"""
pdf_tts/pipeline.py
-------------------
End-to-end orchestration.

Wires together all pipeline stages in order:
    PDF → extract → clean → chunk → TTS → merge

This module contains no I/O logic of its own; it delegates everything to
the specialised modules (extractor, cleaner, chunker, tts, merger).
"""

from pathlib import Path

from .config import CHUNK_TARGET_CHARS
from .extractor import extract_pdf, read_markdown
from .cleaner import clean_text
from .chunker import chunk_text, save_chunks
from .tts import generate_audio
from .merger import merge_audio
from .utils import ensure_dirs
from .validator import validate_dependencies
from .logger import log


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
    Run the full PDF → audiobook pipeline.

    Args:
        pdf_path:          Path to the input PDF file.
        model_path:        Path to the Piper .onnx voice model.
        piper_exe:         Path to piper.exe.
        output_dir:        Root directory for all output files.
        generate_mp3:      Also produce an MP3 alongside the final WAV.
        keep_chunks:       Retain intermediate per-chunk WAV files.
        remove_references: Strip the References / Bibliography section.
        chunk_size:        Target character count per TTS chunk.
    """
    pdf_stem = pdf_path.stem

    log.info("=" * 60)
    log.info("PDF to Audiobook Pipeline")
    log.info("=" * 60)
    log.info("Input PDF  : %s", pdf_path)
    log.info("Piper model: %s", model_path)
    log.info("Output dir : %s", output_dir)
    log.info("=" * 60)

    # 1 – Pre-flight checks
    validate_dependencies(piper_exe=piper_exe, model_path=model_path)

    # 2 – Create output directories
    dirs = ensure_dirs(output_dir)

    # 3 – PDF extraction
    md_path  = extract_pdf(pdf_path, dirs["markdown"])
    raw_text = read_markdown(md_path)

    # 4 – Text cleaning
    clean = clean_text(raw_text, remove_references=remove_references)

    # 5 – Sentence chunking
    chunks = chunk_text(clean, target_chars=chunk_size, max_chars=chunk_size + 200)
    save_chunks(chunks, dirs["chunks"], pdf_stem)

    # 6 – TTS generation
    audio_files = generate_audio(
        chunks=chunks,
        audio_dir=dirs["audio"],
        pdf_stem=pdf_stem,
        piper_exe=piper_exe,
        model_path=model_path,
    )

    # 7 – Merge
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
