"""
Detailed failure classification for all eval tests.

Usage:
  python run_detailed_classification.py          # run both v2 and v3
  python run_detailed_classification.py --parser v2   # run v2 only
  python run_detailed_classification.py --parser v3   # run v3 only

Outputs:
  results/detailed_classification_v2.txt
  results/detailed_classification_v3.txt
"""

import json
import os
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

PDFS_DIR = os.path.join(EVAL_DIR, "pdfs")
GROUND_TRUTH_PATH = os.path.join(EVAL_DIR, "ground_truth.jsonl")
RESULTS_DIR = os.path.join(EVAL_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Load ground truth
# ---------------------------------------------------------------------------
def load_ground_truth():
    expected = {}
    gt_dicts = {}
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            doc_id = obj.get("document_id", "")
            rows = []
            raw_dicts = []
            for sh in obj.get("shareholders", []):
                name = sh.get("name", "")
                st = sh.get("share_type") or ""
                sc = sh.get("share_count", 0)
                rows.append((name, st, sc))
                raw_dicts.append({"name": name, "shareType": st, "shareCount": sc})
            expected[doc_id] = rows
            gt_dicts[doc_id] = raw_dicts
    return expected, gt_dicts


# ---------------------------------------------------------------------------
# Run one test and return formatted text
# ---------------------------------------------------------------------------
def run_one_test(pipeline_fn, pdf_path, doc_id, expected, gt_dicts):
    from parser_eval import (
        _names_match_for_eval,
        classify_failures,
        _ALL_FAILURE_TYPES,
        CORRECT,
    )
    from parser_types import RowCandidate

    lines = []

    try:
        with open(pdf_path, "rb") as f:
            file_bytes = f.read()
        parse_result = pipeline_fn(file_bytes)
        shareholders = parse_result.shareholders
    except Exception as e:
        lines.append(f"  ERROR: {e}")
        return "\n".join(lines)

    # Print extracted shareholders
    if shareholders:
        lines.append(f"  {'#':<4} {'주주명':<35} {'주식종류':<15} {'주식수':>12}")
        lines.append(f"  {'-'*4} {'-'*35} {'-'*15} {'-'*12}")
        for i, sh in enumerate(shareholders, 1):
            lines.append(f"  {i:<4} {sh.name:<35} {sh.shareType:<15} {sh.shareCount:>12,}")
    else:
        lines.append("  (no shareholders parsed)")

    # Compare with ground truth
    if doc_id not in expected:
        lines.append("  (no ground truth available — skipped)")
        return "\n".join(lines)

    exp = expected[doc_id]
    actual = [(sh.name, sh.shareType, sh.shareCount) for sh in shareholders]

    rows_match = len(exp) == len(actual) and all(
        _names_match_for_eval(e[0], a[0]) and e[1] == a[1] and e[2] == a[2]
        for e, a in zip(exp, actual)
    )

    if rows_match:
        lines.append(f"  Result: PASS ({len(actual)} shareholders match)")
        return "\n".join(lines)

    lines.append("  Result: FAIL")

    # Missing / Extra
    missing = set(exp) - set(actual)
    extra = set(actual) - set(exp)
    if missing:
        lines.append("  Missing:")
        for row in sorted(missing, key=lambda r: exp.index(r) if r in exp else 999):
            lines.append(f"    - {row[0]} / {row[1]} / {row[2]:,}")
    if extra:
        lines.append("  Extra:")
        for row in sorted(extra, key=lambda r: actual.index(r) if r in actual else 999):
            lines.append(f"    + {row[0]} / {row[1]} / {row[2]:,}")

    # Failure classification
    all_final_rows = []
    for trace in parse_result.traces:
        all_final_rows.extend(trace.final_rows)

    if not all_final_rows:
        # Try building RowCandidates from shareholders for classification
        for i, sh in enumerate(shareholders):
            all_final_rows.append(RowCandidate(
                name=sh.name,
                share_type=sh.shareType,
                share_count=sh.shareCount,
                source="unknown",
                row_index=i,
            ))

    gt_entries = gt_dicts[doc_id]
    details = classify_failures(all_final_rows, gt_entries, page_num=0)

    total_gt = len(gt_entries)
    correct = sum(1 for d in details if d["type"] == CORRECT)
    accuracy = correct / total_gt if total_gt > 0 else 0.0

    failure_counts = {ft: 0 for ft in _ALL_FAILURE_TYPES}
    for d in details:
        if d["type"] in failure_counts:
            failure_counts[d["type"]] += 1

    lines.append("")
    lines.append(f"  Failure Classification (accuracy: {accuracy:.0%})")
    for ft, count in failure_counts.items():
        if count > 0:
            lines.append(f"    {ft}: {count}")

    for detail in details:
        if detail["type"] == CORRECT:
            continue
        gt_info = detail.get("ground_truth")
        ex_info = detail.get("extracted")
        gt_str = f"{gt_info['name']}/{gt_info['shareCount']:,}" if gt_info else "-"
        ex_str = f"{ex_info['name']}/{ex_info['shareCount']:,}" if ex_info else "-"
        src = detail.get("source") or "-"
        flags = detail.get("flags", [])
        flags_str = f" [{', '.join(flags)}]" if flags else ""
        lines.append(
            f"    [{detail['type']}] GT: {gt_str} -> EX: {ex_str} (src={src}){flags_str}"
        )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Run all tests for a parser version
# ---------------------------------------------------------------------------
def run_all(parser_version):
    expected, gt_dicts = load_ground_truth()

    if parser_version == "v3":
        from pdf_parser_v3 import _parse_pipeline_v3 as pipeline_fn
        label = "V3"
    else:
        from pdf_parser_v2 import _parse_pipeline_v2 as pipeline_fn
        label = "V2"

    # Discover all PDFs
    all_pdfs = sorted(
        [f for f in os.listdir(PDFS_DIR) if f.startswith("Test") and f.endswith(".pdf")],
        key=lambda f: int(f.replace("Test", "").replace(".pdf", "")),
    )

    output_lines = []
    total = passed = failed = 0

    for fname in all_pdfs:
        pdf_path = os.path.join(PDFS_DIR, fname)
        doc_id = fname.replace(".pdf", "")

        header = f"\n{'=' * 60}\n  {fname}\n{'=' * 60}\n\n  [{label}]"
        print(f"  Running {fname} [{label}]...", flush=True)

        result_text = run_one_test(pipeline_fn, pdf_path, doc_id, expected, gt_dicts)

        output_lines.append(header)
        output_lines.append(result_text)

        if "Result: PASS" in result_text:
            total += 1
            passed += 1
        elif "Result: FAIL" in result_text:
            total += 1
            failed += 1

    # Summary
    summary = f"\n{'=' * 60}\n  Summary: {passed}/{total} passed"
    if failed:
        summary += f"  ({failed} failed)"
    summary += f"\n{'=' * 60}"
    output_lines.append(summary)

    # Write to file
    out_path = os.path.join(RESULTS_DIR, f"detailed_classification_{parser_version}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n  Wrote {out_path}")
    print(f"  {passed}/{total} passed ({failed} failed)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    versions = ["v2", "v3"]

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--parser" and i + 1 < len(args):
            versions = [args[i + 1]]
            i += 2
        elif args[i].startswith("--parser="):
            versions = [args[i].split("=", 1)[1]]
            i += 1
        else:
            i += 1

    for ver in versions:
        print(f"\n{'#' * 60}")
        print(f"  Running {ver.upper()} eval (36 tests)")
        print(f"{'#' * 60}")
        run_all(ver)
