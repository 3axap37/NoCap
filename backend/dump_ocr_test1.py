"""
One-shot: dump raw CLOVA OCR output for Test1.pdf with full bbox coords.
Shows (1) raw word-level tokens, (2) after cell-merging, (3) after row-grouping.
"""
import io, os, sys
from dotenv import load_dotenv
load_dotenv(encoding="utf-8-sig")

from pdf2image import convert_from_bytes
from pdf_parser_clova import _call_clova_ocr
from pdf_parser_v2 import _extract_clova_lines
import base64, json, uuid, time, requests

PDF_PATH = "Test1.pdf"
OUT_PATH = "ocr_dump_test1.txt"
POPPLER_PATH = r"C:\poppler\Library\bin"
CLOVA_OCR_INVOKE_URL = os.getenv("CLOVA_OCR_INVOKE_URL", "")
CLOVA_OCR_SECRET = os.getenv("CLOVA_OCR_SECRET", "")

def dump_raw_words(image_bytes: bytes):
    """Call CLOVA and return raw word-level fields (before any merging)."""
    payload = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [{"format": "jpg", "name": "page",
                     "data": base64.b64encode(image_bytes).decode()}],
    }
    resp = requests.post(
        CLOVA_OCR_INVOKE_URL,
        headers={"X-OCR-SECRET": CLOVA_OCR_SECRET, "Content-Type": "application/json"},
        data=json.dumps(payload), timeout=30,
    )
    resp.raise_for_status()
    words = []
    for img_res in resp.json().get("images", []):
        for field in img_res.get("fields", []):
            text = field.get("inferText", "").strip()
            if not text:
                continue
            v = field.get("boundingPoly", {}).get("vertices", [])
            xs = [p.get("x", 0) for p in v[:4]]
            ys = [p.get("y", 0) for p in v[:4]]
            words.append({
                "text": text,
                "conf": round(field.get("inferConfidence", 1.0), 3),
                "x": (min(xs), max(xs)),
                "y": (min(ys), max(ys)),
                "line_break": field.get("lineBreak", True),
            })
    return words


with open(PDF_PATH, "rb") as f:
    pdf_bytes = f.read()

images = convert_from_bytes(pdf_bytes, dpi=300, poppler_path=POPPLER_PATH, fmt="jpeg")

out = open(OUT_PATH, "w", encoding="utf-8")

def p(*args, **kwargs):
    print(*args, **kwargs, file=out)

for page_idx, img in enumerate(images, 1):
    jpeg_buf = io.BytesIO()
    img.save(jpeg_buf, format="JPEG", quality=95)
    jpeg_bytes = jpeg_buf.getvalue()

    p(f"\n{'='*70}")
    p(f"PAGE {page_idx}")
    p(f"{'='*70}")

    # ── 1. Raw word-level tokens ──────────────────────────────────────────
    p(f"\n── 1. RAW WORD-LEVEL (before any merging) ──")
    words = dump_raw_words(jpeg_bytes)
    for i, w in enumerate(words, 1):
        lb = " ←LINE_BREAK" if w["line_break"] else ""
        p(f"  W{i:03d}  x={w['x'][0]:6.0f}-{w['x'][1]:6.0f}  y={w['y'][0]:5.0f}-{w['y'][1]:5.0f}  "
          f"conf={w['conf']:.2f}  [{w['text']}]{lb}")

    # ── 2. After CLOVA cell-merging (_call_clova_ocr) ────────────────────
    p(f"\n── 2. AFTER CLOVA CELL-MERGE (_call_clova_ocr) ──")
    cells = _call_clova_ocr(jpeg_bytes)
    for i, (bbox, text, conf) in enumerate(cells, 1):
        x1, y1 = bbox[0]
        x2, y2 = bbox[2]
        p(f"  C{i:03d}  x={x1:6.0f}-{x2:6.0f}  y={y1:5.0f}-{y2:5.0f}  conf={conf:.2f}  [{text}]")

    # ── 3. After pdf_parser_v2 row-grouping (_extract_clova_lines) ───────
    p(f"\n── 3. AFTER ROW-GROUPING (_extract_clova_lines) ──")
    rows = _extract_clova_lines(jpeg_bytes, page_idx)
    for i, row in enumerate(rows, 1):
        p(f"  R{i:03d}  {row}")

out.close()
print(f"Done → {OUT_PATH}")
