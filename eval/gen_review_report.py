"""Generate GT review report for Test37~Test59."""
import json, os, sys

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(os.path.dirname(EVAL_DIR), "backend")
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)
from dotenv import load_dotenv
load_dotenv(encoding="utf-8-sig")

from parser_eval import _names_match_for_eval

GT_PATH = os.path.join(EVAL_DIR, "ground_truth.jsonl")
RESULTS_PATH = os.path.join(EVAL_DIR, "results", "result_v2.jsonl")

# Load GT
gt_map = {}
with open(GT_PATH, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        gt_map[obj["document_id"]] = obj["shareholders"]

# Load parser results
parser_map = {}
with open(RESULTS_PATH, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        parser_map[obj["document_id"]] = obj["shareholders"]


def fmt(n):
    return f"{n:,}"


def norm(sh):
    return {
        "name": sh.get("name", ""),
        "shareType": sh.get("share_type") or sh.get("shareType") or "",
        "shareCount": sh.get("share_count") or sh.get("shareCount") or 0,
    }


def match_rows(gt_list, ex_list):
    gt_used = [False] * len(gt_list)
    ex_used = [False] * len(ex_list)
    matches = []

    # Pass 1: exact (nospace name + type + count)
    for gi, g in enumerate(gt_list):
        if gt_used[gi]:
            continue
        gn = g["name"].replace(" ", "")
        for ei, e in enumerate(ex_list):
            if ex_used[ei]:
                continue
            en = e["name"].replace(" ", "")
            if gn == en and g["shareType"] == e["shareType"] and g["shareCount"] == e["shareCount"]:
                matches.append((gi, ei, "exact"))
                gt_used[gi] = True
                ex_used[ei] = True
                break

    # Pass 2: fuzzy name + type + count
    for gi, g in enumerate(gt_list):
        if gt_used[gi]:
            continue
        for ei, e in enumerate(ex_list):
            if ex_used[ei]:
                continue
            if (
                _names_match_for_eval(g["name"], e["name"])
                and g["shareType"] == e["shareType"]
                and g["shareCount"] == e["shareCount"]
            ):
                matches.append((gi, ei, "exact"))
                gt_used[gi] = True
                ex_used[ei] = True
                break

    # Pass 3: same count, match name loosely
    for gi, g in enumerate(gt_list):
        if gt_used[gi]:
            continue
        for ei, e in enumerate(ex_list):
            if ex_used[ei]:
                continue
            if g["shareCount"] == e["shareCount"]:
                matches.append((gi, ei, "count_match"))
                gt_used[gi] = True
                ex_used[ei] = True
                break

    return matches, gt_used, ex_used


lines = ["# Ground Truth 검수 리포트", ""]

total = pass_count = fail_count = total_disc = 0

for test_num in range(37, 60):
    doc_id = f"Test{test_num}"
    total += 1

    if doc_id not in gt_map:
        lines.append(f"## {doc_id} — SKIP (GT 없음)")
        lines.append("")
        continue

    gt_norm = [norm(s) for s in gt_map[doc_id]]
    ex_norm = [norm(s) for s in parser_map.get(doc_id, [])]

    # Check PASS using eval logic
    exp = [(s["name"], s["shareType"], s["shareCount"]) for s in gt_norm]
    act = [(s["name"], s["shareType"], s["shareCount"]) for s in ex_norm]
    rows_match = len(exp) == len(act) and all(
        _names_match_for_eval(e[0], a[0]) and e[1] == a[1] and e[2] == a[2]
        for e, a in zip(exp, act)
    )

    if rows_match:
        pass_count += 1
        lines.append(f"## {doc_id} — PASS")
        lines.append("일치 확인됨")
        lines.append("")
        continue

    fail_count += 1
    matches, gt_used, ex_used = match_rows(gt_norm, ex_norm)

    discrepancies = []
    matched_items = []

    for gi, ei, mtype in matches:
        g, e = gt_norm[gi], ex_norm[ei]
        if mtype == "exact":
            matched_items.append(
                f"- {g['name']} / {g['shareType'] or '(null)'} / {fmt(g['shareCount'])} ✓"
            )
        elif mtype == "count_match":
            gn_ns = g["name"].replace(" ", "")
            en_ns = e["name"].replace(" ", "")
            if gn_ns != en_ns:
                discrepancies.append(
                    {
                        "type": "name_diff",
                        "gt": f"{g['name']} / {g['shareType'] or '(null)'} / {fmt(g['shareCount'])}",
                        "ex": f"{e['name']} / {e['shareType'] or '(null)'} / {fmt(e['shareCount'])}",
                    }
                )
            if g["shareType"] != e["shareType"]:
                discrepancies.append(
                    {
                        "type": "type_diff",
                        "gt": f"{g['name']} / **{g['shareType'] or '(null)'}** / {fmt(g['shareCount'])}",
                        "ex": f"{e['name']} / **{e['shareType'] or '(null)'}** / {fmt(e['shareCount'])}",
                    }
                )

    # Unmatched GT = missing
    for gi, used in enumerate(gt_used):
        if not used:
            g = gt_norm[gi]
            discrepancies.append(
                {
                    "type": "missing",
                    "gt": f"{g['name']} / {g['shareType'] or '(null)'} / {fmt(g['shareCount'])}",
                    "ex": "(없음)",
                }
            )

    # Unmatched EX = extra
    for ei, used in enumerate(ex_used):
        if not used:
            e = ex_norm[ei]
            discrepancies.append(
                {
                    "type": "extra",
                    "gt": "(없음)",
                    "ex": f"{e['name']} / {e['shareType'] or '(null)'} / {fmt(e['shareCount'])}",
                }
            )

    total_disc += len(discrepancies)
    n_correct = sum(1 for m in matches if m[2] == "exact")
    acc = n_correct / max(len(gt_norm), 1)

    lines.append(f"## {doc_id} — FAIL (accuracy: {acc:.0%})")
    lines.append("")
    lines.append("### 불일치 항목")
    lines.append("")
    lines.append("| # | 유형 | Ground Truth | 파서 결과 | 판정 |")
    lines.append("|---|------|-------------|----------|------|")
    for i, d in enumerate(discrepancies, 1):
        if d["type"] == "missing":
            verdict = "[ ] GT맞음 [ ] GT수정"
        elif d["type"] == "extra":
            verdict = "[ ] 파서맞음 [ ] 파서오류"
        elif d["type"] == "name_diff":
            verdict = "[ ] GT맞음 [ ] 파서맞음"
        elif d["type"] == "type_diff":
            verdict = "[ ] GT맞음 [ ] 파서맞음"
        elif d["type"] == "count_diff":
            verdict = "[ ] GT맞음 [ ] 파서맞음"
        else:
            verdict = "[ ] 확인필요"
        lines.append(f"| {i} | {d['type']} | {d['gt']} | {d['ex']} | {verdict} |")

    lines.append("")
    lines.append("### 일치 항목 (참고용)")
    if matched_items:
        for item in matched_items:
            lines.append(item)
    else:
        lines.append("(일치 항목 없음)")
    lines.append("")

lines.append("---")
lines.append("")
lines.append("## 요약")
lines.append(f"- 전체: {total}건 (Test37~Test59)")
lines.append(f"- PASS: {pass_count}건 (검수 불필요)")
lines.append(f"- FAIL: {fail_count}건 (검수 필요)")
lines.append(f"- 총 불일치 항목: {total_disc}건")

report = "\n".join(lines)
out_path = os.path.join(EVAL_DIR, "gt_review_report.md")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(report)
print(f"Report saved to {out_path}")
print(f"PASS={pass_count}, FAIL={fail_count}, discrepancies={total_disc}")
