"""
pdf_parser_v3.py — Reader-First 3-Pass pipeline.

Pass 1: _read_document()         — LLM reads PDF, outputs semi-structured text
Pass 2-A: _verify_completeness() — Code-based validation
Pass 2-B: _repair_with_pdf()     — Conditional LLM repair (PDF re-sent + draft)
Pass 3: _structure_output()      — Code parser (no LLM), section-state based
→ _post_validate + _validate_direct_result
→ On failure: v2 fallback
"""

import base64
import io
import json
import logging
import os
import re
from enum import Enum
from typing import Optional

from dotenv import load_dotenv

import openai

from models import Shareholder
from parser_types import RowCandidate, PageTrace, V3PageTrace
from pdf_parser_v2 import (
    ParseResult,
    ParseMethod,
    _clean_name,
    _normalize_share_type,
    _is_skip_row,
    _deduplicate,
    _post_validate,
    _parse_pipeline_v2,
    _parse_count,
    _KNOWN_SHARE_TYPES,
)

load_dotenv(encoding="utf-8-sig")

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ---------------------------------------------------------------------------
# READER_PROMPT (Pass 1)
# ---------------------------------------------------------------------------

READER_PROMPT = """\
이 PDF는 주주명부(주주 목록)입니다.
문서를 처음부터 끝까지 꼼꼼히 읽고, 반드시 아래 형식으로만 작성해주세요.
다른 형식이나 설명 없이 아래 형식만 출력하세요.

【이름 규칙 — 반드시 준수】
- 법인명/펀드명/조합명은 아무리 길어도 전체를 그대로 적으세요.
  절대 축약하거나 잘라내지 마세요.
  예) "데일리 골든아워 바이오 헬스케어 펀드3호" → 전체 기입
  예) "크립톤-엔젤링크 7호 개인투자조합" → 전체 기입
  예) "블리스바인 프론티어 투자조합" → 전체 기입
  예) "수이제네리스 글로벌 스케일업 투자조합" → 전체 기입
- 여러 줄로 나뉜 이름은 이어붙여서 적으세요.
- "재단법인", "주식회사", "(주)", "㈜" 등 접두어도 이름의 일부입니다.
- 영문 병기는 괄호 포함 전체를 적으세요. 예) "김혜련(JIN HAILIAN)"
- 이름 뒤 직함/괄호 표기도 보존하세요. 예) "김창규(대표이사)"

【핵심 원칙 — 복사 모드】
- 표의 데이터 행은 해석하거나 요약하지 말고, 보이는 문자열을 그대로 옮겨 적으세요.
- 이름, 주식종류, 주식수는 원문 표기 그대로 유지하세요.
- 긴 법인명/펀드명/조합명을 절대 축약하지 마세요.
- 확실하지 않은 경우 추정하지 말고, 보이는 범위 안에서만 적으세요.
- 다른 행의 값을 섞지 마세요. 각 행은 해당 행의 값만 적으세요.

【행 선별 규칙】
- 표의 모든 데이터 행을 빠짐없이 적으세요. 마지막 행까지 반드시 포함.
- 합계/소계/총계, 서명란, 날짜, 메타 정보 행만 [제외 행]에 넣으세요.
- 확실하지 않으면 데이터 행에 포함하세요 (누락보다 과포함이 낫습니다).
- 표가 90도 또는 270도 회전되어 있을 수 있습니다. 회전된 표도 정상적으로 읽으세요.

【출력 형식 — 반드시 이 형식으로만】

=== 페이지 N ===
[데이터 행]
1. 주주명 / 주식종류 / 주식수
2. 주주명 / 주식종류 / 주식수
...

[제외 행]
- 행 내용 (제외 사유)

규칙:
- 주식종류가 표에 없으면 생략: "1. 주주명 / 주식수"
- 주식종류가 있으면 포함: "1. 주주명 / 보통주 / 주식수"
- 주식수는 쉼표 포함 원문 그대로 적으세요.
- 번호는 1부터 순서대로.
- 데이터 행은 반드시 "번호. " 형태로 시작.
- 제외 행은 반드시 "- " 형태로 시작.
"""


# ---------------------------------------------------------------------------
# API call wrapper (shared by Pass 1 and Pass 2-B)
# ---------------------------------------------------------------------------


