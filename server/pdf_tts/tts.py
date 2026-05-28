"""
pdf_tts/tts.py
--------------
Piper TTS integration.

Calls piper.exe once per text chunk via subprocess, passing text through
stdin and writing a numbered .wav file per chunk.  This keeps memory use
flat regardless of document length.
"""

import subprocess
from pathlib import Path

from .logger import log


def generate_audio(
    chunks: list,
    audio_dir: Path,
    pdf_stem: str,
    piper_exe: Path,
    model_path: Path,
) -> list:
    """
    Generate one WAV file per chunk using Piper TTS.

    Piper is invoked via subprocess with text fed through stdin.
    WAV files are written sequentially to *audio_dir* and named:
        <pdf_stem>_chunk_<NNNN>.wav

    Args:
        chunks:     List of text strings (output of chunker.chunk_text).
        audio_dir:  Directory where chunk WAVs are written.
        pdf_stem:   PDF filename without extension, used for naming files.
        piper_exe:  Path to piper.exe.
        model_path: Path to the .onnx voice model.

    Returns:
        List of Path objects for the generated WAV files, in order.

    Raises:
        FileNotFoundError – piper.exe or model not found.
        RuntimeError      – Piper exits non-zero or produces an empty file.
    """
    piper_exe  = piper_exe.resolve()
    model_path = model_path.resolve()

    if not piper_exe.exists():
        raise FileNotFoundError(
            f"piper.exe not found at: {piper_exe}\n"
            "  -> Download from https://github.com/rhasspy/piper/releases"
        )
    if not model_path.exists():
        raise FileNotFoundError(
            f"Piper model not found at: {model_path}\n"
            "  -> Download the .onnx and .onnx.json files and place them in "
            f"{model_path.parent}"
        )

    total = len(chunks)
    audio_files: list[Path] = []

    log.info("Generating audio for %d chunks using Piper...", total)

    for i, chunk in enumerate(chunks):
        out_wav = audio_dir / f"{pdf_stem}_chunk_{i:04d}.wav"

        cmd = [
            str(piper_exe),
            "--model", str(model_path),
            "--output_file", str(out_wav),
        ]

        log.info("[%d/%d] %s  (%d chars)", i + 1, total, out_wav.name, len(chunk))

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
                f"Could not launch piper.exe at {piper_exe}. "
                "Verify the path and that the binary is executable."
            )

        if result.returncode != 0:
            log.error("Piper stderr for chunk %d:\n%s", i, result.stderr)
            raise RuntimeError(f"Piper failed on chunk {i} (exit {result.returncode}).")

        if not out_wav.exists() or out_wav.stat().st_size == 0:
            raise RuntimeError(f"Piper produced no audio for chunk {i}: {out_wav}")

        audio_files.append(out_wav)

    log.info(
        "Audio generation complete – %d WAV files saved to: %s",
        len(audio_files),
        audio_dir,
    )
    return audio_files
