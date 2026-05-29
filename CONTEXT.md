# TTS Reader Conversation Context (Generated)

Date generated: 2026-05-29
Workspace root: C:/Users/ImranQureshi/Desktop/code/tts-reader

## 1) Project Goal
Build a PDF-to-audio reading system that:
- Uploads a PDF
- Processes it to speech audio
- Shows a play button when ready
- Lets user read while listening with live highlighting

## 2) Repository Layout
- `server/` Python backend + pipeline
- `client/` React + TypeScript + Vite frontend

## 3) Major History (Chronological)
1. Started with monolithic `main.py` pipeline.
2. Refactored into modular `pdf_tts/` package.
3. Marker extraction was too slow; introduced `--fast` extraction via `pdftext`.
4. Added column-aware reading order for multi-column PDFs.
5. Removed hardcoded cleanup rules; moved to model/library-guided cleanup.
6. Integrated pretrained DocLayout-YOLO filtering for layout-aware text keep/drop.
7. Added structured extraction metadata (block bbox, keep/drop reasons, layout matches).
8. Added FastAPI endpoints for extraction and full processing.
9. Implemented React client for upload, processing status, reader, and audio controls.
10. Added background job processing API and job polling endpoints for frontend UX.
11. Added chunk timing generation in pipeline for playback-sync highlighting.
12. Fixed `UnboundLocalError` caused by variable shadowing in `pipeline.py`.

## 4) Backend Architecture (server)
### Core modules
- `server/pdf_tts/extractor.py`
  - Fast extraction with `pdftext`.
  - Column-aware sorting.
  - Layout + margin/repetition filtering support.
  - Writes text + companion metadata JSON.

- `server/pdf_tts/layout_filter.py`
  - Uses pretrained DocLayout-YOLO (`DocStructBench`) from Hugging Face.
  - Detects layout regions and filters blocks by overlap/allowed labels.

- `server/pdf_tts/cleaner.py`
  - Text cleanup using `trafilatura` and generic reference/email/citation cleanup.

- `server/pdf_tts/chunker.py`
  - NLTK sentence tokenization into TTS-friendly chunks.

- `server/pdf_tts/tts.py`
  - Invokes Piper per chunk, writes chunk WAVs.

- `server/pdf_tts/merger.py`
  - Merges chunk WAVs, optionally outputs MP3 via ffmpeg.

- `server/pdf_tts/pipeline.py`
  - Orchestrates end-to-end run.
  - Returns structured result including `chunk_timing`.

### API
- `server/api.py`
  - CORS enabled.
  - In-memory background job registry (`_jobs`).
  - Endpoints:
    - `GET /health`
    - `POST /api/v1/extract`
    - `POST /api/v1/process` (starts async background job, returns `job_id`)
    - `GET /api/v1/jobs/{job_id}` (status + `chunk_timing`)
    - `GET /api/v1/jobs/{job_id}/audio`
    - `GET /api/v1/jobs/{job_id}/pdf`

## 5) Frontend Architecture (client)
### Stack
- React 18
- TypeScript
- Vite
- Tailwind
- react-pdf

### UX flow
1. Upload page (`UploadPage`)
2. Processing page with polling (`ProcessingPage`)
3. Reader page (`ReaderPage`) with:
   - PDF panel (`PdfViewer`)
   - Text panel (`TextPanel`)
   - Audio controls (`AudioPlayer`)

### Important files
- `client/src/App.tsx`
- `client/src/api.ts`
- `client/src/components/UploadPage.tsx`
- `client/src/components/ProcessingPage.tsx`
- `client/src/components/ReaderPage.tsx`
- `client/src/components/PdfViewer.tsx`
- `client/src/components/TextPanel.tsx`
- `client/src/components/AudioPlayer.tsx`

## 6) Sync / Highlighting Status
### Implemented now
- Chunk-level timing metadata (`start`, `end`) from generated chunk WAV durations.
- Active transcript chunk highlighting in text panel while audio plays.
- Approximate PDF text highlighting by matching terms from active chunk in PDF text layer.

### Not yet fully implemented
- True exact per-word/per-sentence forced alignment with precise timestamps and PDF coordinates.
- Current PDF highlighting is heuristic keyword matching, not strict word-level alignment.

## 7) Critical Bug Found and Fixed
### Error seen
`UnboundLocalError: cannot access local variable 'chunk_text' where it is not associated with a value`

### Root cause
In `server/pdf_tts/pipeline.py`, loop variable `chunk_text` shadowed imported function `chunk_text()`.

### Fix
Renamed loop variable to `chunk_body`.

### Validation
- `python -m py_compile pdf_tts/pipeline.py api.py` succeeded.

## 8) Dev/Run Notes
### Backend
From `server/`:
- Activate venv
- Run `uvicorn api:app --host 0.0.0.0 --port 8000 --reload`

### Frontend
From `client/`:
- `npm install`
- `npm run dev`

### API routing in dev
- Frontend uses relative `/api/...` fetch paths.
- Vite proxy forwards `/api` to `http://localhost:8000` (dev only).

## 9) Known Environment Notes
- OS: Windows
- Workspace folders observed: `tts-reader/server`, `tts-reader/client`
- User terminal had a `vite dev` command with exit code 127 at one point; normal command should be `npm run dev`.

## 10) Current Overall State
- End-to-end architecture is in place.
- Upload → process async job → poll → play audio is implemented.
- Read-while-listening UX works with chunk-level sync and approximate PDF highlight.
- Exact forced-alignment-quality PDF highlighting remains future work.
