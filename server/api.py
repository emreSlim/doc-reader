"""
FastAPI application exposing PDF extraction and TTS processing.

Run:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logger(request: Request, call_next):
    start = time.perf_counter()
    log.debug("[http] -> %s %s", request.method, request.url.path)
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    log.debug("[http] <- %s %s %d (%.1f ms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response

WORKSPACE_ROOT = Path(__file__).resolve().parent
INPUT_UPLOAD_DIR = WORKSPACE_ROOT / "input" / "api_uploads"
INPUT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Thread pool for running pipeline jobs (separate from Uvicorn's own pool).
# Uses all available CPU cores; each pipeline job spawns its own Piper subprocesses.
_executor = ThreadPoolExecutor(max_workers=os.cpu_count()-2 or 1, thread_name_prefix="pipeline")

# In-memory job registry
_jobs: dict[str, dict] = {}


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


def _run_pipeline_bg(
    job_id: str,
    pdf: Path,
    model: Path,
    piper: Path,
    out_root: Path,
    generate_mp3: bool,
    remove_references: bool,
    chunk_size: int,
    fast: bool,
) -> None:
    log.debug(
        "[job:%s] Pipeline thread started | pdf=%s model=%s piper=%s out=%s "
        "mp3=%s remove_refs=%s chunk_size=%d fast=%s",
        job_id, pdf.name, model.name, piper.name, out_root,
        generate_mp3, remove_references, chunk_size, fast,
    )
    try:
        validate_dependencies(piper_exe=piper, model_path=model)
        log.debug("[job:%s] Dependencies validated.", job_id)
        result = run_pipeline(
            pdf_path=pdf,
            model_path=model,
            piper_exe=piper,
            output_dir=out_root,
            generate_mp3=generate_mp3,
            keep_chunks=True,
            remove_references=remove_references,
            chunk_size=chunk_size,
            fast=fast,
        )
        _jobs[job_id]["status"] = "done"
        _jobs[job_id]["result"] = result
        log.info(
            "[job:%s] Completed. chunks=%d total_audio=%.1fs aligned_words=%d source=%s",
            job_id,
            len(result.get("chunk_timing", [])),
            result.get("chunk_timing", [{}])[-1].get("end", 0.0) if result.get("chunk_timing") else 0.0,
            result.get("aligned_word_count", 0),
            result.get("alignment_timing_source", "?"),
        )
    except Exception as exc:
        log.exception("[job:%s] Pipeline failed: %s", job_id, exc)
        _jobs[job_id]["status"] = "error"
        _jobs[job_id]["error"] = str(exc)


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
    pdf_path: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    fast: bool = Form(default=True),
    remove_references: bool = Form(default=True),
    chunk_size: int = Form(default=CHUNK_TARGET_CHARS),
    generate_mp3: bool = Form(default=True),
    output_dir: str = Form(default=str(DEFAULT_OUTPUT_DIR)),
    model_path: str = Form(default=str(DEFAULT_MODEL_PATH)),
    piper_exe: str = Form(default=str(DEFAULT_PIPER_EXE)),
):
    """
    Upload a PDF and start the TTS pipeline as a background job.
    Returns job_id immediately; poll GET /api/v1/jobs/{job_id} for status.
    """
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

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "processing",
        "pdf_path": str(pdf),
        "result": None,
        "error": None,
    }
    log.info("Started job %s for PDF: %s", job_id, pdf.name)
    log.debug(
        "[job:%s] Params | fast=%s remove_refs=%s chunk_size=%d mp3=%s model=%s",
        job_id, fast, remove_references, chunk_size, generate_mp3, model.name,
    )

    _executor.submit(
        _run_pipeline_bg,
        job_id, pdf, model, piper, out_root,
        generate_mp3, remove_references, chunk_size, fast,
    )

    return {"job_id": job_id, "status": "processing"}


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str):
    """Poll job status. Returns chunk_timing list when done."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if job["status"] == "processing":
        return {"job_id": job_id, "status": "processing"}

    if job["status"] == "error":
        return {"job_id": job_id, "status": "error", "error": job.get("error")}

    result = job["result"]
    return {
        "job_id": job_id,
        "status": "done",
        "chunk_timing": result.get("chunk_timing", []),
        "aligned_word_count": result.get("aligned_word_count", 0),
        "word_alignment_path": result.get("word_alignment_path"),
        "alignment_timing_source": result.get("alignment_timing_source", "estimated-chunk"),
        "has_mp3": bool(result.get("final_mp3")),
        "pdf_name": Path(result["pdf_path"]).name,
    }


@app.get("/api/v1/jobs/{job_id}/alignment")
def get_alignment(job_id: str):
    """Return word-level alignment payload for precise PDF highlighting."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail=f"Job not done (status: {job['status']})")

    result = job["result"]
    align_path_str = result.get("word_alignment_path")
    if not align_path_str:
        raise HTTPException(status_code=404, detail="No alignment path in result")

    align_path = Path(align_path_str)
    if not align_path.exists():
        raise HTTPException(status_code=404, detail=f"Alignment file missing: {align_path}")

    return JSONResponse(json.loads(align_path.read_text(encoding="utf-8")))


@app.get("/api/v1/jobs/{job_id}/audio")
def get_audio(job_id: str):
    """Stream the generated audio (MP3 preferred, WAV fallback)."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail=f"Job not done (status: {job['status']})")

    result = job["result"]
    audio_path_str = result.get("final_mp3") or result.get("final_wav")
    if not audio_path_str:
        raise HTTPException(status_code=404, detail="No audio file in result")

    audio_path = Path(audio_path_str)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Audio file missing: {audio_path}")

    media_type = "audio/mpeg" if audio_path.suffix == ".mp3" else "audio/wav"
    return FileResponse(
        str(audio_path),
        media_type=media_type,
        headers={"Accept-Ranges": "bytes"},
    )


@app.get("/api/v1/jobs/{job_id}/pdf")
def get_pdf_file(job_id: str):
    """Serve the original PDF so the browser can render it."""
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    pdf_path = Path(job["pdf_path"])
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF file not found on server")

    return FileResponse(str(pdf_path), media_type="application/pdf")
