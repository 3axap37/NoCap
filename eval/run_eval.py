"""
Eval runner for shareholder PDF parser.

Usage:
  python run_eval.py                     # run all tests
  python run_eval.py --tests 1,2,3       # run only Test1, Test2, Test3
  python run_eval.py --tests 7-13        # run Test7 through Test13

Ground truth is loaded from ground_truth.jsonl.
Results are written to results/result_v2.jsonl.
"""

import json
import os
import sys

# ---------------------------------------------------------------------------
# Path setup: add backend/ to sys.path so we can import parsers
# ---------------------------------------------------------------------------
EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(EVAL_DIR)
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
sys.path.insert(0, BACKEND_DIR)

# Backend modules need .env and working dir set to backend/
os.chdir(BACKEND_DIR)
from dotenv import load_dotenv

load_dotenv(encoding="utf-8-sig")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PDFS_DIR = os.path.join(EVAL_DIR, "pdfs")
GROUND_TRUTH_PATH = os.path.join(EVAL_DIR, "ground_truth.jsonl")
RESULTS_DIR = os.path.join(EVAL_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33m!\033[0m"


# ---------------------------------------------------------------------------
# Ground truth loader
# ---------------------------------------------------------------------------
def load_ground_truth(path: str) -> tuple[dict[str, list[tuple[str, str, int]]], dict[str, list[dict]]]:
    """Load ground_truth.jsonl.

    Returns:
        (expected, gt_dicts)
        expected: {document_id: [(name, share_type, count)]} — for pass/fail check
        gt_dicts: {document_id: [{"name", "shareType", "shareCount"}]} — for classify_failures
    """
    expected = {}
    gt_dicts = {}
    try:
        with open(path, encoding="utf-8") as f:
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
                    st = sh.get("share_type") or ""  # null → ""
                    sc = sh.get("share_count", 0)
                    rows.append((name, st, sc))
                    raw_dicts.append({"name": name, "shareType": st, "shareCount": sc})
                expected[doc_id] = rows
                gt_dicts[doc_id] = raw_dicts
    except FileNotFoundError:
        print(f"  Warning: ground truth not found at {path}")
    return expected, gt_dicts


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
def parse_args():
    test_nums = None
    parser_version = "v2"

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--tests" and i + 1 < len(args):
            test_nums = _parse_test_nums(args[i + 1])
            i += 2
        elif args[i].startswith("--tests="):
            test_nums = _parse_test_nums(args[i].split("=", 1)[1])
            i += 1
        elif args[i] == "--parser" and i + 1 < len(args):
            parser_version = args[i + 1]
            i += 2
        elif args[i].startswith("--parser="):
            parser_version = args[i].split("=", 1)[1]
            i += 1
        else:
            i += 1

    return test_nums, parser_version


def _parse_test_nums(s: str) -> list[int]:
    """Parse '1,2,3' or '7-13' or '1,3,7-13' into sorted list of ints."""
    nums = set()
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            nums.update(range(int(lo), int(hi) + 1))
        else:
            nums.add(int(part))
    return sorted(nums)


# ---------------------------------------------------------------------------
# Parser loader
# ---------------------------------------------------------------------------
def load_parser(version: str = "v2"):
    """Return (label, parse_fn, pipeline_fn)."""
    if version == "v3":
        from pdf_parser_v3 import parse_shareholders_from_pdf as fn
        from pdf_parser_v3 import _parse_pipeline_v3 as pipeline_fn
        return ("V3", fn, pipeline_fn)
    else:
        from pdf_parser_v2 import parse_shareholders_from_pdf as fn
        from pdf_parser_v2 import _parse_pipeline_v2 as pipeline_fn
        return ("V2", fn, pipeline_fn)


# ---------------------------------------------------------------------------
# Run one parser on one file
# ---------------------------------------------------------------------------
def run_one(parser_label, parse_fn, pipeline_fn, pdf_path, doc_id, expected, gt_for_classify):
    """Run parser, print results, return (shareholders, passed|failed|None)."""
    print(f"\n  [{parser_label}]")
    try:
        with open(pdf_path, "rb") as f:
            file_bytes = f.read()
        # Use pipeline to get full ParseResult with traces
        from pdf_parser_v2 import ParseResult
        parse_result = pipeline_fn(file_bytes)
        shareholders = parse_result.shareholders
        warning = "; ".join(parse_result.warnings) if parse_result.warnings else None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None, None

    if warning:
        print(f"  {WARN}  {warning}")

    if not shareholders:
        print("  (no shareholders parsed)")
    else:
        print(f"  {'#':<4} {'주주명':<25} {'주식종류':<15} {'주식수':>10}")
        print(f"  {'-'*4} {'-'*25} {'-'*15} {'-'*10}")
        for i, sh in enumerate(shareholders, 1):
            print(f"  {i:<4} {sh.name:<25} {sh.shareType:<15} {sh.shareCount:>10,}")

    # Check against ground truth
    status = None
    if doc_id in expected:
        from parser_eval import _normalize_name_for_eval, _names_match_for_eval
        exp = expected[doc_id]
        actual = [(sh.name, sh.shareType, sh.shareCount) for sh in shareholders]
        # Compare: same length + each row matches (name via _names_match_for_eval)
        rows_match = len(exp) == len(actual) and all(
            _names_match_for_eval(e[0], a[0]) and e[1] == a[1] and e[2] == a[2]
            for e, a in zip(exp, actual)
        )
        if rows_match:
            print(f"  Result: {PASS} ({len(actual)} shareholders match)")
            status = "pass"
        else:
            print(f"  Result: {FAIL}")
            status = "fail"
            missing = set(exp) - set(actual)
            extra = set(actual) - set(exp)
            if missing:
                print("  Missing:")
                for row in sorted(missing):
                    print(f"    - {row[0]} / {row[1]} / {row[2]:,}")
            if extra:
                print("  Extra:")
                for row in sorted(extra):
                    print(f"    + {row[0]} / {row[1]} / {row[2]:,}")

            # Failure classification (if traces available)
            if parse_result.traces and doc_id in gt_for_classify:
                _print_failure_report(parse_result, gt_for_classify[doc_id])

    return shareholders, status


def _print_failure_report(parse_result, gt_entries):
    """Print failure classification report for a failed test."""
    from parser_eval import run_eval_from_result
    report = run_eval_from_result(parse_result, gt_entries)
    print(f"\n  Failure Classification (accuracy: {report['accuracy']:.0%})")
    for ft, count in report["failures"].items():
        if count > 0:
            print(f"    {ft}: {count}")
    for detail in report["details"]:
        if detail["type"] != "correct":
            gt_info = detail.get("ground_truth")
            ex_info = detail.get("extracted")
            gt_str = f"{gt_info['name']}/{gt_info['shareCount']:,}" if gt_info else "-"
            ex_str = f"{ex_info['name']}/{ex_info['shareCount']:,}" if ex_info else "-"
            flags_str = f" [{', '.join(detail['flags'])}]" if detail["flags"] else ""
            print(f"    [{detail['type']}] GT: {gt_str} -> EX: {ex_str} (src={detail['source']}){flags_str}")


# ---------------------------------------------------------------------------
# Write results JSONL
# ---------------------------------------------------------------------------
def write_results(results: dict, label: str = "v2"):
    out_path = os.path.join(RESULTS_DIR, f"result_{label.lower()}.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for doc_id, shareholders in results.items():
            obj = {
                "document_id": doc_id,
                "shareholders": [
                    {
                        "name": sh.name,
                        "share_type": sh.shareType if sh.shareType else None,
                        "share_count": sh.shareCount,
                    }
                    for sh in shareholders
                ],
                "total_shares": sum(sh.shareCount for sh in shareholders),
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    print(f"\n  Wrote {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    test_nums, parser_version = parse_args()
    expected, gt_dicts = load_ground_truth(GROUND_TRUTH_PATH)
    label, parse_fn, pipeline_fn = load_parser(parser_version)

    # Determine which PDF files to run
    if test_nums:
        files = [f"Test{n}.pdf" for n in test_nums]
    else:
        # Auto-detect all TestN.pdf in pdfs/
        all_pdfs = sorted(
            [f for f in os.listdir(PDFS_DIR) if f.startswith("Test") and f.endswith(".pdf")],
            key=lambda f: int(f.replace("Test", "").replace(".pdf", "")),
        )
        files = all_pdfs

    total = passed = failed = 0
    all_results: dict[str, list] = {}

    for fname in files:
        pdf_path = os.path.join(PDFS_DIR, fname)
        if not os.path.exists(pdf_path):
            print(f"\n[{fname}] — file not found, skipping")
            continue

        doc_id = fname.replace(".pdf", "")
        print(f"\n{'='*55}")
        print(f"  {fname}")
        print(f"{'='*55}")

        shareholders, status = run_one(label, parse_fn, pipeline_fn, pdf_path, doc_id, expected, gt_dicts)
        if shareholders is not None:
            all_results[doc_id] = shareholders
        if status == "pass":
            total += 1
            passed += 1
        elif status == "fail":
            total += 1
            failed += 1

    # Summary
    if total > 0:
        print(f"\n{'='*55}")
        print(f"  Summary: {passed}/{total} passed", end="")
        if failed:
            print(f"  ({failed} failed)", end="")
        print()

    # Write results
    if all_results:
        write_results(all_results, label)


if __name__ == "__main__":
    main()
