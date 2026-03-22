"""Trace second-pass sc_words detection for Test4 to find why '400' is missed."""
import io, os, re, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(encoding="utf-8-sig")
from pdf2image import convert_from_bytes
from pdf_parser_clova import _call_clova_ocr_words
from pdf_parser import _is_skip_row, _normalize_share_type, _KNOWN_SHARE_TYPES

POPPLER_PATH = r"C:\poppler\Library\bin"
_SC_PAT = re.compile(r'^\d{1,3}(?:,\d{3})+주?$|^\d{3,}주$')
_SC_PAT2 = re.compile(r'^\d{2,4}$')

with open("Test4.pdf", "rb") as f:
    pdf_bytes = f.read()

images = convert_from_bytes(pdf_bytes, dpi=300, poppler_path=POPPLER_PATH, fmt="jpeg")
img = images[0]
buf = io.BytesIO()
img.save(buf, format="JPEG", quality=95)
words = _call_clova_ocr_words(buf.getvalue())

avg_h = sum(w["y2"] - w["y1"] for w in words) / len(words)
print(f"avg_h = {avg_h:.1f}")

def _on_skip_row(w):
    return any(
        _is_skip_row(other["text"])
        for other in words
        if abs(other["yc"] - w["yc"]) <= avg_h * 1.5
    )

# First-pass
sc_words = [w for w in words if _SC_PAT.match(w["text"].strip()) and not _on_skip_row(w)]
print(f"\nFirst-pass sc_words ({len(sc_words)}):")
for w in sc_words:
    print(f"  '{w['text']}'  y={w['yc']:.1f}  x={w['x1']:.0f}-{w['x2']:.0f}")

if len(sc_words) >= 2:
    max_x1 = max(w["x1"] for w in sc_words)
    sc_words = [w for w in sc_words if w["x1"] >= max_x1 * 0.75]

sc_x1_min = min(w["x1"] for w in sc_words)
sc_x2_max = max(w["x2"] for w in sc_words)
print(f"\nsc_x1_min={sc_x1_min:.0f}  sc_x2_max={sc_x2_max:.0f}")
print(f"x-range filter: [{sc_x1_min*0.85:.0f}, {sc_x2_max*1.15:.0f}]")

existing_ycs = {w["yc"] for w in sc_words}
print(f"existing_ycs: {sorted(existing_ycs)}")
print(f"avg_h*0.5 = {avg_h*0.5:.1f}")

# Show ALL _SC_PAT2 candidates and why they pass/fail
print("\n--- All _SC_PAT2 candidate words ---")
for w in words:
    txt = w["text"].strip()
    if not _SC_PAT2.match(txt):
        continue
    x1_ok = w["x1"] >= sc_x1_min * 0.85
    x2_ok = w["x2"] <= sc_x2_max * 1.15
    skip_ok = not _on_skip_row(w)
    yc_ok = not any(abs(w["yc"] - yc) <= avg_h * 0.5 for yc in existing_ycs)
    close_ycs = [yc for yc in existing_ycs if abs(w["yc"] - yc) <= avg_h * 0.5]
    status = "PASS" if (x1_ok and x2_ok and skip_ok and yc_ok) else "FAIL"
    fail_reasons = []
    if not x1_ok: fail_reasons.append(f"x1={w['x1']:.0f}<{sc_x1_min*0.85:.0f}")
    if not x2_ok: fail_reasons.append(f"x2={w['x2']:.0f}>{sc_x2_max*1.15:.0f}")
    if not skip_ok: fail_reasons.append("skip_row")
    if not yc_ok: fail_reasons.append(f"y_close_to {close_ycs}")
    reason_str = ", ".join(fail_reasons) if fail_reasons else ""
    print(f"  {status}: '{txt}'  y={w['yc']:.1f}  x={w['x1']:.0f}-{w['x2']:.0f}  {reason_str}")

# Second-pass
sc2_words = [
    w for w in words
    if _SC_PAT2.match(w["text"].strip())
    and not _on_skip_row(w)
    and w["x1"] >= sc_x1_min * 0.85
    and w["x2"] <= sc_x2_max * 1.15
    and not any(abs(w["yc"] - yc) <= avg_h * 0.5 for yc in existing_ycs)
]
print(f"\nSecond-pass sc2_words ({len(sc2_words)}):")
for w in sc2_words:
    print(f"  '{w['text']}'  y={w['yc']:.1f}  x={w['x1']:.0f}-{w['x2']:.0f}")
