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
from .cleaner import clean_marker_text
from .chunker import chunk_text, save_chunks
from .tts import generate_audio
from .merger import merge_audio
from .chunk_highlight import build_chunk_highlights
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
    """
    pdf_stem = pdf_path.stem

    log.info("=" * 60)
    log.info("PDF to Audiobook Pipeline")
    log.info("=" * 60)
    log.info("Input PDF  : %s", pdf_path)
    log.info("Piper model: %s", model_path)
    log.info("Output dir : %s", output_dir)
    log.info("=" * 60)

    import time as _time

    # 1 – Pre-flight checks
    log.debug("[pipeline] Stage 1: validating dependencies...")
    validate_dependencies(piper_exe=piper_exe, model_path=model_path)

    # 2 – Create output directories
    log.debug("[pipeline] Stage 2: creating output dirs at %s", output_dir)
    dirs = ensure_dirs(output_dir)

    # 3 – PDF extraction
    log.debug("[pipeline] Stage 3: extracting PDF with Marker...")
    _t0 = _time.perf_counter()
    md_path  = extract_pdf(pdf_path, dirs["markdown"])
    raw_text = read_markdown(md_path)
    log.debug("[pipeline] Stage 3 done in %.1fs | raw_chars=%d", _time.perf_counter() - _t0, len(raw_text))

    # 4 – Text cleaning
    log.debug("[pipeline] Stage 4: light-cleaning Marker markdown/text (remove_references=%s)...", remove_references)
    clean = clean_marker_text(raw_text, remove_references=remove_references)
    log.debug("[pipeline] Stage 4 done for Marker | clean_chars=%d (removed %d chars)", len(clean), len(raw_text) - len(clean))

    # 5 – Sentence chunking
    log.debug("[pipeline] Stage 5: chunking (target=%d chars)...", chunk_size)
    chunks = chunk_text(clean, target_chars=chunk_size, max_chars=chunk_size + 200)
    chunk_files = save_chunks(chunks, dirs["chunks"], pdf_stem)
    log.debug("[pipeline] Stage 5 done | %d chunks saved", len(chunks))

    # 6 – TTS generation
    log.debug("[pipeline] Stage 6: TTS generation for %d chunks...", len(chunks))
    _t0 = _time.perf_counter()
    audio_files = generate_audio(
        chunks=chunks,
        audio_dir=dirs["audio"],
        pdf_stem=pdf_stem,
        piper_exe=piper_exe,
        model_path=model_path,
    )
    log.debug("[pipeline] Stage 6 done in %.1fs | %d WAVs generated", _time.perf_counter() - _t0, len(audio_files))

    # Compute chunk timing from WAV durations BEFORE potential deletion
    log.debug("[pipeline] Computing chunk timing from WAV durations...")
    cumulative = 0.0
    chunk_timing: list[dict] = []
    for i, (wav_path, chunk_body) in enumerate(zip(audio_files, chunks)):
        dur = _get_wav_duration(wav_path)
        log.debug("  chunk %d: %.3fs | %d chars | %s", i, dur, len(chunk_body), wav_path.name)
        chunk_timing.append({
            "index": i,
            "text": chunk_body,
            "start": round(cumulative, 3),
            "end": round(cumulative + dur, 3),
        })
        cumulative += dur
    log.info("Computed chunk timing: %d chunks, total %.1fs", len(chunk_timing), cumulative)

    # 7 – Merge
    log.debug("[pipeline] Stage 7: merging %d WAV files (mp3=%s keep_chunks=%s)...", len(audio_files), generate_mp3, keep_chunks)
    _t0 = _time.perf_counter()
    final_wav = merge_audio(
        audio_files=audio_files,
        final_dir=dirs["final"],
        pdf_stem=pdf_stem,
        generate_mp3=generate_mp3,
        keep_chunks=keep_chunks,
    )
    log.debug("[pipeline] Stage 7 done in %.1fs | final_wav=%s", _time.perf_counter() - _t0, final_wav.name)

    log.info("=" * 60)
    log.info("Pipeline complete!")
    log.info("Final audio: %s", final_wav)
    log.info("=" * 60)

    final_mp3 = dirs["final"] / f"{pdf_stem}_audiobook.mp3"

    # 8 – Chunk highlight mapping (text chunk -> PDF bbox)
    log.debug("[pipeline] Stage 8: building chunk highlights...")
    _t0 = _time.perf_counter()
    highlight_payload, highlight_path = build_chunk_highlights(
        pdf_path=pdf_path,
        chunk_timing=chunk_timing,
        output_dir=output_dir,
    )
    log.debug(
        "[pipeline] Stage 8 done in %.1fs | mapped=%d/%d coverage=%.2f%% path=%s",
        _time.perf_counter() - _t0,
        highlight_payload.get("highlight_count", 0),
        highlight_payload.get("chunk_count", 0),
        highlight_payload.get("coverage", 0.0),
        highlight_path.name,
    )

    return {
        "pdf_path": str(pdf_path),
        "extracted_path": str(md_path),
        "extraction_metadata_path": str(get_extraction_metadata_path(md_path)),
        "chunk_files": [str(path) for path in chunk_files],
        "chunk_timing": chunk_timing,
        "chunk_highlight_path": str(highlight_path),
        "chunk_highlight_coverage": highlight_payload.get("coverage", 0.0),
        "final_wav": str(final_wav),
        "final_mp3": str(final_mp3) if final_mp3.exists() else None,
        "output_dir": str(output_dir),
    }
