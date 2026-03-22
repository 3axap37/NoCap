"""
parser_eval.py — 실패 분류 및 eval 실행 함수.

eval 스크립트에서 호출. 파싱 본 로직에서는 사용하지 않음.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from parser_types import RowCandidate


# ---------------------------------------------------------------------------
# 실패 유형 상수
# ---------------------------------------------------------------------------
CORRECT = "correct"
ROW_OMISSION = "row_omission"
ROW_HALLUCINATION = "row_hallucination"
NAME_TRUNCATION = "name_truncation"
NAME_CORRUPTION = "name_corruption"
SHARE_TYPE_MISMATCH = "share_type_mismatch"
SHARE_COUNT_MISMATCH = "share_count_mismatch"

_ALL_FAILURE_TYPES = (
    ROW_OMISSION,
    ROW_HALLUCINATION,
    NAME_TRUNCATION,
    NAME_CORRUPTION,
    SHARE_TYPE_MISMATCH,
    SHARE_COUNT_MISMATCH,
)


def _edit_distance(s1: str, s2: str) -> int:
    """Levenshtein edit distance."""
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _normalize_name_for_eval(name: str) -> str:
    """eval 비교용 이름 정규화. 파서 출력은 변경하지 않는다."""
    n = name

    # 연속 공백 → 단일 공백
    n = re.sub(r'\s+', ' ', n).strip()

    # 법인 표기 통일: ㈜, (주), 주식회사 → 정규형
    n = n.replace("㈜", "(주)")
    n = re.sub(r'주식회사\s*', '(주)', n)

    # "투자 조합" ↔ "투자조합" 등 조합/펀드 내 공백 제거
    _COMPOUND_TOKENS = [
        "투자조합", "개인투자조합", "산학협력단", "투자펀드",
        "창업초기", "벤처투자", "기술지주",
    ]
    for token in _COMPOUND_TOKENS:
        spaced_pattern = r'\s*'.join(re.escape(c) for c in token)
        n = re.sub(spaced_pattern, token, n)

    # 괄호 앞뒤 공백 정리
    n = re.sub(r'\s*\(\s*', '(', n)
    n = re.sub(r'\s*\)\s*', ')', n)

    return n.strip()


_PAREN_REMOVE_KWS_EVAL = frozenset({
    "업무집행조합원", "주식회사", "유한회사", "유한책임회사",
    "재단법인", "사단법인", "창조경제혁신센터", "혁신센터",
    "자기주식",
})


def _strip_org_paren_for_eval(name: str) -> str:
    """eval 비교 시 괄호 내 업무집행조합원/법인 부가정보를 무시."""
    while True:
        m = re.search(r'\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$', name)
        if not m:
            break
        content = m.group(1)
        if any(kw in content for kw in _PAREN_REMOVE_KWS_EVAL):
            name = name[:m.start()].rstrip()
        else:
            break
    return name


def _names_match_for_eval(gt_name: str, ex_name: str) -> bool:
    """eval용 이름 비교. 단계적으로 관대하게 비교한다."""
    # 1차: 기존 normalization 후 exact match
    gt_norm = _normalize_name_for_eval(gt_name)
    ex_norm = _normalize_name_for_eval(ex_name)
    if gt_norm == ex_norm:
        return True

    # 2차: 공백 전부 제거 후 비교
    gt_nospace = gt_norm.replace(" ", "")
    ex_nospace = ex_norm.replace(" ", "")
    if gt_nospace == ex_nospace:
        return True

    # 3차: 공백 제거 후 edit distance 1 이하 허용
    if _edit_distance(gt_nospace, ex_nospace) <= 1:
        return True

    # 4차: 괄호 내 업무집행조합원/법인 부가정보 제거 후 비교
    # GT와 파서 간 "(업무집행조합원 ...)" 포함 여부 불일치 허용
    # 정규화 전 원본에서 strip → 다시 정규화 (주식회사→(주) 치환 전에 처리)
    gt_stripped = _normalize_name_for_eval(_strip_org_paren_for_eval(gt_name)).replace(" ", "")
    ex_stripped = _normalize_name_for_eval(_strip_org_paren_for_eval(ex_name)).replace(" ", "")
    if gt_stripped == ex_stripped:
        return True
    if _edit_distance(gt_stripped, ex_stripped) <= 1:
        return True

    return False


def _gt_to_dict(gt: dict) -> dict:
    """Normalize ground truth entry to {name, shareType, shareCount}."""
    return {
        "name": gt.get("name", ""),
        "shareType": gt.get("shareType") or gt.get("share_type") or "",
        "shareCount": gt.get("shareCount") or gt.get("share_count") or 0,
    }


def _rc_to_dict(rc: RowCandidate) -> dict:
    """Convert RowCandidate to comparable dict."""
    return {
        "name": rc.name,
        "shareType": rc.share_type,
        "shareCount": rc.share_count or 0,
    }


# ---------------------------------------------------------------------------
# classify_failures
# ---------------------------------------------------------------------------


def classify_failures(
    final_rows: list[RowCandidate],
    ground_truth: list[dict],
    page_num: int = 0,
) -> list[dict]:
    """
    final_rows와 ground_truth를 매칭하여 실패 유형을 분류.

    매칭 로직:
      1. shareCount exact match로 1:1 매칭 (unique한 경우)
      2. 매칭 안 된 나머지는 순서(row_index) proximity로 매칭
      3. 그래도 매칭 안 된 것은 unmatched

    Returns: list of failure/correct report dicts.
    """
    gt_entries = [_gt_to_dict(g) for g in ground_truth]
    rc_entries = list(final_rows)

    # Build maps: shareCount → indices (for uniqueness check)
    gt_by_sc: dict[int, list[int]] = {}
    for i, g in enumerate(gt_entries):
        gt_by_sc.setdefault(g["shareCount"], []).append(i)

    rc_by_sc: dict[int, list[int]] = {}
    for i, rc in enumerate(rc_entries):
        sc = rc.share_count or 0
        rc_by_sc.setdefault(sc, []).append(i)

    matched_gt: set[int] = set()
    matched_rc: set[int] = set()
    pairs: list[tuple[int, int]] = []  # (gt_idx, rc_idx)

    # Pass 1: exact shareCount match (only when count is unique on both sides)
    for sc, gt_idxs in gt_by_sc.items():
        if sc <= 0:
            continue
        rc_idxs = rc_by_sc.get(sc, [])
        if len(gt_idxs) == 1 and len(rc_idxs) == 1:
            gi, ri = gt_idxs[0], rc_idxs[0]
            if gi not in matched_gt and ri not in matched_rc:
                pairs.append((gi, ri))
                matched_gt.add(gi)
                matched_rc.add(ri)

    # Pass 2: for remaining, match by order proximity
    unmatched_gt = [i for i in range(len(gt_entries)) if i not in matched_gt]
    unmatched_rc = [i for i in range(len(rc_entries)) if i not in matched_rc]

    # Greedy matching: for each unmatched GT (in order), find closest unmatched RC
    remaining_rc = set(unmatched_rc)
    for gi in unmatched_gt:
        if not remaining_rc:
            break
        # Find the RC with the closest index
        best_ri = min(remaining_rc, key=lambda ri: abs(ri - gi))
        pairs.append((gi, best_ri))
        matched_gt.add(gi)
        matched_rc.add(best_ri)
        remaining_rc.discard(best_ri)

    # Build results
    results: list[dict] = []

    for gi, ri in pairs:
        gt = gt_entries[gi]
        rc = rc_entries[ri]
        extracted = _rc_to_dict(rc)

        failure_type = _classify_pair(gt, extracted)

        results.append({
            "type": failure_type,
            "ground_truth": gt,
            "extracted": extracted,
            "source": rc.source,
            "flags": rc.flags,
            "page_num": page_num,
        })

    # Unmatched GT → row_omission
    for gi in range(len(gt_entries)):
        if gi not in matched_gt:
            results.append({
                "type": ROW_OMISSION,
                "ground_truth": gt_entries[gi],
                "extracted": None,
                "source": None,
                "flags": [],
                "page_num": page_num,
            })

    # Unmatched RC → row_hallucination
    for ri in remaining_rc:
        rc = rc_entries[ri]
        results.append({
            "type": ROW_HALLUCINATION,
            "ground_truth": None,
            "extracted": _rc_to_dict(rc),
            "source": rc.source,
            "flags": rc.flags,
            "page_num": page_num,
        })

    return results


def _classify_pair(gt: dict, extracted: dict) -> str:
    """Classify the failure type for a matched (gt, extracted) pair."""
    gt_name_norm = _normalize_name_for_eval(gt["name"])
    ex_name_norm = _normalize_name_for_eval(extracted["name"])
    name_match = _names_match_for_eval(gt["name"], extracted["name"])
    st_match = (gt["shareType"] or "") == (extracted["shareType"] or "")
    sc_match = gt["shareCount"] == extracted["shareCount"]

    if name_match and st_match and sc_match:
        return CORRECT

    # Name checks (prioritize name issues)
    if not name_match:
        # Truncation: GT normalized name starts with extracted normalized name
        if gt_name_norm and ex_name_norm and gt_name_norm.startswith(ex_name_norm) and len(ex_name_norm) < len(gt_name_norm):
            return NAME_TRUNCATION

        # Reverse: extracted starts with GT
        if gt_name_norm and ex_name_norm and ex_name_norm.startswith(gt_name_norm) and len(gt_name_norm) < len(ex_name_norm):
            return NAME_CORRUPTION

        return NAME_CORRUPTION

    if not st_match:
        return SHARE_TYPE_MISMATCH

    if not sc_match:
        return SHARE_COUNT_MISMATCH

    return CORRECT


# ---------------------------------------------------------------------------
# run_eval
# ---------------------------------------------------------------------------


def run_eval(pdf_path: str, ground_truth_path: str) -> dict:
    """
    1. PDF 파싱 → ParseResult (traces 포함)
    2. ground truth 로드
    3. 페이지별 classify_failures 호출
    4. 요약 통계 반환
    """
    from pdf_parser_v2 import parse_shareholders_from_pdf, _parse_pipeline_v2

    # Parse
    with open(pdf_path, "rb") as f:
        file_bytes = f.read()

    result = _parse_pipeline_v2(file_bytes)

    # Load ground truth
    with open(ground_truth_path, encoding="utf-8") as f:
        gt_data = json.load(f) if ground_truth_path.endswith(".json") else None

    if gt_data is None:
        # Try JSONL — find matching document
        import os
        doc_id = os.path.splitext(os.path.basename(pdf_path))[0]
        gt_entries = []
        with open(ground_truth_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj.get("document_id") == doc_id:
                    gt_entries = obj.get("shareholders", [])
                    break
    else:
        gt_entries = gt_data.get("shareholders", [])

    # Collect all final rows from traces
    all_final_rows: list[RowCandidate] = []
    for trace in result.traces:
        all_final_rows.extend(trace.final_rows)

    # Classify failures
    details = classify_failures(all_final_rows, gt_entries, page_num=0)

    # Summary
    total_gt = len(gt_entries)
    total_extracted = len(all_final_rows)
    correct = sum(1 for d in details if d["type"] == CORRECT)
    failure_counts = {ft: 0 for ft in _ALL_FAILURE_TYPES}
    for d in details:
        if d["type"] in failure_counts:
            failure_counts[d["type"]] += 1

    return {
        "total_gt_rows": total_gt,
        "total_extracted_rows": total_extracted,
        "correct": correct,
        "failures": failure_counts,
        "accuracy": correct / total_gt if total_gt > 0 else 0.0,
        "details": details,
    }


def run_eval_from_result(
    result,  # ParseResult
    ground_truth: list[dict],
) -> dict:
    """
    ParseResult와 ground truth list를 직접 받아 eval 수행.
    run_eval.py에서 사용하기 편한 인터페이스.
    """
    all_final_rows: list[RowCandidate] = []
    for trace in result.traces:
        all_final_rows.extend(trace.final_rows)

    details = classify_failures(all_final_rows, ground_truth, page_num=0)

    total_gt = len(ground_truth)
    correct = sum(1 for d in details if d["type"] == CORRECT)
    failure_counts = {ft: 0 for ft in _ALL_FAILURE_TYPES}
    for d in details:
        if d["type"] in failure_counts:
            failure_counts[d["type"]] += 1

    return {
        "total_gt_rows": total_gt,
        "total_extracted_rows": len(all_final_rows),
        "correct": correct,
        "failures": failure_counts,
        "accuracy": correct / total_gt if total_gt > 0 else 0.0,
        "details": details,
    }
