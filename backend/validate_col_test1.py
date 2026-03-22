"""
Validate column-based reconstruction on Test1.pdf (single CLOVA call).
"""
import io, os, sys
from dotenv import load_dotenv
load_dotenv(encoding="utf-8-sig")

from pdf2image import convert_from_bytes
from pdf_parser_clova import _call_clova_ocr_words
from pdf_parser_v2 import _reconstruct_rows_from_words, _extract_ocr_total_from_words

PDF_PATH = "Test1.pdf"
POPPLER_PATH = r"C:\poppler\Library\bin"

EXPECTED = [
    ("김주곤",                              "보통주", "93,000"),
    ("오세준",                              "보통주",  "5,000"),
    ("김용환",                              "보통주",  "2,000"),
    ("데일리 골든아워 바이오 헬스케어 펀드3호", "우선주",  "8,000"),
    ("서울대 STH 창업초기 벤처투자조합",       "우선주",  "6,000"),
    ("크립톤-엔젤링크 7호 개인투자조합",       "우선주",  "1,901"),
]

with open(PDF_PATH, "rb") as f:
    pdf_bytes = f.read()

images = convert_from_bytes(pdf_bytes, dpi=300, poppler_path=POPPLER_PATH, fmt="jpeg")
img = images[0]

jpeg_buf = io.BytesIO()
img.save(jpeg_buf, format="JPEG", quality=95)
raw_words = _call_clova_ocr_words(jpeg_buf.getvalue())

print(f"\n[raw words: {len(raw_words)}]")

ocr_total = _extract_ocr_total_from_words(raw_words)
print(f"[ocr_total detected: {ocr_total}]  (expected: 115,901)")

rows = _reconstruct_rows_from_words(raw_words)

print("\n=== RECONSTRUCTED ROWS ===")
for i, row in enumerate(rows, 1):
    print(f"  {i}: {row}")

print("\n=== VALIDATION ===")
passed = 0
for exp_name, exp_type, exp_count in EXPECTED:
    found = any(row[0] == exp_name and row[-1] == exp_count for row in rows)
    status = "PASS" if found else "FAIL"
    if found:
        passed += 1
    print(f"  [{status}] {exp_name} ({exp_count})")

print(f"\n{passed}/{len(EXPECTED)} passed")
sys.exit(0 if passed == len(EXPECTED) else 1)
