"""
FastAPI application exposing PDF extraction and TTS processing.

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from pdf_tts.cleaner import clean_text
from pdf_tts.config import (
    CHUNK_TARGET_CHARS,
    DEFAULT_MODEL_PATH,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_PIPER_EXE,
)
from pdf_tts.extractor import extract_pdf, get_extraction_metadata_path, read_markdown
from pdf_tts.logger import log
from pdf_tts.pipeline import run_pipeline
from pdf_tts.utils import ensure_dirs
from pdf_tts.validator import validate_dependencies

app = FastAPI(title="PDF TTS API", version="1.0.0")

WORKSPACE_ROOT = Path(__file__).resolve().parent
INPUT_UPLOAD_DIR = WORKSPACE_ROOT / "input" / "api_uploads"
INPUT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return safe or f"upload_{int(time.time())}.pdf"


async def _resolve_pdf_source(
    pdf_path: str | None,
    file: UploadFile | None,
) -> Path:
    if bool(pdf_path) == bool(file):
        raise HTTPException(status_code=400, detail="Provide exactly one of 'pdf_path' or 'file'.")

    if pdf_path:
        resolved = Path(pdf_path)
        if not resolved.is_absolute():
            resolved = (WORKSPACE_ROOT / resolved).resolve()
        if not resolved.exists():
            raise HTTPException(status_code=404, detail=f"PDF not found: {resolved}")
        return resolved

    assert file is not None
    filename = _safe_filename(file.filename or "upload.pdf")
    target = INPUT_UPLOAD_DIR / filename
    content = await file.read()
    target.write_bytes(content)
    return target


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/extract")
async def extract_endpoint(
    pdf_path: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    fast: bool = Form(default=True),
    remove_references: bool = Form(default=True),
    output_dir: str = Form(default=str(DEFAULT_OUTPUT_DIR)),
):
    pdf = await _resolve_pdf_source(pdf_path, file)
    out_root = Path(output_dir)
    if not out_root.is_absolute():
        out_root = (WORKSPACE_ROOT / out_root).resolve()

    dirs = ensure_dirs(out_root)
    extracted_path = extract_pdf(pdf, dirs["markdown"], fast=fast)
    raw_text = read_markdown(extracted_path)
    cleaned_text = clean_text(raw_text, remove_references=remove_references)

    metadata_path = get_extraction_metadata_path(extracted_path)
    metadata = None
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    return JSONResponse(
        {
            "pdf_path": str(pdf),
            "fast": fast,
            "extracted_path": str(extracted_path),
            "extraction_metadata_path": str(metadata_path) if metadata_path.exists() else None,
            "cleaned_text": cleaned_text,
            "cleaned_char_count": len(cleaned_text),
            "metadata": metadata,
        }
    )


@app.post("/api/v1/process")
async def process_endpoint(
    pdf_path: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    fast: bool = Form(default=True),
    remove_references: bool = Form(default=True),
    chunk_size: int = Form(default=CHUNK_TARGET_CHARS),
    keep_chunks: bool = Form(default=False),
    generate_mp3: bool = Form(default=True),
    output_dir: str = Form(default=str(DEFAULT_OUTPUT_DIR)),
    model_path: str = Form(default=str(DEFAULT_MODEL_PATH)),
    piper_exe: str = Form(default=str(DEFAULT_PIPER_EXE)),
):
    pdf = await _resolve_pdf_source(pdf_path, file)

    out_root = Path(output_dir)
    if not out_root.is_absolute():
        out_root = (WORKSPACE_ROOT / out_root).resolve()

    model = Path(model_path)
    if not model.is_absolute():
        model = (WORKSPACE_ROOT / model).resolve()

    piper = Path(piper_exe)
    if not piper.is_absolute():
        piper = (WORKSPACE_ROOT / piper).resolve()

    try:
        validate_dependencies(piper_exe=piper, model_path=model)
        result = run_pipeline(
            pdf_path=pdf,
            model_path=model,
            piper_exe=piper,
            output_dir=out_root,
            generate_mp3=generate_mp3,
            keep_chunks=keep_chunks,
            remove_references=remove_references,
            chunk_size=chunk_size,
            fast=fast,
        )
    except (FileNotFoundError, EnvironmentError, ValueError, RuntimeError) as exc:
        log.exception("Processing failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse(result)
