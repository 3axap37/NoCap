"""
Run: python debug_pdf.py <your_file.pdf>
Prints what each extraction stage sees, so you can diagnose why parsing fails.
"""
import io
import sys

import pdfplumber

PDF_PATH = sys.argv[1] if len(sys.argv) > 1 else input("PDF path: ").strip()
file_bytes = open(PDF_PATH, "rb").read()

# ---------------------------------------------------------------------------
# Stage 1: pdfplumber tables
# ---------------------------------------------------------------------------
print("\n=== STAGE 1: pdfplumber tables ===")
with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
    print(f"Pages: {len(pdf.pages)}")
    for i, page in enumerate(pdf.pages, 1):
        tables = page.extract_tables()
        print(f"\n[Page {i}] {len(tables)} table(s) found")
        for t, table in enumerate(tables):
            print(f"  Table {t+1}: {len(table)} rows x {len(table[0]) if table else 0} cols")
            for row in table[:5]:
                print(f"    {row}")

# ---------------------------------------------------------------------------
# Stage 2: pdfplumber raw text
# ---------------------------------------------------------------------------
print("\n=== STAGE 2: pdfplumber raw text ===")
with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
    for i, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        print(f"\n[Page {i}] {len(text)} chars extracted")
        for line in text.splitlines()[:20]:
            print(f"  {repr(line)}")
        if not text.strip():
            print("  (no text — likely a scanned image)")

# ---------------------------------------------------------------------------
# Stage 3: EasyOCR — raw boxes, reconstructed table, and column mapping
# ---------------------------------------------------------------------------
print("\n=== STAGE 3: EasyOCR ===")
try:
    import numpy as np
    from pdf2image import convert_from_bytes
    import easyocr
    from pdf_parser import _reconstruct_table_from_ocr, _build_column_map, _find_header_row

    images = convert_from_bytes(file_bytes, dpi=300, poppler_path=r"C:\poppler\Library\bin")
    print(f"{len(images)} page image(s) converted")

    reader = easyocr.Reader(["ko", "en"], gpu=False)

    for i, img in enumerate(images, 1):
        print(f"\n--- Page {i}: raw OCR boxes ---")
        results = reader.readtext(np.array(img), detail=1, paragraph=False)
        print(f"  {len(results)} text box(es) detected")
        for bbox, text, conf in results:
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            print(f"  conf={conf:.2f}  x={min(xs):6.0f}  y={min(ys):6.0f} | {repr(text)}")

        print(f"\n--- Page {i}: reconstructed table ---")
        table = _reconstruct_table_from_ocr(results)
        if not table:
            print("  (no table reconstructed)")
        else:
            print(f"  {len(table)} rows x {len(table[0])} cols")
            for r, row in enumerate(table):
                print(f"  row {r:2d}: {row}")

            print(f"\n--- Page {i}: column mapping ---")
            header_idx = _find_header_row(table)
            if header_idx is None:
                print("  Header row NOT found — '주주명' keyword missing from all rows")
                print("  Header candidates (first 3 rows):")
                for row in table[:3]:
                    print(f"    {row}")
            else:
                headers = [str(c).strip() if c else "" for c in table[header_idx]]
                print(f"  Header row index: {header_idx}")
                print(f"  Headers: {headers}")
                col_map = _build_column_map(headers)
                print(f"  Column map: {col_map}")
                print(f"\n  Data rows (name col={col_map['name']}, "
                      f"type col={col_map['type']}, count col={col_map['count']}):")
                for row in table[header_idx + 1:]:
                    name_val = row[col_map['name']] if col_map['name'] is not None else "N/A"
                    type_val = row[col_map['type']] if col_map['type'] is not None else "N/A"
                    count_val = row[col_map['count']] if col_map['count'] is not None else "N/A"
                    print(f"    name={repr(name_val)}  type={repr(type_val)}  count={repr(count_val)}")

except ImportError as e:
    print(f"  OCR dependencies not available: {e}")
except Exception as e:
    import traceback
    traceback.print_exc()
