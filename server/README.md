# PDF to Audiobook Converter

Convert any PDF — including research papers and two-column academic articles — into a clean, natural-sounding audiobook MP3/WAV using **Marker**, **DocLayout-YOLO**, **Piper TTS**, **NLTK**, and **FFmpeg**.

---

## Pipeline Overview

```
PDF → Marker extraction + layout filtering → Text Cleaning → NLTK Chunking → Piper TTS → FFmpeg Merge → Chunk→PDF Highlight Mapping
```

---

## Folder Structure

```
tts-reader/
│
├── input/                          ← Put your PDF files here
│
├── output/
│   ├── markdown/                   ← Marker-extracted markdown files
│   ├── chunks/                     ← Numbered text chunk files (for debugging)
│   ├── audio/                      ← Intermediate per-chunk WAV files
│   └── final/                      ← Final merged audiobook (WAV + MP3)
│
├── piper/
│   ├── piper.exe                   ← Piper TTS binary (Windows)
│   ├── models/
│   │   ├── en_US-amy-medium.onnx
│   │   └── en_US-amy-medium.onnx.json
│   └── espeak-ng-data/             ← Required by Piper (included with release)
│
├── api.py                          ← FastAPI server (used by client)
├── main.py                         ← Optional CLI entrypoint
├── requirements.txt
└── README.md
```

---

## Requirements

### System Dependencies

