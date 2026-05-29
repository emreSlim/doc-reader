"""
pdf_tts/pipeline.py
-------------------
End-to-end orchestration.

Wires together all pipeline stages in order:
    PDF → extract → clean → chunk → TTS → merge

This module contains no I/O logic of its own; it delegates everything to
the specialised modules (extractor, cleaner, chunker, tts, merger).
"""

import wave as _wave_module
from pathlib import Path

from .config import CHUNK_TARGET_CHARS
from .extractor import extract_pdf, get_extraction_metadata_path, read_markdown
from .cleaner import clean_text
from .chunker import chunk_text, save_chunks
from .tts import generate_audio
from .merger import merge_audio
from .word_alignment import build_word_alignment
from .utils import ensure_dirs
from .validator import validate_dependencies
from .logger import log


def _get_wav_duration(path: Path) -> float:
    """Return the duration of a WAV file in seconds."""
    try:
        with _wave_module.open(str(path), "r") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def run_pipeline(
    pdf_path: Path,
    model_path: Path,
    piper_exe: Path,
    output_dir: Path,
    generate_mp3: bool = True,
    keep_chunks: bool = False,
    remove_references: bool = True,
    chunk_size: int = CHUNK_TARGET_CHARS,
    fast: bool = False,
) -> dict:
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
        fast:              Use pdftext for extraction (instant, digital PDFs only).
                           If False, use Marker (handles scanned PDFs, much slower).
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
    md_path  = extract_pdf(pdf_path, dirs["markdown"], fast=fast)
    raw_text = read_markdown(md_path)

    # 4 – Text cleaning
    clean = clean_text(raw_text, remove_references=remove_references)

    # 5 – Sentence chunking
    chunks = chunk_text(clean, target_chars=chunk_size, max_chars=chunk_size + 200)
    chunk_files = save_chunks(chunks, dirs["chunks"], pdf_stem)

    # 6 – TTS generation
    audio_files = generate_audio(
        chunks=chunks,
        audio_dir=dirs["audio"],
        pdf_stem=pdf_stem,
        piper_exe=piper_exe,
        model_path=model_path,
    )

    # Compute chunk timing from WAV durations BEFORE potential deletion
    cumulative = 0.0
    chunk_timing: list[dict] = []
    for i, (wav_path, chunk_body) in enumerate(zip(audio_files, chunks)):
        dur = _get_wav_duration(wav_path)
        chunk_timing.append({
            "index": i,
            "text": chunk_body,
            "start": round(cumulative, 3),
            "end": round(cumulative + dur, 3),
        })
        cumulative += dur
    log.info("Computed chunk timing: %d chunks, total %.1fs", len(chunk_timing), cumulative)

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

    final_mp3 = dirs["final"] / f"{pdf_stem}_audiobook.mp3"

    # 8 – Word alignment (timing + PDF word bboxes)
    alignment_audio = final_mp3 if final_mp3.exists() else final_wav
    alignment_payload, alignment_path = build_word_alignment(
        pdf_path=pdf_path,
        chunk_timing=chunk_timing,
        output_dir=output_dir,
        audio_path=alignment_audio,
        extraction_metadata_path=get_extraction_metadata_path(md_path),
    )

    return {
        "pdf_path": str(pdf_path),
        "extracted_path": str(md_path),
        "extraction_metadata_path": str(get_extraction_metadata_path(md_path)),
        "chunk_files": [str(path) for path in chunk_files],
        "chunk_timing": chunk_timing,
        "word_alignment_path": str(alignment_path),
        "aligned_word_count": alignment_payload.get("aligned_word_count", 0),
        "alignment_timing_source": alignment_payload.get("timing_source", "estimated-chunk"),
        "final_wav": str(final_wav),
        "final_mp3": str(final_mp3) if final_mp3.exists() else None,
        "output_dir": str(output_dir),
        "fast": fast,
    }
