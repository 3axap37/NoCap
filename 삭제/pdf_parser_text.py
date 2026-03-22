import io
import re
from typing import Optional

import pdfplumber

from models import Shareholder


def parse_shareholders_from_pdf(
    file_bytes: bytes,
) -> tuple[list[Shareholder], Optional[str]]:
    """Parse 주주명부 PDF and extract shareholder information."""
    shareholders, warning = _try_table_extraction(file_bytes)

    if not shareholders:
        shareholders, warning = _parse_text_fallback(file_bytes)

    return shareholders, warning


# ---------------------------------------------------------------------------
# Table-based extraction
# ---------------------------------------------------------------------------

_NAME_KEYWORDS = ("주주명", "성명", "주주")
_TYPE_KEYWORDS = ("주식종류", "종류", "주식 종류")
_COUNT_KEYWORDS = ("주식수", "주식 수", "수량", "발행주식수", "발행 주식수")
_SKIP_ROWS = {"소계", "합계", "총계", "계"}


def _match_header(headers: list[str], keywords: tuple) -> Optional[int]:
    for kw in keywords:
        for i, h in enumerate(headers):
            if kw in h:
                return i
    return None


def _parse_count(raw: str) -> Optional[int]:
    cleaned = re.sub(r"[^\d]", "", raw)
    if not cleaned:
        return None
    v = int(cleaned)
    return v if v > 0 else None


def _try_table_extraction(
    file_bytes: bytes,
) -> tuple[list[Shareholder], Optional[str]]:
    shareholders: list[Shareholder] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Find the header row (row containing shareholder name column)
                header_row_idx = None
                for i, row in enumerate(table):
                    if row and any(
                        any(kw in str(cell) for kw in _NAME_KEYWORDS)
                        for cell in row
                        if cell
                    ):
                        header_row_idx = i
                        break

                if header_row_idx is None:
                    continue

                headers = [
                    str(cell).strip() if cell else ""
                    for cell in table[header_row_idx]
                ]

                name_idx = _match_header(headers, _NAME_KEYWORDS)
                type_idx = _match_header(headers, _TYPE_KEYWORDS)
                count_idx = _match_header(headers, _COUNT_KEYWORDS)

                if name_idx is None:
                    continue

                for row in table[header_row_idx + 1 :]:
                    if not row or name_idx >= len(row) or not row[name_idx]:
                        continue

                    name = str(row[name_idx]).strip()
                    if not name or name in _SKIP_ROWS:
                        continue

                    share_type = "보통주"
                    if type_idx is not None and type_idx < len(row) and row[type_idx]:
                        share_type = str(row[type_idx]).strip() or "보통주"

                    share_count = 0
                    if (
                        count_idx is not None
                        and count_idx < len(row)
                        and row[count_idx]
                    ):
                        parsed = _parse_count(str(row[count_idx]))
                        if parsed:
                            share_count = parsed

                    if name and share_count > 0:
                        shareholders.append(
                            Shareholder(
                                name=name,
                                shareType=share_type,
                                shareCount=share_count,
                            )
                        )

                if shareholders:
                    return shareholders, None

    return [], None


# ---------------------------------------------------------------------------
# Text-based fallback
# ---------------------------------------------------------------------------

_SHARE_TYPES = ("보통주", "우선주", "RCPS", "전환우선주", "상환전환우선주")

# Patterns: "홍길동 보통주 10,000"
_TEXT_PATTERNS = [
    re.compile(
        r"(?P<name>\S+(?:\s+\S+)?)\s+(?P<type>보통주|우선주|RCPS|전환우선주|상환전환우선주)\s+(?P<count>[\d,]+)"
    ),
    # Fallback: any name followed by digits
    re.compile(r"(?P<name>[\w가-힣]+)\s+(?P<count>[\d,]+)\s*주"),
]


def _parse_text_fallback(
    file_bytes: bytes,
) -> tuple[list[Shareholder], str]:
    shareholders: list[Shareholder] = []
    seen: set[str] = set()

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                for pattern in _TEXT_PATTERNS:
                    m = pattern.search(line)
                    if not m:
                        continue

                    name = m.group("name").strip()
                    if not name or name in _SKIP_ROWS or len(name) > 30:
                        continue
                    if name in seen:
                        continue

                    share_type = "보통주"
                    try:
                        share_type = m.group("type")
                    except IndexError:
                        pass

                    count_str = m.group("count").replace(",", "")
                    try:
                        count = int(count_str)
                    except ValueError:
                        continue

                    if count <= 0:
                        continue

                    seen.add(name)
                    shareholders.append(
                        Shareholder(
                            name=name,
                            shareType=share_type,
                            shareCount=count,
                        )
                    )
                    break

    warning = (
        "PDF 테이블을 인식하지 못해 텍스트 기반으로 파싱했습니다. "
        "주주 정보를 직접 확인하고 필요한 경우 수정해 주세요."
    )
    return shareholders, warning
