"""Generate full analysis report for all tests."""
import json, os, sys, re
from collections import defaultdict

EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(os.path.dirname(EVAL_DIR), "backend")
sys.path.insert(0, BACKEND_DIR)
os.chdir(BACKEND_DIR)
from dotenv import load_dotenv
load_dotenv(encoding="utf-8-sig")
from parser_eval import _names_match_for_eval

GT_PATH = os.path.join(EVAL_DIR, "ground_truth.jsonl")
RESULTS_PATH = os.path.join(EVAL_DIR, "results", "result_v2.jsonl")

gt_map = {}
with open(GT_PATH, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        gt_map[obj["document_id"]] = obj["shareholders"]

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


def classify_errors(gt_list, ex_list):
    """Classify errors between GT and parser result."""
    gt = [norm(s) for s in gt_list]
    ex = [norm(s) for s in ex_list]

    # Check PASS
    if len(gt) == len(ex) and all(
        _names_match_for_eval(g["name"], e["name"])
        and g["shareType"] == e["shareType"]
        and g["shareCount"] == e["shareCount"]
        for g, e in zip(gt, ex)
    ):
        return "PASS", [], [], len(gt)

    gt_used = [False] * len(gt)
    ex_used = [False] * len(ex)
    matches = []  # (gi, ei, "exact")
    errors = []

    # Pass 1: exact match
    for gi, g in enumerate(gt):
        if gt_used[gi]:
            continue
        for ei, e in enumerate(ex):
            if ex_used[ei]:
                continue
            gn = g["name"].replace(" ", "")
            en = e["name"].replace(" ", "")
            if gn == en and g["shareType"] == e["shareType"] and g["shareCount"] == e["shareCount"]:
                matches.append((gi, ei))
                gt_used[gi] = True
                ex_used[ei] = True
                break

    # Pass 2: fuzzy name match
    for gi, g in enumerate(gt):
        if gt_used[gi]:
            continue
        for ei, e in enumerate(ex):
            if ex_used[ei]:
                continue
            if (
                _names_match_for_eval(g["name"], e["name"])
                and g["shareType"] == e["shareType"]
                and g["shareCount"] == e["shareCount"]
            ):
                matches.append((gi, ei))
                gt_used[gi] = True
                ex_used[ei] = True
                break

    # Pass 3: same count, classify differences
    for gi, g in enumerate(gt):
        if gt_used[gi]:
            continue
        for ei, e in enumerate(ex):
            if ex_used[ei]:
                continue
            if g["shareCount"] == e["shareCount"]:
                # Matched by count — classify what differs
                if g["name"].replace(" ", "") != e["name"].replace(" ", "") and not _names_match_for_eval(g["name"], e["name"]):
                    gn_ns = g["name"].replace(" ", "")
                    en_ns = e["name"].replace(" ", "")
                    if gn_ns in en_ns or en_ns in gn_ns:
                        if len(gn_ns) > len(en_ns):
                            errors.append(("name_truncation", g, e))
                        else:
                            errors.append(("name_corruption", g, e))
                    else:
                        errors.append(("name_corruption", g, e))
                if g["shareType"] != e["shareType"]:
                    errors.append(("share_type_mismatch", g, e))
                gt_used[gi] = True
                ex_used[ei] = True
                break

    # Pass 4: different count, same name
    for gi, g in enumerate(gt):
        if gt_used[gi]:
            continue
        for ei, e in enumerate(ex):
            if ex_used[ei]:
                continue
            if _names_match_for_eval(g["name"], e["name"]) or g["name"].replace(" ", "") == e["name"].replace(" ", ""):
                errors.append(("share_count_mismatch", g, e))
                if g["shareType"] != e["shareType"]:
                    errors.append(("share_type_mismatch", g, e))
                gt_used[gi] = True
                ex_used[ei] = True
                break

    # Remaining unmatched
    for gi, used in enumerate(gt_used):
        if not used:
            errors.append(("row_omission", gt[gi], None))
    for ei, used in enumerate(ex_used):
        if not used:
            errors.append(("row_hallucination", None, ex[ei]))

    n_correct = len(matches)
    return "FAIL", errors, matches, n_correct


# Collect all results
all_tests = sorted(set(list(gt_map.keys()) + list(parser_map.keys())),
                   key=lambda x: int(re.search(r'\d+', x).group()))

pass_tests = []
fail_tests = []
error_counts = defaultdict(int)
error_by_test = defaultdict(list)
error_detail_by_test = {}

for doc_id in all_tests:
    if doc_id not in gt_map:
        continue
    gt_list = gt_map[doc_id]
    ex_list = parser_map.get(doc_id, [])

    status, errors, matches, n_correct = classify_errors(gt_list, ex_list)
    n_gt = len([norm(s) for s in gt_list])
    acc = n_correct / max(n_gt, 1)

    if status == "PASS":
        pass_tests.append(doc_id)
    else:
        fail_tests.append(doc_id)
        error_detail_by_test[doc_id] = {
            "errors": errors,
            "n_correct": n_correct,
            "n_gt": n_gt,
            "accuracy": acc,
            "gt": [norm(s) for s in gt_list],
            "ex": [norm(s) for s in ex_list],
        }
        for err_type, g, e in errors:
            error_counts[err_type] += 1
            error_by_test[err_type].append(doc_id)

# Generate report
L = []
L.append("# Parser V2 전체 분석 리포트")
L.append("")
total = len(pass_tests) + len(fail_tests)
L.append("## 1. 전체 요약")
L.append(f"- 전체: {total}건")
L.append(f"- PASS: {len(pass_tests)}건 ({len(pass_tests)/total:.0%})")
L.append(f"- FAIL: {len(fail_tests)}건")
L.append(f"- PASS 테스트: {', '.join(pass_tests)}")
L.append(f"- FAIL 테스트: {', '.join(fail_tests)}")
L.append("")

L.append("## 2. 에러 유형별 집계")
L.append("")
L.append("| 에러 유형 | 발생 건수 | 영향 테스트 수 | 영향 테스트 | 해결 가능성 |")
L.append("|----------|----------|-------------|-----------|-----------|")

feasibility = {
    "name_corruption": "medium",
    "name_truncation": "medium",
    "share_type_mismatch": "high",
    "share_count_mismatch": "high",
    "row_omission": "low",
    "row_hallucination": "high",
}
for err_type in ["name_corruption", "name_truncation", "share_type_mismatch",
                 "share_count_mismatch", "row_omission", "row_hallucination"]:
    count = error_counts.get(err_type, 0)
    tests = sorted(set(error_by_test.get(err_type, [])), key=lambda x: int(re.search(r'\d+', x).group()))
    feas = feasibility.get(err_type, "?")
    L.append(f"| {err_type} | {count}건 | {len(tests)}개 | {', '.join(tests)} | {feas} |")

L.append("")
L.append("## 3. FAIL 케이스 상세")
L.append("")

for doc_id in fail_tests:
    d = error_detail_by_test[doc_id]
    acc = d["accuracy"]
    L.append(f"### {doc_id} — FAIL (accuracy: {acc:.0%})")
    L.append("")

    # Group errors by type
    err_by_type = defaultdict(list)
    for err_type, g, e in d["errors"]:
        err_by_type[err_type].append((g, e))

    L.append(f"- 에러 유형: {', '.join(err_by_type.keys())}")
    L.append("- 상세:")

    for err_type, pairs in err_by_type.items():
        for g, e in pairs:
            g_str = f"{g['name']} / {g['shareType'] or '(null)'} / {fmt(g['shareCount'])}" if g else "(없음)"
            e_str = f"{e['name']} / {e['shareType'] or '(null)'} / {fmt(e['shareCount'])}" if e else "(없음)"
            L.append(f"  - [{err_type}] GT: {g_str} → 파서: {e_str}")

    # Cause analysis
    types = list(err_by_type.keys())
    if "share_count_mismatch" in types and len(err_by_type["share_count_mismatch"]) >= 3:
        # Check if all counts are multiplied
        ratios = []
        for g, e in err_by_type["share_count_mismatch"]:
            if g and e and g["shareCount"] > 0:
                ratios.append(e["shareCount"] / g["shareCount"])
        if ratios and all(abs(r - ratios[0]) < 0.01 for r in ratios):
            L.append(f"- 원인 분석: VLM이 금액 컬럼을 주식수로 오독 (일괄 {ratios[0]:.0f}배). 액면가 보정 로직 미적용 케이스")
            L.append("- 수정 가능성: **high** — 액면가 감지 로직 개선")
        else:
            L.append("- 원인 분석: 주식수 컬럼 오독 (비균일 배율)")
            L.append("- 수정 가능성: medium")
    elif "row_hallucination" in types and len(err_by_type["row_hallucination"]) >= 3:
        L.append("- 원인 분석: 다중 페이지 PDF에서 VLM/OCR이 비주주 행(서식, 헤더, 주소 등)을 주주로 오인")
        L.append("- 수정 가능성: **medium** — OCR fallback 가드레일 강화")
    elif "name_corruption" in types:
        nc = err_by_type["name_corruption"]
        # Check if it's parenthetical suffix issue
        paren_count = sum(1 for g, e in nc if e and "(" in e["name"] and (not g or "(" not in g["name"]))
        if paren_count >= len(nc) * 0.5:
            L.append("- 원인 분석: VLM이 업무집행조합원 정보를 괄호로 이름에 포함. GT는 제외")
            L.append("- 수정 가능성: **high** — 괄호 내 업무집행조합원 정보 제거 후처리")
        elif len(nc) >= 5:
            L.append("- 원인 분석: VLM이 표 구조를 오독하여 이름-주식수 매핑이 대량으로 꼬임")
            L.append("- 수정 가능성: **low** — VLM 표 구조 인식 한계")
        else:
            L.append("- 원인 분석: VLM 한글 오독 또는 OCR 이름 오류")
            L.append("- 수정 가능성: medium — OCR-VLM 이름 교차 검증 가능성")
    elif "share_type_mismatch" in types:
        L.append("- 원인 분석: 주식종류 컬럼 인식 실패 또는 정규화 미비")
        L.append("- 수정 가능성: high — _normalize_share_type() 확장")
    elif "row_omission" in types:
        L.append("- 원인 분석: VLM이 표의 일부 주주를 누락")
        L.append("- 수정 가능성: low — VLM 근본 한계")
    else:
        L.append("- 원인 분석: 복합 에러")
        L.append("- 수정 가능성: medium")
    L.append("")

# Priority analysis
L.append("## 4. 개선 우선순위 제안")
L.append("")

# Analyze patterns
paren_tests = []
count_mismatch_tests = []
halluc_tests = []
simple_name_tests = []

for doc_id in fail_tests:
    d = error_detail_by_test[doc_id]
    err_types = defaultdict(list)
    for et, g, e in d["errors"]:
        err_types[et].append((g, e))

    # Parenthetical name issue
    if "name_corruption" in err_types:
        nc = err_types["name_corruption"]
        paren = sum(1 for g, e in nc if e and "(" in e["name"] and g and "(" not in g["name"])
        if paren >= len(nc) * 0.5 and paren >= 2:
            paren_tests.append(doc_id)

    # Count mismatch (multiplicative)
    if "share_count_mismatch" in err_types and len(err_types["share_count_mismatch"]) >= 3:
        count_mismatch_tests.append(doc_id)

    # Hallucination heavy
    if "row_hallucination" in err_types and len(err_types["row_hallucination"]) >= 3:
        halluc_tests.append(doc_id)

    # Simple name issues (1-2 errors)
    total_errs = len(d["errors"])
    if total_errs <= 2 and "name_corruption" in err_types:
        simple_name_tests.append(doc_id)

pri = 1
if paren_tests:
    L.append(f"### Priority {pri}: 괄호 내 업무집행조합원 정보 제거")
    L.append(f"- 대상: {', '.join(paren_tests)}")
    L.append(f"- 예상 효과: +{len(paren_tests)} PASS")
    L.append("- 구현 난이도: low")
    L.append("- 접근 방법: `_clean_name()`에 `(업무집행조합원 ...)` 패턴 제거 추가. 펀드명 뒤의 `(조합원명 사업자번호)` 형태를 정규식으로 제거.")
    L.append("")
    pri += 1

if count_mismatch_tests:
    L.append(f"### Priority {pri}: 액면가 보정 로직 확장")
    L.append(f"- 대상: {', '.join(count_mismatch_tests)}")
    L.append(f"- 예상 효과: +{len(count_mismatch_tests)} PASS")
    L.append("- 구현 난이도: medium")
    L.append("- 접근 방법: `_detect_face_value()` 감지 조건 확장. 현재 OCR 기반 감지가 작동하지 않는 케이스 분석 필요.")
    L.append("")
    pri += 1

if halluc_tests:
    L.append(f"### Priority {pri}: OCR fallback/VLM hallucination 가드레일 강화")
    L.append(f"- 대상: {', '.join(halluc_tests)}")
    L.append(f"- 예상 효과: +{len(halluc_tests)} PASS (hallucination 제거 시)")
    L.append("- 구현 난이도: medium")
    L.append("- 접근 방법: `_is_valid_fallback_row()` 필터 강화, `_post_validate()` 서식/헤더 행 감지 추가")
    L.append("")
    pri += 1

if simple_name_tests:
    L.append(f"### Priority {pri}: 소규모 이름 오독 (1-2건 에러)")
    L.append(f"- 대상: {', '.join(simple_name_tests)}")
    L.append(f"- 예상 효과: +{len(simple_name_tests)} PASS (개별 수정 가능 시)")
    L.append("- 구현 난이도: medium~high")
    L.append("- 접근 방법: OCR-VLM 이름 교차 검증, V3 앙상블 조건 확장")
    L.append("")
    pri += 1

L.append(f"### Priority {pri}: 복잡한 표 구조 / VLM 근본 한계")
hard_tests = [t for t in fail_tests if t not in paren_tests + count_mismatch_tests + halluc_tests + simple_name_tests]
L.append(f"- 대상: {', '.join(hard_tests) if hard_tests else '(위 Priority에 포함되지 않은 나머지)'}")
L.append("- 예상 효과: 불확실")
L.append("- 구현 난이도: high")
L.append("- 접근 방법: VLM 프롬프트 대폭 수정, 표 영역 사전 분할, 또는 다중 VLM 호출 앙상블")
L.append("")

L.append("## 5. 해결 불가 케이스")
L.append("")
for doc_id in fail_tests:
    d = error_detail_by_test[doc_id]
    err_types = [et for et, _, _ in d["errors"]]
    if d["accuracy"] == 0 or (len(d["errors"]) >= 10 and "name_corruption" in err_types):
        L.append(f"- **{doc_id}** (accuracy {d['accuracy']:.0%}): ", )
        if d["accuracy"] == 0:
            L.append(f"  VLM이 표 전체를 오독. 현재 아키텍처로는 해결 어려움.")
        else:
            L.append(f"  대량 name_corruption ({len(d['errors'])}건). VLM 표 구조 인식 근본 한계.")
        L.append("")

report = "\n".join(L)
out_path = os.path.join(EVAL_DIR, "full_analysis_report.md")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(report)
print(f"Report saved: {out_path}")
print(f"PASS={len(pass_tests)}/{total}, FAIL={len(fail_tests)}")
print(f"Error counts: {dict(error_counts)}")
