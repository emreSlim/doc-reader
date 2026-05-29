"""
pdf_tts/tts.py
--------------
Piper TTS integration.

Uses the piper-tts Python package to synthesize one WAV file per text
chunk.  The voice model is loaded once and reused for all chunks.
"""

import wave
from pathlib import Path

from .logger import log


def generate_audio(
    chunks: list,
    audio_dir: Path,
    pdf_stem: str,
    model_path: Path,
) -> list:
    """
    Generate one WAV file per chunk using Piper TTS.

    The voice model is loaded once from *model_path* and each chunk is
    synthesized sequentially.  WAV files are written to *audio_dir* and
    named:  <pdf_stem>_chunk_<NNNN>.wav

    Args:
        chunks:     List of text strings (output of chunker.chunk_text).
        audio_dir:  Directory where chunk WAVs are written.
        pdf_stem:   PDF filename without extension, used for naming files.
        model_path: Path to the .onnx voice model.

    Returns:
        List of Path objects for the generated WAV files, in order.

    Raises:
        FileNotFoundError – model not found.
        RuntimeError      – synthesis produces an empty file.
    """
    from piper.voice import PiperVoice  # imported here to keep startup fast

    model_path = model_path.resolve()

    if not model_path.exists():
        raise FileNotFoundError(
            f"Piper model not found at: {model_path}\n"
            "  -> Download the .onnx and .onnx.json files and place them in "
            f"{model_path.parent}"
        )

    total = len(chunks)
    log.debug("[tts] model=%s audio_dir=%s", model_path.name, audio_dir)
    log.info("Loading Piper voice model: %s", model_path.name)
    voice = PiperVoice.load(str(model_path))
    log.info("Generating audio for %d chunks using Piper...", total)

    audio_files: list[Path] = []
    for i, chunk in enumerate(chunks):
        out_wav = audio_dir / f"{pdf_stem}_chunk_{i:04d}.wav"
        log.info("[%d/%d] %s  (%d chars)", i + 1, total, out_wav.name, len(chunk))
        with wave.open(str(out_wav), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(voice.config.sample_rate)
            for audio_chunk in voice.synthesize(chunk):
                wav_file.writeframes(audio_chunk.audio_int16_bytes)
        if not out_wav.exists() or out_wav.stat().st_size == 0:
            raise RuntimeError(f"Piper produced no audio for chunk {i}: {out_wav}")
        size_kb = out_wav.stat().st_size // 1024
        log.debug("[tts] chunk %d → %s (%d KB)", i, out_wav.name, size_kb)
        audio_files.append(out_wav)

    log.info(
        "Audio generation complete – %d WAV files saved to: %s",
        len(audio_files),
        audio_dir,
    )
    return audio_files
