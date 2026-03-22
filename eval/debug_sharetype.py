"""
debug_sharetype.py — Test27/Test31 shareType empty 원인 진단.

파이프라인 각 단계의 share_type 관련 중간값을 dump.

Usage:
    python debug_sharetype.py Test27
    python debug_sharetype.py Test31
    python debug_sharetype.py Test27 Test31
"""

import io
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(EVAL_DIR)
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)

from dotenv import load_dotenv
load_dotenv(encoding="utf-8-sig")

from pdf2image import convert_from_bytes
from pdf_parser_v2 import (
    _call_clova_ocr_words,
    _reconstruct_rows_from_words,
    _build_ocr_suffix,
    _extract_via_vlm,
    _post_validate,
    _extract_ocr_total_from_words,
    _normalize_share_type,
    _KNOWN_SHARE_TYPES,
    _choose_document_dpi,
    _parse_count,
    _SC_PAT,
    CLOVA_OCR_INVOKE_URL,
    CLOVA_OCR_SECRET,
    POPPLER_PATH,
)

PDFS_DIR = os.path.join(EVAL_DIR, "pdfs")
DEBUG_DIR = os.path.join(EVAL_DIR, "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

# Share type keywords to search in OCR words
_ST_KEYWORDS = ["보통주", "우선주", "전환", "상환", "RCPS", "종류주식", "의결권", "보통", "우선"]


def diagnose(test_name: str):
    pdf_path = os.path.join(PDFS_DIR, f"{test_name}.pdf")
    if not os.path.exists(pdf_path):
        print(f"  {pdf_path} not found!")
        return

    out_path = os.path.join(DEBUG_DIR, f"{test_name.lower()}_sharetype_trace.txt")
    lines: list[str] = []

    def w(text: str = ""):
        lines.append(text)
        try:
            print(text)
        except UnicodeEncodeError:
            print(text.encode("utf-8", errors="replace").decode("utf-8"))

    w(f"{'='*60}")
    w(f"  ShareType Diagnosis: {test_name}")
    w(f"{'='*60}")

    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    dpi = _choose_document_dpi(file_bytes)
    images = convert_from_bytes(file_bytes, dpi=dpi, poppler_path=POPPLER_PATH, fmt="png")

    for page_num, img in enumerate(images, 1):
        w(f"\n--- Page {page_num} ---")

        # PNG for VLM
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_bytes = png_buf.getvalue()

        # JPEG for CLOVA
        jpeg_buf = io.BytesIO()
        img.save(jpeg_buf, format="JPEG", quality=95)

        # =====================================================================
        # Stage 1: CLOVA OCR raw words — share type keyword search
        # =====================================================================
        w(f"\n[Stage 1] OCR words containing share type keywords")
        try:
            raw_words = _call_clova_ocr_words(jpeg_buf.getvalue())
        except Exception as e:
            w(f"  CLOVA OCR failed: {e}")
            raw_words = []

        st_words_found = []
        for word in raw_words:
            text = word.get("text", "")
            for kw in _ST_KEYWORDS:
                if kw in text:
                    st_words_found.append(word)
                    break
            # Also check if _normalize_share_type produces a known type
            nt = _normalize_share_type(text)
            if nt in _KNOWN_SHARE_TYPES and word not in st_words_found:
                st_words_found.append(word)

        if st_words_found:
            for sw in st_words_found:
                w(f"  word: \"{sw['text']}\", x1={sw['x1']:.0f}, x2={sw['x2']:.0f}, "
                  f"y1={sw['y1']:.0f}, y2={sw['y2']:.0f}, yc={sw['yc']:.0f}")
        else:
            w("  None found")

        # =====================================================================
        # Stage 2 & 3: _reconstruct_rows_from_words + has_share_type_col
        # =====================================================================
        w(f"\n[Stage 2] Reconstructed rows from OCR words")
        ocr_candidates = _reconstruct_rows_from_words(raw_words) if raw_words else []
        if ocr_candidates:
            for i, rc in enumerate(ocr_candidates):
                w(f"  Row {i}: name=\"{rc.name}\", share_type=\"{rc.share_type}\", "
                  f"share_count={rc.share_count}, raw_cells={rc.raw_cells}")
        else:
            w("  (no rows reconstructed)")

        # Manually compute has_share_type_col like the function does
        w(f"\n[Stage 3] has_share_type_col check")
        if raw_words:
            # Need to find sc_x1_min first (replicating logic)
            _SC_PAT2 = re.compile(r'^\d{2,4}$')
            avg_h = sum(wd["y2"] - wd["y1"] for wd in raw_words) / len(raw_words)

            sc_words = [
                wd for wd in raw_words
                if _SC_PAT.match(wd["text"].strip())
            ]
            if sc_words:
                if len(sc_words) >= 2:
                    max_x1 = max(wd["x1"] for wd in sc_words)
                    sc_words = [wd for wd in sc_words if wd["x1"] >= max_x1 * 0.75]
                if sc_words:
                    sc_x1_min = min(wd["x1"] for wd in sc_words)
                    has_st_col = any(
                        wd["x1"] < sc_x1_min
                        and _normalize_share_type(wd["text"]) in _KNOWN_SHARE_TYPES
                        for wd in raw_words
                    )
                    w(f"  sc_x1_min = {sc_x1_min:.0f}")
                    w(f"  has_share_type_col = {has_st_col}")

                    # Show which words match the share_type_col check
                    if not has_st_col:
                        w("  Detail: words that normalize to known share types:")
                        for wd in raw_words:
                            nt = _normalize_share_type(wd["text"])
                            if nt in _KNOWN_SHARE_TYPES:
                                w(f"    \"{wd['text']}\" -> \"{nt}\", x1={wd['x1']:.0f} "
                                  f"(< sc_x1_min={sc_x1_min:.0f}? {wd['x1'] < sc_x1_min})")
                else:
                    w("  (no sc_words after x-filter)")
            else:
                w("  (no share-count words found)")
        else:
            w("  (no OCR words)")

        # =====================================================================
        # Stage 4: OCR suffix sent to VLM
        # =====================================================================
        w(f"\n[Stage 4] OCR suffix sent to VLM")
        clova_rows = [rc.raw_cells for rc in ocr_candidates]
        if clova_rows:
            suffix = _build_ocr_suffix(clova_rows)
            suffix_lines = suffix.strip().split("\n")
            w(f"  (total {len(suffix_lines)} lines, showing first 15)")
            for sl in suffix_lines[:15]:
                w(f"  {sl}")
            if len(suffix_lines) > 15:
                w(f"  ... ({len(suffix_lines) - 15} more lines)")
        else:
            w("  (no clova_rows, empty suffix)")

        # =====================================================================
        # Stage 5: VLM response
        # =====================================================================
        w(f"\n[Stage 5] VLM response")
        clova_suffix = _build_ocr_suffix(clova_rows) if clova_rows else ""
        vlm_result = _extract_via_vlm(png_bytes, page_num, clova_suffix)
        if vlm_result is not None:
            for i, rc in enumerate(vlm_result):
                w(f"  Item {i}: name=\"{rc.name}\", shareType=\"{rc.share_type}\", "
                  f"shareCount={rc.share_count}")
        else:
            w("  VLM returned None")

        # =====================================================================
        # Stage 6: OCR share_type correction map
        # =====================================================================
        w(f"\n[Stage 6] OCR share_type map")
        if clova_rows:
            ocr_st_map: dict[int, str] = {}
            for ocr_row in clova_rows:
                if len(ocr_row) != 3:
                    continue
                sc_val = _parse_count(ocr_row[-1])
                if not sc_val:
                    continue
                ocr_nt = _normalize_share_type(ocr_row[1]) if ocr_row[1] else ""
                if ocr_nt not in _KNOWN_SHARE_TYPES:
                    continue
                if sum(1 for r in clova_rows if _parse_count(r[-1]) == sc_val) == 1:
                    ocr_st_map[sc_val] = ocr_nt
            if ocr_st_map:
                for sc, st in sorted(ocr_st_map.items()):
                    w(f"  {sc:>10,}: \"{st}\"")
            else:
                w("  Empty (no 3-cell rows with valid share types)")
                w("  Detail — clova_rows cell counts:")
                for i, row in enumerate(clova_rows):
                    w(f"    Row {i}: {len(row)} cells -> {row}")
        else:
            w("  Empty (no clova_rows)")

        # =====================================================================
        # Stage 7: Final rows after _post_validate + OCR correction
        # =====================================================================
        w(f"\n[Stage 7] Final rows (after post_validate + ocr_st_correction)")
        if vlm_result is not None:
            validated = _post_validate(vlm_result)
            page_rows = validated["shareholders"]

            # Apply OCR st correction (replicate pipeline logic)
            if clova_rows and ocr_st_map:
                from pdf_parser_v2 import RowCandidate as RC
                corrected = []
                for rc in page_rows:
                    new_st = ocr_st_map.get(rc.share_count or 0)
                    if new_st and new_st != rc.share_type:
                        corrected.append(RC(
                            name=rc.name, share_type=new_st,
                            share_count=rc.share_count, source=rc.source,
                            row_index=rc.row_index, confidence=rc.confidence,
                            flags=rc.flags + ["type_ocr_override"],
                            raw_cells=rc.raw_cells,
                        ))
                    else:
                        corrected.append(rc)
                page_rows = corrected

            for i, rc in enumerate(page_rows):
                w(f"  Row {i}: name=\"{rc.name}\", share_type=\"{rc.share_type}\", "
                  f"share_count={rc.share_count}, flags={rc.flags}")
        else:
            w("  (VLM returned None, no final rows)")

    # Write output file
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  -> Saved to {out_path}")


def main():
    tests = sys.argv[1:] if len(sys.argv) > 1 else ["Test27", "Test31"]
    for test_name in tests:
        diagnose(test_name)
        print()


if __name__ == "__main__":
    main()
