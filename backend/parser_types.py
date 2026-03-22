"""
parser_types.py — RowCandidate / PageTrace: 파싱 중간 산출물 데이터 클래스.

내부 디버그·eval 전용. 외부 인터페이스(Shareholder, parse_shareholders_from_pdf)에는 영향 없음.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from models import Shareholder


@dataclass
class RowCandidate:
    """OCR과 VLM 양쪽의 행 단위 중간 산출물. 실패 분류의 비교 단위.

    flags 규약:
        address_trimmed    — OCR 이름에서 주소 부분을 잘라냄
        name_incomplete    — OCR 이름이 "..."로 끝남 (부분 감지)
        small_sc_2nd_pass  — 2nd-pass 소액 주식수 감지로 추가됨
        embedded_sc_3rd_pass — 3rd-pass 합성 토큰에서 주식수 추출
        type_ocr_override  — VLM 주식종류를 OCR 값으로 교정함
        retry_added        — VLM 재시도에서 추가됨
        count_only_match   — OCR fallback: shareCount 기준으로만 삽입됨
    """

    name: str
    share_type: str  # 정규화된 주식종류. 없으면 ""
    share_count: Optional[int]
    source: str  # "ocr" | "vlm" | "ocr_fallback" | "vlm_retry"
    row_index: int  # 페이지 내 순서 (0-based)
    confidence: float = 1.0
    flags: list[str] = field(default_factory=list)
    # 원본 셀 데이터 보존 (OCR 행의 경우 [name, share_type?, sc_text])
    raw_cells: list[str] = field(default_factory=list)

    def to_shareholder(self) -> Shareholder:
        """RowCandidate → Shareholder 변환."""
        return Shareholder(
            name=self.name,
            shareType=self.share_type,
            shareCount=self.share_count or 0,
        )


@dataclass
class PageTrace:
    """한 페이지의 파싱 중간 산출물. 디버그/eval 전용."""

    page_num: int
    ocr_rows: list[RowCandidate] = field(default_factory=list)
    vlm_rows: list[RowCandidate] = field(default_factory=list)
    vlm_retry_rows: Optional[list[RowCandidate]] = None  # 재시도 안 했으면 None
    final_rows: list[RowCandidate] = field(default_factory=list)  # 후처리 완료된 최종
    ocr_total: Optional[int] = None  # 합계행에서 추출한 총 주식수
    failure_report: Optional[dict] = None  # eval 시 채움


@dataclass
class V3PageTrace:
    """v3 reader-first 파이프라인의 trace. 디버그/eval 전용."""

    page_num: int  # 0이면 문서 전체
    draft_text: str  # Pass 1 출력 (반구조화 텍스트)
    validator_issues: list[str] = field(default_factory=list)  # Pass 2-A 검증 결과
    repair_text: Optional[str] = None  # Pass 2-B 출력 (repair 안 했으면 None)
    verified_text: str = ""  # Pass 2 최종
    structured_rows: list[RowCandidate] = field(default_factory=list)  # Pass 3 출력
    final_rows: list[RowCandidate] = field(default_factory=list)  # post_validate 후 최종
    text_total: Optional[int] = None  # 텍스트 레이어에서 추출한 합계
    route: str = "direct"  # "direct" | "v2_fallback"