| Dependency | Version | Download |
|---|---|---|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| FFmpeg | Latest | [ffmpeg.org](https://ffmpeg.org/download.html) |
| Piper TTS | Latest | [GitHub Releases](https://github.com/rhasspy/piper/releases) |

### Python Packages

See [requirements.txt](requirements.txt).

---

## Installation

### Step 1 – Clone / set up the project

Use a single environment under `server/.venv`.

```bash
cd C:\Users\YourName\Desktop\code\tts-reader\server
python -m venv .venv
.venv\Scripts\activate
```

### Step 2 – Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 3 – Install FFmpeg

1. Download the **Windows build** from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
2. Extract and copy `ffmpeg.exe`, `ffprobe.exe` to a folder (e.g. `C:\ffmpeg\bin\`)
3. Add that folder to your **System PATH**:
   - Open *Start → Environment Variables → System Variables → Path → Edit → New*
   - Add `C:\ffmpeg\bin`
4. Verify: open a new terminal and run `ffmpeg -version`

### Step 4 – Download Piper TTS

1. Go to [https://github.com/rhasspy/piper/releases](https://github.com/rhasspy/piper/releases)
2. Download the **Windows AMD64** release (e.g. `piper_windows_amd64.zip`)
3. Extract all contents into the `piper/` folder inside this project
4. You should now have `piper/piper.exe` and `piper/espeak-ng-data/`

### Step 5 – Download a Piper voice model

1. Browse voices at [https://github.com/rhasspy/piper/releases](https://github.com/rhasspy/piper/releases) or [https://huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
2. Download a model pair, e.g.:
   - `en_US-amy-medium.onnx`
   - `en_US-amy-medium.onnx.json`
3. Place **both files** into `piper/models/`

Recommended voices for audiobook narration:
- `en_US-amy-medium` – clear, natural female voice
- `en_US-lessac-medium` – warm male voice
- `en_US-libritts-high` – highest quality, slower generation

---

## Usage

### Basic usage

```bash
python main.py input/my_paper.pdf
```

### Run API server (recommended)

```bash
uvicorn api:app --host localhost --port 8000
```

### API endpoints

- `GET /health`
- `POST /api/v1/extract`
- `POST /api/v1/process`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs/{job_id}/metadata`
- `GET /api/v1/jobs/{job_id}/highlights`
- `GET /api/v1/jobs/{job_id}/audio`
- `GET /api/v1/jobs/{job_id}/pdf`

### With a specific voice model

```bash
python main.py input/my_paper.pdf --model piper/models/en_US-lessac-medium.onnx
```

### Skip MP3 output (WAV only)

```bash
python main.py input/my_paper.pdf --no-mp3
```

### Keep the references / bibliography section

```bash
python main.py input/my_paper.pdf --keep-references
```

### Keep intermediate chunk WAV files

```bash
python main.py input/my_paper.pdf --keep-chunks
```

### Custom output directory

```bash
python main.py input/my_paper.pdf --output-dir D:\audiobooks\
```

### Adjust chunk size (default: 400 characters)

```bash
python main.py input/my_paper.pdf --chunk-size 300
```

### All options

```
usage: main.py [-h] [--model MODEL] [--piper PIPER_EXE]
               [--output-dir OUTPUT_DIR] [--no-mp3] [--keep-chunks]
               [--keep-references] [--chunk-size CHUNK_SIZE]
               pdf

positional arguments:
  pdf                   Path to the input PDF file.

options:
  --model MODEL         Path to Piper .onnx model file
  --piper PIPER_EXE     Path to piper.exe
  --output-dir DIR      Root output directory (default: ./output)
  --no-mp3              Skip MP3 conversion, keep WAV only
  --keep-chunks         Keep intermediate chunk WAV files after merging
  --keep-references     Do NOT remove the References/Bibliography section
  --chunk-size N        Target chunk size in characters (default: 400)
```

---

## Output Files

After a successful run you will find:

```
output/
├── markdown/
│   └── my_paper/
│       └── my_paper.md             ← Marker-extracted markdown
├── chunks/
│   ├── my_paper_chunk_0000.txt     ← Text chunks (for inspection)
│   ├── my_paper_chunk_0001.txt
│   └── ...
├── audio/                          ← Deleted automatically unless --keep-chunks
├── alignment/
│   └── my_paper_chunk_highlights.json  ← chunk→PDF highlight map
└── final/
    ├── my_paper_merge_list.txt     ← FFmpeg concat list
    ├── my_paper_audiobook.wav      ← Uncompressed audiobook
    └── my_paper_audiobook.mp3      ← Compressed audiobook (final deliverable)
```

---

## How It Works

### 1. PDF Extraction + Layout Filtering
Marker extraction is combined with DocLayout-YOLO based filtering so narration focuses on readable body text and headings while suppressing many non-narrative regions.

### 2. Text Cleaning
The extracted markdown is cleaned to remove:
- Markdown symbols (`#`, `**`, `*`, etc.)
- Citation references (`[1]`, `[12]`, `[Smith 2020]`)
- Figure / Table captions
- Standalone page numbers
- Hyperlinks and URLs
- The entire References / Bibliography section (configurable)

### 3. Sentence Chunking (NLTK)
The cleaned text is split into speech-friendly chunks using NLTK's sentence tokenizer. Chunks are sized around 400 characters (configurable) to keep Piper's generation fast and reliable. No sentence is ever cut mid-way.

### 4. Audio Generation (Piper TTS)
Piper is called once per chunk via subprocess. Piper reads text from stdin and writes a WAV file per chunk. This approach avoids memory buildup for large documents.

### 5. Audio Merging (FFmpeg)
All chunk WAVs are concatenated using FFmpeg's `concat` demuxer (lossless, no re-encoding). The result is then optionally converted to MP3 using the LAME encoder.

### 6. Chunk Highlight Mapping
Each generated chunk is text-matched to PDF words (PyMuPDF) and stored as normalized polygons for stable PDF area highlighting in the client.

---

## Troubleshooting

### `piper.exe not found`
- Ensure `piper/piper.exe` exists.
- If you placed it elsewhere, pass `--piper path/to/piper.exe`.

### `FFmpeg not found on PATH`
- Install FFmpeg and make sure `ffmpeg.exe` is accessible from the terminal.
- Run `ffmpeg -version` to verify.

### `Marker extraction failed`
- Ensure `marker-pdf` is installed: `pip install marker-pdf`
- Some very old or scanned PDFs may require OCR. Marker supports OCR — check the [Marker documentation](https://github.com/VikParuchuri/marker).
- Try running Marker manually: `python -m marker.scripts.convert_single your.pdf --output_dir output/markdown`

### `Text is empty after cleaning`
- The PDF may be entirely image-based (scanned without OCR). Marker's OCR mode may help.
- Inspect the markdown file under `output/markdown/` to see what Marker extracted.

### `Chunk highlighting seems missing`
- Ensure you are using a newly processed job (highlights are generated per job).
- Check `GET /api/v1/jobs/{job_id}/highlights` for payload presence.

### Audio sounds robotic or unnatural
- Try a higher-quality model such as `en_US-libritts-high`.
- Reduce `--chunk-size` to 250–300 for shorter, more natural phrases.

### MP3 conversion fails
- Ensure your FFmpeg build includes `libmp3lame`. Most Windows builds do.
- Use `--no-mp3` to skip MP3 and keep WAV only.

### Large PDFs run out of memory
- This is unlikely since the pipeline processes one chunk at a time.
- If Marker itself uses too much memory, process the PDF in sections.

---

## Supported PDF Types

| Type | Support |
|---|---|
| Digital / born-digital PDF | Excellent |
| Two-column academic papers | Excellent (Marker handles column order) |
| Scanned PDF with text layer | Good |
| Scanned PDF without text layer | Requires OCR (Marker OCR mode) |
| Password-protected PDF | Not supported |

---

## License

This project is for personal, local use. Ensure you comply with the licenses of:
- [Marker](https://github.com/VikParuchuri/marker) – GPL-3.0
- [Piper TTS](https://github.com/rhasspy/piper) – MIT
- [FFmpeg](https://ffmpeg.org/) – LGPL/GPL
- [NLTK](https://www.nltk.org/) – Apache 2.0
- [DocLayout-YOLO](https://github.com/opendatalab/DocLayout-YOLO)
