"""Print OCR-reconstructed rows for each test PDF."""
import io, os, sys
from dotenv import load_dotenv
load_dotenv(encoding="utf-8-sig")
from pdf2image import convert_from_bytes
from pdf_parser_clova import _call_clova_ocr_words
from pdf_parser_v2 import _reconstruct_rows_from_words, _extract_ocr_total_from_words

POPPLER_PATH = r"C:\poppler\Library\bin"
TESTS = ["Test2", "Test3", "Test4", "Test6"]

for name in TESTS:
    pdf = f"{name}.pdf"
    if not os.path.exists(pdf):
        continue
    with open(pdf, "rb") as f:
        pdf_bytes = f.read()
    images = convert_from_bytes(pdf_bytes, dpi=300, poppler_path=POPPLER_PATH, fmt="jpeg")
    for pg, img in enumerate(images):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        words = _call_clova_ocr_words(buf.getvalue())
        rows = _reconstruct_rows_from_words(words)
        total = _extract_ocr_total_from_words(words)
        print(f"\n=== {name} page {pg+1} (ocr_total={total}) ===")
        for i, row in enumerate(rows, 1):
            print(f"  {i}: {row}")
