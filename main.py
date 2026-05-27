"""
main.py
-------
CLI entry point for the PDF → Audiobook pipeline.

All business logic lives in the pdf_tts/ package.
This file is responsible only for argument parsing and top-level
error handling.

Usage:
    python main.py <path_to_pdf> [options]

Run `python main.py --help` for the full option list.
"""

import argparse
import sys
from pathlib import Path

from pdf_tts.config import DEFAULT_MODEL_PATH, DEFAULT_PIPER_EXE, DEFAULT_OUTPUT_DIR, CHUNK_TARGET_CHARS
from pdf_tts.pipeline import run_pipeline


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert a PDF into a natural-sounding audiobook using Marker + Piper.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pdf", type=Path, help="Path to the input PDF file.")
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL_PATH,
        help=f"Path to Piper .onnx model  (default: {DEFAULT_MODEL_PATH})",
    )
    parser.add_argument(
        "--piper",
        type=Path,
        default=DEFAULT_PIPER_EXE,
        dest="piper_exe",
        help=f"Path to piper.exe  (default: {DEFAULT_PIPER_EXE})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        dest="output_dir",
        help=f"Root output directory  (default: {DEFAULT_OUTPUT_DIR})",
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
        help=f"Target chunk size in characters  (default: {CHUNK_TARGET_CHARS})",
    )
    return parser


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
        print(f"ERROR – File not found: {exc}", file=sys.stderr)
        sys.exit(1)
    except EnvironmentError as exc:
        print(f"ERROR – Environment:\n{exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"ERROR – Value: {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"ERROR – Runtime: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