def _call_pdf_reader(file_bytes: bytes, prompt: str) -> Optional[str]:
    """Send PDF + text prompt via Responses API and return the text output."""
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set")
        return None

    try:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        b64_pdf = base64.b64encode(file_bytes).decode()

        response = client.responses.create(
            model="gpt-4o",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_file",
                            "filename": "shareholder_registry.pdf",
                            "file_data": f"data:application/pdf;base64,{b64_pdf}",
                        },
                        {
                            "type": "input_text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )
        return response.output_text
    except Exception as e:
        logger.error("PDF reader API call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Pass 1: _read_document
# ---------------------------------------------------------------------------


def _read_document(file_bytes: bytes) -> Optional[str]:
    """Pass 1: Send PDF to LLM, get semi-structured text output."""
    return _call_pdf_reader(file_bytes, READER_PROMPT)


# ---------------------------------------------------------------------------
# Pass 2-A: _verify_completeness (code-based)
# ---------------------------------------------------------------------------


def _count_draft_rows(draft_text: str) -> int:
    """Count numbered data rows in [데이터 행] sections."""
    count = 0
    in_data = False
    for line in draft_text.split("\n"):
        if "[데이터" in line:
            in_data = True
            continue
        if "[제외" in line:
            in_data = False
            continue
        if in_data and re.match(r"^\d+\.\s", line):
            count += 1
    return count


def _sum_draft_counts(draft_text: str) -> int:
    """Sum share counts from [데이터 행] sections."""
    total = 0
    in_data = False
    for line in draft_text.split("\n"):
        if "[데이터" in line:
            in_data = True
            continue
        if "[제외" in line:
            in_data = False
            continue
        if not in_data:
            continue
        row_match = re.match(r"^\d+\.\s*(.+)", line)
        if not row_match:
            continue
        parts = [p.strip() for p in row_match.group(1).split("/")]
        if len(parts) < 2:
            continue
        count_str = parts[-1]
        cleaned = count_str.replace(",", "").replace("주", "").strip()
        if re.match(r"^\d+$", cleaned):
            val = int(cleaned)
            if 1 < val < 10_000_000_000:
                total += val
    return total


def _extract_total_from_text(file_bytes: bytes) -> Optional[int]:
    """Extract the total share count from PDF text (합계/총계 row)."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                if any(kw in line for kw in ("합계", "총계", "소계")):
                    numbers = re.findall(r"\d{1,3}(?:,\d{3})+|\d{4,}", line)
                    for n_str in numbers:
                        n = int(n_str.replace(",", ""))
                        if 100 < n < 10_000_000_000:
                            return n
    except Exception:
        pass
    return None


def _verify_completeness(draft_text: str, file_bytes: bytes) -> dict:
    """Code-based verification of the draft.
    Returns: {"passed": bool, "issues": list[str]}"""
    issues = []

    draft_count = _count_draft_rows(draft_text)
    draft_sum = _sum_draft_counts(draft_text)
    text_total = _extract_total_from_text(file_bytes)

    # 1. No data rows
    if draft_count == 0:
        issues.append("no_data_rows")

    # 2. Sum deficit vs text total
    if text_total and draft_sum < text_total * 0.85:
        issues.append(f"sum_deficit: draft={draft_sum}, expected={text_total}")

    # 3. Name truncation suspects
    in_data = False
    for line in draft_text.split("\n"):
        if "[데이터" in line:
            in_data = True
            continue
        if "[제외" in line:
            in_data = False
            continue
        if not in_data:
            continue
        row_match = re.match(r"^\d+\.\s*(.+)", line)
        if not row_match:
            continue
        parts = [p.strip() for p in row_match.group(1).split("/")]
        name_part = parts[0]
        entity_keywords = ("펀드", "조합", "주식회사", "재단법인", "투자", "산학")
        if any(kw in name_part for kw in entity_keywords) and len(name_part) <= 6:
            issues.append(f"truncation_suspect: {name_part}")

    return {"passed": len(issues) == 0, "issues": issues}


# ---------------------------------------------------------------------------
# Pass 2-B: _repair_with_pdf (conditional LLM, PDF re-sent)
# ---------------------------------------------------------------------------


def _repair_with_pdf(
    draft_text: str,
    file_bytes: bytes,
    issues: list[str],
) -> Optional[str]:
    """Re-send PDF + draft + issues to LLM for grounded repair."""
    issues_text = "\n".join(f"- {issue}" for issue in issues)

    repair_prompt = f"""\
아래는 이 주주명부 PDF에서 추출한 초안입니다.
검증 결과 다음 문제가 발견되었습니다:

{issues_text}

PDF 원문을 다시 확인하고, 초안을 수정해주세요.
특히:
- 누락된 주주가 없는지 (표의 모든 행이 포함되었는지)
- 법인명/펀드명/조합명이 잘리지 않았는지 (전체 이름이 보존되었는지)
- 합계/메타/서명 행이 데이터 행에 섞이지 않았는지

초안과 동일한 형식으로 전체를 다시 작성해주세요.

--- 초안 ---
{draft_text}
"""

    return _call_pdf_reader(file_bytes, repair_prompt)


# ---------------------------------------------------------------------------
# Pass 3: _structure_output (code parser, no LLM)
# ---------------------------------------------------------------------------


class _Section(Enum):
    UNKNOWN = "unknown"
    DATA = "data"
    EXCLUDED = "excluded"


def _structure_output(verified_text: str) -> list[RowCandidate]:
    """Parse verified semi-structured text into RowCandidates.
    Uses section-state tracking. No LLM calls."""
    candidates = []
    current_section = _Section.UNKNOWN
    current_page = 1
    idx = 0

    for line in verified_text.split("\n"):
        line = line.strip()
        if not line:
            continue

        # Page boundary
        page_match = re.match(r"===\s*페이지\s*(\d+)", line)
        if page_match:
            current_page = int(page_match.group(1))
            current_section = _Section.UNKNOWN
            continue

        # Section transitions
        if "[데이터" in line:
            current_section = _Section.DATA
            continue
        if "[제외" in line:
            current_section = _Section.EXCLUDED
            continue

        # Only parse numbered rows in DATA section
        if current_section != _Section.DATA:
            continue

        row_match = re.match(r"^(\d+)\.\s*(.+)", line)
        if not row_match:
            continue

        content = row_match.group(2)
        parts = [p.strip() for p in content.split("/")]
        if len(parts) < 2:
            continue

        # Name: first field
        name = _clean_name(parts[0])
        if not name or _is_skip_row(name):
            continue

        # Share count: last field
        count_str = parts[-1]
        count = _parse_count(count_str)
        if not count or count <= 0:
            continue

        # Share type: middle field (if present)
        share_type = ""
        if len(parts) >= 3:
            raw_type = parts[1]
            normalized = _normalize_share_type(raw_type)
            if normalized in _KNOWN_SHARE_TYPES:
                share_type = normalized

        candidates.append(
            RowCandidate(
                name=name,
                share_type=share_type,
                share_count=count,
                source="direct_pdf",
                row_index=idx,
            )
        )
        idx += 1

    return candidates


# ---------------------------------------------------------------------------
# Count Verifier (draft 기준 교차 검증)
# ---------------------------------------------------------------------------


def _verify_counts(
    candidates: list[RowCandidate],
    verified_text: str,
) -> list[RowCandidate]:
    """Cross-verify shareCount between Pass 3 output and draft text.
    If mismatch detected and draft value is valid, replace with draft value."""

    # Step 1: Extract per-row counts from draft (last / field only)
    draft_counts: dict[int, int] = {}
    in_data = False
    draft_idx = 0
    for line in verified_text.split("\n"):
        if "[데이터" in line:
            in_data = True
            continue
        if "[제외" in line:
            in_data = False
            continue
        if not in_data:
            continue
        row_match = re.match(r"^\d+\.\s*(.+)", line)
        if not row_match:
            continue
        parts = [p.strip() for p in row_match.group(1).split("/")]
        if len(parts) >= 2:
            draft_count = _parse_count(parts[-1])
            if draft_count is not None and 0 < draft_count < 10_000_000_000:
                draft_counts[draft_idx] = draft_count
        draft_idx += 1

    # Step 2: Detect mismatches and conditionally replace
    corrected = []
    for rc in candidates:
        draft_count = draft_counts.get(rc.row_index)

        if draft_count is None or draft_count == rc.share_count:
            corrected.append(rc)
            continue

        # Mismatch detected
        logger.info(
            "Count mismatch: row %d '%s' structured=%d, draft=%d",
            rc.row_index,
            rc.name,
            rc.share_count or 0,
            draft_count,
        )

        if draft_count > 0:
            corrected.append(
                RowCandidate(
                    name=rc.name,
                    share_type=rc.share_type,
                    share_count=draft_count,
                    source=rc.source,
                    row_index=rc.row_index,
                    confidence=rc.confidence,
                    flags=rc.flags + ["count_mismatch_with_draft"],
                    raw_cells=rc.raw_cells,
                )
            )
        else:
            corrected.append(
                RowCandidate(
                    name=rc.name,
                    share_type=rc.share_type,
                    share_count=rc.share_count,
                    source=rc.source,
                    row_index=rc.row_index,
                    confidence=rc.confidence,
                    flags=rc.flags + ["count_mismatch_unresolved"],
                    raw_cells=rc.raw_cells,
                )
            )

    return corrected


# ---------------------------------------------------------------------------
# Validation (reused from previous version)
# ---------------------------------------------------------------------------


def _validate_direct_result(
    candidates: list[RowCandidate],
    file_bytes: bytes,
) -> bool:
    """Check if direct PDF result is trustworthy enough to use."""
    if len(candidates) == 0:
        return False

    for rc in candidates:
        if _is_skip_row(rc.name):
            return False
        if (rc.share_count or 0) >= 10_000_000_000:
            return False

    text_total = _extract_total_from_text(file_bytes)
    if text_total is not None:
        extracted_total = sum(rc.share_count or 0 for rc in candidates)
        if extracted_total < text_total * 0.85:
            logger.info(
                "Direct result incomplete: extracted=%d vs text_total=%d",
                extracted_total,
                text_total,
            )
            return False

    return True


# ---------------------------------------------------------------------------
# v2 fallback helper
# ---------------------------------------------------------------------------


def _fallback_to_v2(
    file_bytes: bytes,
    draft_text: str = "",
    verification: Optional[dict] = None,
    repair_text: Optional[str] = None,
    verified_text: str = "",
) -> ParseResult:
    """Run full v2 pipeline and record v3 trace with route=v2_fallback."""
    logger.info("Falling back to v2 pipeline")
    result = _parse_pipeline_v2(file_bytes)

    v3_trace = V3PageTrace(
        page_num=0,
        draft_text=draft_text,
        validator_issues=verification["issues"] if verification else [],
        repair_text=repair_text,
        verified_text=verified_text,
        structured_rows=[],
        final_rows=[],
        text_total=None,
        route="v2_fallback",
    )
    result.v3_traces.append(v3_trace)

    return result


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def _parse_pipeline_v3(file_bytes: bytes) -> ParseResult:
    result = ParseResult()

    # Pass 1: Read document
    draft_text = _read_document(file_bytes)
    if draft_text is None or not draft_text.strip():
        logger.info("Pass 1 failed, falling back to v2")
        return _fallback_to_v2(file_bytes, draft_text or "")

    logger.info("Pass 1 draft:\n%s", draft_text[:500])

    # Pass 2-A: Code-based verification
    verification = _verify_completeness(draft_text, file_bytes)

    # Pass 2-B: Grounded repair (only when verification fails)
    verified_text = draft_text
    repair_text = None
    if not verification["passed"]:
        logger.info("Verification failed: %s. Attempting repair.", verification["issues"])
        repair_text = _repair_with_pdf(draft_text, file_bytes, verification["issues"])
        if repair_text and repair_text.strip():
            verified_text = repair_text

    # Pass 3: Structure output (code parser, no LLM)
    candidates = _structure_output(verified_text)

    if not candidates:
        logger.info("Pass 3 produced 0 candidates, falling back to v2")
        return _fallback_to_v2(file_bytes, draft_text, verification, repair_text, verified_text)

    # Count verify (draft 기준 교차 검증)
    candidates = _verify_counts(candidates, verified_text)

    # Post-validate
    validated = _post_validate(candidates)
    valid_candidates = validated["shareholders"]

    # Final validation
    if not _validate_direct_result(valid_candidates, file_bytes):
        logger.info("Final validation failed, falling back to v2")
        return _fallback_to_v2(file_bytes, draft_text, verification, repair_text, verified_text)

    # Success
    result.shareholders = _deduplicate(
        [rc.to_shareholder() for rc in valid_candidates]
    )
    result.method = ParseMethod.OCR
    result.warnings.append("PDF 직접 파싱 완료. 결과를 확인해 주세요.")

    # Count pages
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        result.page_count = len(reader.pages)
    except Exception:
        pass

    # V3 Trace
    text_total = _extract_total_from_text(file_bytes)
    v3_trace = V3PageTrace(
        page_num=0,
        draft_text=draft_text,
        validator_issues=verification["issues"],
        repair_text=repair_text,
        verified_text=verified_text,
        structured_rows=candidates,
        final_rows=valid_candidates,
        text_total=text_total,
        route="direct",
    )
    result.v3_traces.append(v3_trace)

    # Also add a PageTrace for eval compatibility
    trace = PageTrace(
        page_num=0,
        ocr_rows=[],
        vlm_rows=candidates,
        vlm_retry_rows=None,
        final_rows=valid_candidates,
        ocr_total=text_total,
    )
    result.traces.append(trace)

    logger.info("v3 reader-first succeeded with %d shareholders", len(result.shareholders))
    return result


# ---------------------------------------------------------------------------
# Public API (same signature as v2)
# ---------------------------------------------------------------------------


def parse_shareholders_from_pdf(
    file_bytes: bytes,
) -> tuple[list[Shareholder], Optional[str]]:
    """v3 entry point. Same signature as v2."""
    result = _parse_pipeline_v3(file_bytes)
    warning = "; ".join(result.warnings) if result.warnings else None
    return result.shareholders, warning
