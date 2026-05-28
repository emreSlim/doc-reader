"""
pdf_tts/layout_filter.py
------------------------
Pretrained layout filtering using DocLayout-YOLO.

This module uses the DocStructBench-pretrained DocLayout-YOLO model to detect
high-level document regions on rendered PDF pages. It is used to keep only
regions likely to contain narratable content (`plain text`, `title`) and to
suppress figures, captions, tables, formulas, and many page-noise regions
without any task-specific training data.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from huggingface_hub import hf_hub_download

from .logger import log

DOC_LAYOUT_REPO_ID = "juliozhao/DocLayout-YOLO-DocStructBench"
DOC_LAYOUT_FILENAME = "doclayout_yolo_docstructbench_imgsz1024.pt"
DEFAULT_ALLOWED_LABELS = {"plain text", "title"}
_DEFAULT_RENDER_SCALE = 1.5
_DEFAULT_CONFIDENCE = 0.20

_LAYOUT_MODEL = None


def get_layout_model():
    """Load and cache the pretrained DocLayout-YOLO model."""
    global _LAYOUT_MODEL
    if _LAYOUT_MODEL is not None:
        return _LAYOUT_MODEL

    from doclayout_yolo import YOLOv10

    checkpoint = hf_hub_download(
        repo_id=DOC_LAYOUT_REPO_ID,
        filename=DOC_LAYOUT_FILENAME,
    )
    _LAYOUT_MODEL = YOLOv10(checkpoint)
    log.info("Loaded DocLayout-YOLO model from %s", checkpoint)
    return _LAYOUT_MODEL


def _render_pdf_pages(pdf_path: Path, scale: float) -> tuple[list[str], list[dict[str, Any]], tempfile.TemporaryDirectory]:
    """Render PDF pages to temporary PNG files for layout inference."""
    import fitz

    tmp_dir = tempfile.TemporaryDirectory(prefix="tts_reader_layout_")
    image_paths: list[str] = []
    page_meta: list[dict[str, Any]] = []

    doc = fitz.open(str(pdf_path))
    try:
        for page_index, page in enumerate(doc):
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            image_path = str(Path(tmp_dir.name) / f"page_{page_index:04d}.png")
            pix.save(image_path)
            image_paths.append(image_path)
            page_meta.append(
                {
                    "page_index": page_index,
                    "pdf_width": float(page.rect.width),
                    "pdf_height": float(page.rect.height),
                    "render_scale": scale,
                }
            )
    finally:
        doc.close()

    return image_paths, page_meta, tmp_dir


def detect_layout_regions(
    pdf_path: Path,
    *,
    device: str = "cpu",
    confidence: float = _DEFAULT_CONFIDENCE,
    render_scale: float = _DEFAULT_RENDER_SCALE,
    allowed_labels: set[str] | None = None,
) -> dict[int, list[dict[str, Any]]]:
    """
    Run DocLayout-YOLO on each PDF page and return page-indexed regions.

    Bounding boxes are converted back to PDF coordinate space.
    """
    allowed_labels = allowed_labels or DEFAULT_ALLOWED_LABELS
    model = get_layout_model()

    image_paths, page_meta, tmp_dir = _render_pdf_pages(pdf_path, render_scale)
    try:
        results = model.predict(image_paths, imgsz=1024, conf=confidence, device=device)
        regions_by_page: dict[int, list[dict[str, Any]]] = {}

        for page_info, result in zip(page_meta, results):
            scale = page_info["render_scale"]
            page_regions: list[dict[str, Any]] = []
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                regions_by_page[page_info["page_index"]] = []
                continue

            for box in boxes:
                cls_id = int(box.cls.item())
                label = result.names[cls_id]
                conf = float(box.conf.item())
                xyxy = box.xyxy[0].tolist()
                pdf_bbox = [float(v / scale) for v in xyxy]
                page_regions.append(
                    {
                        "label": label,
                        "confidence": conf,
                        "bbox": pdf_bbox,
                        "keep": label in allowed_labels,
                    }
                )

            regions_by_page[page_info["page_index"]] = page_regions
    finally:
        tmp_dir.cleanup()

    return regions_by_page


def bbox_overlap_ratio(inner_bbox: list[float], outer_bbox: list[float]) -> float:
    """Return intersection-over-area(inner_bbox)."""
    x1 = max(inner_bbox[0], outer_bbox[0])
    y1 = max(inner_bbox[1], outer_bbox[1])
    x2 = min(inner_bbox[2], outer_bbox[2])
    y2 = min(inner_bbox[3], outer_bbox[3])

    if x2 <= x1 or y2 <= y1:
        return 0.0

    inter_area = (x2 - x1) * (y2 - y1)
    inner_area = max((inner_bbox[2] - inner_bbox[0]) * (inner_bbox[3] - inner_bbox[1]), 1e-6)
    return float(inter_area / inner_area)


def block_is_kept_by_layout(
    block_bbox: list[float],
    page_regions: list[dict[str, Any]],
    *,
    min_overlap_ratio: float = 0.35,
) -> tuple[bool, list[dict[str, Any]]]:
    """Decide whether a text block should be kept based on kept layout regions."""
    matched_regions: list[dict[str, Any]] = []
    for region in page_regions:
        overlap = bbox_overlap_ratio(block_bbox, region["bbox"])
        if overlap >= min_overlap_ratio:
            enriched = dict(region)
            enriched["overlap_ratio"] = overlap
            matched_regions.append(enriched)

    keep = any(region["keep"] for region in matched_regions)
    return keep, matched_regions
