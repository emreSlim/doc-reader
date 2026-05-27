"""
pdf_tts/merger.py
-----------------
FFmpeg-based audio merging.

Concatenates all chunk WAV files into a single final WAV using FFmpeg's
concat demuxer (lossless, no re-encoding).  Optionally converts the
result to MP3 via libmp3lame.
"""

import subprocess
from pathlib import Path

from .logger import log


def merge_audio(
    audio_files: list,
    final_dir: Path,
    pdf_stem: str,
    generate_mp3: bool = True,
    keep_chunks: bool = False,
) -> Path:
    """
    Merge all chunk WAVs into one final audiobook file.

    Steps:
      1. Write an FFmpeg concat list file.
      2. Run `ffmpeg -f concat` to produce the final WAV.
      3. Optionally encode to MP3 with libmp3lame at VBR quality 2.
      4. Delete intermediate chunk WAVs (unless *keep_chunks* is True).

    Args:
        audio_files:  Ordered list of chunk WAV paths.
        final_dir:    Directory for the merged output files.
        pdf_stem:     PDF filename without extension, used for naming output.
        generate_mp3: If True, also produce an MP3 alongside the WAV.
        keep_chunks:  If True, do not delete the chunk WAV files after merging.

    Returns:
        Path to the final merged WAV file.

    Raises:
        ValueError   – if *audio_files* is empty.
        RuntimeError – if FFmpeg exits with a non-zero return code.
    """
    if not audio_files:
        raise ValueError("No audio files to merge.")

    # Build the FFmpeg concat list
    merge_list = final_dir / f"{pdf_stem}_merge_list.txt"
    with merge_list.open("w", encoding="utf-8") as fh:
        for wav in audio_files:
            safe_path = str(wav.resolve()).replace("\\", "/")
            fh.write(f"file '{safe_path}'\n")

    final_wav = final_dir / f"{pdf_stem}_audiobook.wav"

    log.info("Merging %d WAV files → %s", len(audio_files), final_wav.name)

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(merge_list),
            "-c", "copy",
            str(final_wav),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error("FFmpeg merge stderr:\n%s", result.stderr)
        raise RuntimeError(
            f"FFmpeg merge failed (exit {result.returncode}). "
            "Ensure ffmpeg is installed and on PATH."
        )

    log.info(
        "Final WAV saved: %s  (%.1f MB)",
        final_wav,
        final_wav.stat().st_size / 1e6,
    )

    # Optional MP3 conversion
    if generate_mp3:
        _convert_to_mp3(final_wav, final_dir, pdf_stem)

    # Cleanup intermediate chunk WAVs
    if not keep_chunks:
        _delete_chunks(audio_files)

    return final_wav


def _convert_to_mp3(final_wav: Path, final_dir: Path, pdf_stem: str) -> None:
    """Encode *final_wav* to MP3 using FFmpeg + libmp3lame (VBR quality 2)."""
    final_mp3 = final_dir / f"{pdf_stem}_audiobook.mp3"
    log.info("Converting to MP3: %s", final_mp3.name)

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(final_wav),
            "-codec:a", "libmp3lame",
            "-qscale:a", "2",
            str(final_mp3),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.warning(
            "MP3 conversion failed – WAV is still available.\nFFmpeg: %s",
            result.stderr,
        )
    else:
        log.info(
            "MP3 saved: %s  (%.1f MB)",
            final_mp3,
            final_mp3.stat().st_size / 1e6,
        )


def _delete_chunks(audio_files: list) -> None:
    """Delete intermediate chunk WAV files after a successful merge."""
    log.info("Cleaning up %d chunk WAV files...", len(audio_files))
    for wav in audio_files:
        try:
            wav.unlink()
        except OSError as exc:
            log.warning("Could not delete %s: %s", wav, exc)
