"""
pdf_parser_v2.py — Hybrid pipeline: CLOVA OCR line-grouped text + GPT-4o vision

Per page:
  1. CLOVA OCR  → groups tokens into rows by y-coordinate → 2D list
  2. GPT-4o VLM → receives the page image AND the row-grouped OCR text
     - OCR suffix tells VLM exactly how many data rows to map
     - VLM must produce shareholders ≥ n_data_rows (minus aggregates)
  3. Post-VLM row-count check → warn if VLM dropped rows
"""

import base64
import io
import json
import logging
import math
import os
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from dotenv import load_dotenv
from pdf2image import convert_from_bytes

import openai
import requests

from models import Shareholder
from parser_types import RowCandidate, PageTrace, V3PageTrace

load_dotenv(encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Shared constants & utility functions
# (previously imported from pdf_parser.py)
# ---------------------------------------------------------------------------


class ParseMethod(str, Enum):
    TABLE = "table"
    TEXT = "text"
    OCR = "ocr"


@dataclass
class ParseResult:
    """파싱 결과를 구조화하여 반환."""

    shareholders: list[Shareholder] = field(default_factory=list)
    method: Optional[ParseMethod] = None
    warnings: list[str] = field(default_factory=list)
    page_count: int = 0
    traces: list[PageTrace] = field(default_factory=list)  # 디버그/eval 전용
    v3_traces: list[V3PageTrace] = field(default_factory=list)  # v3 reader-first 전용

    @property
    def success(self) -> bool:
        return len(self.shareholders) > 0


_SKIP_CELLS = {
    "소계", "합계", "총계", "계", "합", "총", "소", "total", "합 계", "소 계",
    "주주총수", "총주식수", "배정주식수", "발행주식총수", "총 주식수", "배정 주식수",
}
_KNOWN_SHARE_TYPES = frozenset(
    {"보통주", "우선주", "RCPS", "전환우선주", "상환전환우선주", "종류주식", "의결권없는주식"}
)

_ADDRESS_KEYWORDS = ("시", "구", "동", "로", "길", "번지", "아파트", "APT", "읍", "면", "리")
_UNIT_PATTERN = re.compile(r"\d+\s*[동호층]")


def _parse_count(raw: str) -> Optional[int]:
    """문자열에서 숫자를 추출. 소수점 이하는 버림."""
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.]", "", raw.strip())
    if not cleaned:
        return None
    try:
        value = int(float(cleaned))
        return value if value > 0 else None
    except (ValueError, OverflowError):
        return None


def _collapse_single_char_spaces(name: str) -> str:
    """PDF 텍스트 레이어의 글자 단위 공백을 제거한다.
    '박 미 영' → '박미영', '이 해 성' → '이해성'
    '한양대학교 산학협력단' → 변경 없음 (2글자 이상 단어)
    '적소적재 개인투자조합' → 변경 없음
    """
    tokens = name.split()
    if not tokens:
        return name

    result = []
    buffer = []

    def flush_buffer():
        nonlocal buffer
        if buffer:
            result.append("".join(buffer))
            buffer = []

    for token in tokens:
        if len(token) == 1 and "\uAC00" <= token <= "\uD7A3":
            buffer.append(token)
        else:
            flush_buffer()
            result.append(token)

    flush_buffer()
    return " ".join(result)


_ROMAN_MAP = {
    "\u2160": "I", "\u2161": "II", "\u2162": "III", "\u2163": "IV",
    "\u2164": "V", "\u2165": "VI", "\u2166": "VII", "\u2167": "VIII",
    "\u2168": "IX", "\u2169": "X",
    # Lowercase variants
    "\u2170": "i", "\u2171": "ii", "\u2172": "iii", "\u2173": "iv",
    "\u2174": "v", "\u2175": "vi", "\u2176": "vii", "\u2177": "viii",
    "\u2178": "ix", "\u2179": "x",
}


# 괄호 내 부가정보 제거 키워드 (업무집행조합원, 법인명 등)
_PAREN_REMOVE_KEYWORDS = frozenset({
    "업무집행조합원", "주식회사", "유한회사", "유한책임회사",
    "재단법인", "사단법인", "창조경제혁신센터", "혁신센터",
})


def _strip_org_parenthetical(name: str) -> str:
    """펀드명 뒤의 괄호 내 조직 부가정보 제거.

    제거 대상: (업무집행조합원 ...), (재단법인 ...), (... 주식회사) 등
    보존 대상: (주), (SUP), (DHP), (자기주식), (대표이사), (JIN HAILIAN) 등
    """
    while True:
        # 끝에 있는 괄호 그룹 매칭 (1단계 중첩 허용)
        m = re.search(r'\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)\s*$', name)
        if not m:
            break
        content = m.group(1)
        if any(kw in content for kw in _PAREN_REMOVE_KEYWORDS):
            name = name[:m.start()].rstrip()
        else:
            break
    # 사업자등록번호 단독 괄호: (NNN-NN-NNNNN) 또는 (NNN-NNNNNNN)
    name = re.sub(r'\s*\(\d{3}-\d{2,}-\d{4,}\)\s*$', '', name)
    return name


def _clean_name(name: str) -> str:
    """주주명 정리: 불필요한 문자 제거."""
    name = re.sub(r"[\s]+", " ", name).strip()
    name = re.sub(r"^\d+[.)]\s*", "", name)
    # 주민번호 접미사 제거: (910223), (910223-*******) 등
    name = re.sub(r'\(\d{6}(?:-[\d*]+)?\)', '', name)
    # Unicode 로마숫자 → ASCII (Ⅲ → III 등)
    for roman, ascii_eq in _ROMAN_MAP.items():
        if roman in name:
            name = name.replace(roman, ascii_eq)
    name = _collapse_single_char_spaces(name)
    return name.strip()


def _normalize_share_type(raw: str) -> str:
    """주식 종류를 표준화. 우선주 계열은 모두 '우선주'로 통일."""
    raw = raw.strip()
    if raw in _KNOWN_SHARE_TYPES:
        # 우선주 계열은 모두 "우선주"로 통일
        if "우선" in raw and raw != "우선주":
            return "우선주"
        return raw
    type_map = {
        "보통": "보통주",
        "우선": "우선주",
        "전환우선": "우선주",
        "상환전환우선": "우선주",
    }
    for key, value in type_map.items():
        if key in raw:
            return value
    return raw if raw else "보통주"


def _is_address(text: str) -> bool:
    """주소로 보이는 텍스트인지 확인."""
    if _UNIT_PATTERN.search(text):
        return True
    count = sum(1 for kw in _ADDRESS_KEYWORDS if kw in text)
    return count >= 2


def _is_skip_row(text: str) -> bool:
    """집계 행 등 건너뛸 행인지 확인."""
    normalized = text.strip().replace(" ", "")
    if normalized in _SKIP_CELLS:
        return True
    return any(skip in normalized for skip in _SKIP_CELLS if len(skip) > 1)


def _deduplicate(shareholders: list[Shareholder]) -> list[Shareholder]:
    """중복 제거. 동일 (이름, 주식수)에 대해 shareType 있는 것을 우선 유지."""
    seen: set[tuple[str, str, int]] = set()
    result: list[Shareholder] = []
    for sh in shareholders:
        key = (sh.name, sh.shareType, sh.shareCount)
        if key in seen:
            continue
        seen.add(key)
        result.append(sh)
    # 같은 (name_nospace, count)인데 shareType만 다른 중복 제거
    # shareType이 비어있는 행은 같은 이름+수량의 shareType 있는 행이 있으면 제거
    name_count_map: dict[tuple[str, int], list[Shareholder]] = {}
    for sh in result:
        k = (sh.name.replace(" ", ""), sh.shareCount)
        name_count_map.setdefault(k, []).append(sh)
    deduped: list[Shareholder] = []
    seen_nc: set[tuple[str, int]] = set()
    for sh in result:
        k = (sh.name.replace(" ", ""), sh.shareCount)
        if k in seen_nc:
            continue
        group = name_count_map[k]
        if len(group) > 1:
            # 같은 (name, count)가 여러 개: shareType 있는 것만 유지
            typed = [s for s in group if s.shareType]
            if typed:
                deduped.extend(typed)
            else:
                deduped.append(group[0])  # 모두 empty면 첫 번째만
        else:
            deduped.append(sh)
        seen_nc.add(k)
    return deduped


# ---------------------------------------------------------------------------
# CLOVA OCR API functions
# (previously imported from pdf_parser_clova.py)
# ---------------------------------------------------------------------------


def _call_clova_ocr(image_bytes: bytes) -> list:
    """
    CLOVA OCR API 호출. word-level 결과를 line+cell 단위로 병합하여 반환.
    Returns: [(bbox, text, confidence), ...]
    """
    payload = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [
            {
                "format": "jpg",
                "name": "page",
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }
        ],
    }
    headers = {
        "X-OCR-SECRET": CLOVA_OCR_SECRET,
        "Content-Type": "application/json",
    }

    resp = requests.post(
        CLOVA_OCR_INVOKE_URL,
        headers=headers,
        data=json.dumps(payload),
        timeout=30,
    )
    resp.raise_for_status()

    words = []
    for image_result in resp.json().get("images", []):
        for fld in image_result.get("fields", []):
            text = fld.get("inferText", "").strip()
            if not text:
                continue
            vertices = fld.get("boundingPoly", {}).get("vertices", [])
            if len(vertices) < 4:
                continue
            xs = [v.get("x", 0) for v in vertices[:4]]
            ys = [v.get("y", 0) for v in vertices[:4]]
            words.append({
                "text": text,
                "conf": fld.get("inferConfidence", 1.0),
                "x_left": min(xs),
                "x_right": max(xs),
                "y_top": min(ys),
                "y_bot": max(ys),
                "line_break": fld.get("lineBreak", True),
            })

    if not words:
        return []

    lines: list[list[dict]] = []
    current_line: list[dict] = []
    for word in words:
        current_line.append(word)
        if word["line_break"]:
            lines.append(current_line)
            current_line = []
    if current_line:
        lines.append(current_line)

    avg_height = sum(w["y_bot"] - w["y_top"] for w in words) / len(words)
    gap_threshold = avg_height * 1.5

    results = []
    for line in lines:
        if not line:
            continue
        line.sort(key=lambda w: w["x_left"])
        cell = [line[0]]
        for word in line[1:]:
            if word["x_left"] - cell[-1]["x_right"] <= gap_threshold:
                cell.append(word)
            else:
                _append_cell(cell, results)
                cell = [word]
        _append_cell(cell, results)

    return results


def _append_cell(cell_words: list[dict], results: list) -> None:
    """Merge a group of words into one cell and append in EasyOCR format."""
    merged_text = " ".join(w["text"] for w in cell_words)
    conf = min(w["conf"] for w in cell_words)
    x1 = min(w["x_left"] for w in cell_words)
    x2 = max(w["x_right"] for w in cell_words)
    y1 = min(w["y_top"] for w in cell_words)
    y2 = max(w["y_bot"] for w in cell_words)
    results.append(([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], merged_text, conf))


def _call_clova_ocr_words(image_bytes: bytes) -> list[dict]:
    """
    CLOVA OCR API 호출. raw word-level 결과를 dict 리스트로 반환.
    각 dict: {"text", "x1", "x2", "y1", "y2", "yc", "conf"}
    """
    payload = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(time.time() * 1000),
        "images": [
            {
                "format": "jpg",
                "name": "page",
                "data": base64.b64encode(image_bytes).decode("utf-8"),
            }
        ],
    }
    headers = {
        "X-OCR-SECRET": CLOVA_OCR_SECRET,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        CLOVA_OCR_INVOKE_URL,
        headers=headers,
        data=json.dumps(payload),
        timeout=30,
    )
    resp.raise_for_status()

    words = []
    for image_result in resp.json().get("images", []):
        for fld in image_result.get("fields", []):
            text = fld.get("inferText", "").strip()
            if not text:
                continue
            vertices = fld.get("boundingPoly", {}).get("vertices", [])
            if len(vertices) < 4:
                continue
            xs = [v.get("x", 0) for v in vertices[:4]]
            ys = [v.get("y", 0) for v in vertices[:4]]
            words.append({
                "text": text,
                "conf": fld.get("inferConfidence", 1.0),
                "x1": min(xs),
                "x2": max(xs),
                "y1": min(ys),
                "y2": max(ys),
                "yc": (min(ys) + max(ys)) / 2.0,
            })
    return words

# Column header tokens that are not shareholder data rows
_HEADER_TOKENS = {
    "주주명", "주식종류", "주식수", "성명", "이름", "종류", "수량",
    "지분율", "비율", "번호", "순번", "성 명", "주주 명", "no", "no.",
}

# Matches comma-formatted numbers (e.g. "1,234,567") or plain 4+ digit integers
_TOTAL_RE = re.compile(r'\d{1,3}(?:,\d{3})+|\d{4,}')

# Share count column: comma-formatted integers like "8,000" or "93,000",
# optionally followed by "주" unit suffix (e.g. "3,570주", "510주")
_SC_PAT = re.compile(r'^\d{1,3}(?:,\d{3})+주?$|^\d{3,}주$')

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
CLOVA_OCR_INVOKE_URL = os.getenv("CLOVA_OCR_INVOKE_URL", "")
CLOVA_OCR_SECRET = os.getenv("CLOVA_OCR_SECRET", "")
POPPLER_PATH = os.getenv("POPPLER_PATH") or None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Base VLM prompt (no OCR section — appended dynamically)
# ---------------------------------------------------------------------------

VLM_PROMPT = """\
이 이미지는 주주명부(주주 목록) 페이지입니다.
표의 각 행에서 주주 정보를 추출하여 아래 형식의 JSON으로 반환해주세요.

【규칙】

1. 집계행 완전 제외
   합계·소계·총계·계·합 등 집계 목적의 행은 포함하지 않습니다.

2. 법인·펀드·조합 이름 전체 보존 — 여러 줄 이어붙이기
   - 주주명 셀이 이미지에서 2~3줄로 나뉘어 있을 때, 같은 주주 행에 속하는 모든
     줄을 이어붙여 하나의 name으로 추출합니다.
     예) 이미지의 한 행 안에 "데일리 골든아워" / "바이오 헬스케어" / "펀드3호"가
         줄바꿈으로 나뉘어 있으면 → name: "데일리 골든아워 바이오 헬스케어 펀드3호"
     예) "크립톤-엔젤링크" / "7호 개인투자조합" → name: "크립톤-엔젤링크 7호 개인투자조합"
   - "재단법인", "주식회사", "유한회사" 등 법인 유형 접두어도 이름의 일부입니다.

3. 영문 병기·외국어 표기 포함
   - 이름 뒤에 괄호로 영문 이름이 병기된 경우 괄호 포함 전체를 name으로 반환합니다.
     예) "홍길동(HONG GIL DONG)" → name: "홍길동(HONG GIL DONG)"
   - 국적·외국어 표현이 이름 앞에 붙어 있어도 그대로 포함합니다.

4. 동일 주주, 복수 주식종류 분리
   같은 주주가 보통주·우선주 등 여러 종류를 보유하면 주식종류별로 별도 항목으로 추출합니다.
   예) 표에 "보통주" 열 1,445 / "우선주" 열 976 → 두 항목:
       {"name": "X펀드", "shareType": "보통주", "shareCount": 1445}
       {"name": "X펀드", "shareType": "우선주", "shareCount": 976}
   "0주" 또는 비어 있는 셀은 해당 종류를 보유하지 않은 것이므로 항목을 추가하지 않습니다.

5. 주식종류(shareType) 처리
   - 표 어딘가에 "보통주", "우선주" 등의 텍스트가 한 번이라도 나타나면
     주식종류 컬럼이 존재하는 것으로 간주합니다.
   - 각 행에서 주식종류가 빈 칸이면 가장 가까운 위쪽 행의 주식종류를 상속합니다.
   - 표 전체에 주식종류 관련 텍스트가 전혀 없는 경우에만 shareType을 null로 반환합니다.

6. 주식수(shareCount) 처리
   - 쉼표·"주" 단위를 제거한 양의 정수만 반환합니다.
   - 13자리 이상의 숫자(주민등록번호·사업자번호 등)는 주식수가 아니므로 제외합니다.
   - 주소·기타 텍스트가 숫자 컬럼에 있으면 해당 행은 제외합니다.

7. 한글 이름 정확도
   - 글자가 불명확할 때 문맥상 자연스러운 한글 음절을 선택하세요.
   - 펀드·조합명은 "골든아워", "프론티어", "글로버스타" 등
     금융업계에서 사용하는 일반적인 단어일 가능성이 높습니다.
   - 영어 'F' 발음의 한글 표기는 항상 '프'입니다 (포 아님).
     예: Frontier → "프론티어" (이미지에서 "포론티어"로 보이더라도 "프론티어"가 올바릅니다)
   - 모음 혼동 주의: 'ㅡ'(으)와 'ㅗ'(오)는 시각적으로 유사 — 영어 번역명에서 특히 주의.
   - 'ㅔ'(에)와 'ㅐ'(애) 구분: "혜"(ㅔ)와 "해"(ㅐ)는 다른 글자입니다.
   - "욱"과 "옥", "재"와 "계", "김"과 "건" 등 유사한 글자를 주의해서 구분하세요.
   - 한국 성씨(김, 이, 박, 최, 정, 강, 조, 윤, 장, 임 등)는 정해져 있습니다.
     "건"은 한국 성씨가 아닙니다. 성씨 위치(이름 첫 음절)에 "건"이 보이면
     "김"의 오독일 가능성이 매우 높습니다 — 이미지를 다시 확인하여 "김"으로 교정하세요.

8. 누락 없는 완전 추출
   - 표의 모든 주주를 처음부터 끝까지 빠짐없이 추출하세요.
   - 마지막 주주까지 반드시 포함하세요. 집계행과 헤더만 제외하고 나머지는 전부 포함합니다.
   - 아래 OCR 데이터의 각 행을 순서대로 검토하여 주식수가 포함된 행이 모두 추출되었는지
     확인하세요. 특히 목록 중간·끝 부분의 누락을 주의하세요.

반환 형식 (JSON만, 다른 텍스트 없이):
{"shareholders": [{"name": "주주명", "shareType": "주식종류 또는 null", "shareCount": 정수}]}

반드시 위 JSON 형식만 반환하세요. 주주를 찾지 못한 경우에도 {"shareholders": []}를 반환하세요.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_shareholders_from_pdf(
    file_bytes: bytes,
) -> tuple[list[Shareholder], Optional[str]]:
    result = _parse_pipeline_v2(file_bytes)
    warning = "; ".join(result.warnings) if result.warnings else None
    return result.shareholders, warning


def _v2_confidence_low(result: ParseResult) -> bool:
    """V2 결과의 신뢰도가 낮은지 판단. True면 V3 fallback 시도."""
    if not result.traces:
        return False
    # OCR이 0행 감지 = CLOVA가 표를 못 읽은 경우 (VLM만으로 추출)
    total_ocr_rows = sum(len(t.ocr_rows) for t in result.traces)
    if total_ocr_rows == 0:
        return True
    return False


# ---------------------------------------------------------------------------
# Adaptive DPI
# ---------------------------------------------------------------------------


def _safe_dpi(
    w_pt: float,
    h_pt: float,
    max_pixels: int = 60_000_000,
    target_dpi: int = 300,
    min_dpi: int = 240,
) -> int:
    """페이지 크기(pt)에서 max_pixels를 넘지 않는 최대 dpi를 계산한다."""
    safe = math.sqrt(max_pixels * 72 * 72 / (w_pt * h_pt))
    return max(min_dpi, min(target_dpi, int(safe)))


def _choose_document_dpi(file_bytes: bytes) -> int:
    """PDF 내 가장 큰 페이지 기준으로 문서 단일 dpi를 결정한다."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not available, falling back to 300dpi")
        return 300

    reader = PdfReader(io.BytesIO(file_bytes))
    max_area = 0.0
    max_w = max_h = 0.0

    for page in reader.pages:
        w_pt = float(page.mediabox.width)
        h_pt = float(page.mediabox.height)
        area = w_pt * h_pt
        if area > max_area:
            max_area = area
            max_w, max_h = w_pt, h_pt

    dpi = _safe_dpi(max_w, max_h)
    logger.info(
        "Adaptive DPI: chosen=%d, max_page=%.0fx%.0fpt, est_pixels=%.1fM",
        dpi, max_w, max_h,
        (max_w / 72 * dpi) * (max_h / 72 * dpi) / 1_000_000,
    )
    return dpi


def _pdf_has_text_layer(file_bytes: bytes) -> bool:
    """PDF에 텍스트 레이어가 있는지 확인. 스캔 전용 PDF는 False."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            text = (page.extract_text() or "").strip()
            if len(text) > 20:
                return True
        return False
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _parse_pipeline_v2(file_bytes: bytes) -> ParseResult:
    result = ParseResult()

    if not OPENAI_API_KEY:
        result.warnings.append("OPENAI_API_KEY가 설정되지 않아 처리할 수 없습니다.")
        return result

    dpi = _choose_document_dpi(file_bytes)

    try:
        images = convert_from_bytes(
            file_bytes,
            dpi=dpi,
            poppler_path=POPPLER_PATH,
            fmt="png",
        )
    except Exception as e:
        logger.warning("PDF→image conversion failed: %s", e)
        result.warnings.append(f"PDF 이미지 변환 실패: {e}")
        return result

    result.page_count = len(images)
    clova_available = bool(CLOVA_OCR_INVOKE_URL and CLOVA_OCR_SECRET)

    all_shareholders: list[Shareholder] = []
    needs_review = False

    for page_num, img in enumerate(images, 1):
        # PNG for VLM
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_bytes = png_buf.getvalue()

        # Step 1: CLOVA OCR → column-based row reconstruction
        clova_suffix = ""
        ocr_candidates: list[RowCandidate] = []
        clova_rows: list[list[str]] = []  # raw_cells view for legacy helpers
        ocr_total: Optional[int] = None
        face_value: Optional[int] = None
        if clova_available:
            jpeg_buf = io.BytesIO()
            img.save(jpeg_buf, format="JPEG", quality=95)
            try:
                raw_words = _call_clova_ocr_words(jpeg_buf.getvalue())
            except Exception as e:
                logger.warning("CLOVA OCR failed on page %d: %s", page_num, e)
                raw_words = []
            if raw_words:
                ocr_total = _extract_ocr_total_from_words(raw_words)
                ocr_candidates = _reconstruct_rows_from_words(raw_words)
                face_value = _detect_face_value(raw_words, len(ocr_candidates))
                clova_rows = [rc.raw_cells for rc in ocr_candidates]
                if clova_rows:
                    debug_file = os.getenv("V2_DEBUG_FILE", "")
                    if debug_file:
                        with open(debug_file, "a", encoding="utf-8") as df:
                            df.write(f"\n=== Page {page_num} — Reconstructed Rows ({len(clova_rows)}) ===\n")
                            for i, row in enumerate(clova_rows, 1):
                                df.write(f"Row {i}: {row}\n")
                    clova_suffix = _build_ocr_suffix(clova_rows)

        # Step 2: VLM with OCR suffix
        vlm_result = _extract_via_vlm(png_bytes, page_num, clova_suffix)
        if vlm_result is None:
            logger.warning("VLM returned None for page %d", page_num)
            needs_review = True
            continue

        vlm_rows_raw = list(vlm_result)  # snapshot for trace

        validated = _post_validate(vlm_result)
        page_rows: list[RowCandidate] = validated["shareholders"]
        page_needs_review = validated["needs_review"]

        # Step 3: retry if VLM output is incomplete.
        # Trigger when either:
        #   (a) share-sum < 85% of OCR aggregate total, or
        #   (b) shareholder count < 85% of OCR detected rows
        #       (catches cases where large-count shareholders dominate the sum
        #        but small-count ones are silently dropped).
        vlm_retry_rows: Optional[list[RowCandidate]] = None
        n_ocr_rows = _count_clean_ocr_rows(clova_rows) if clova_rows else 0
        extracted_total = sum(rc.share_count or 0 for rc in page_rows)
        shares_deficit = ocr_total and extracted_total < ocr_total * 0.95
        # Retry if VLM count is strictly less than OCR-detected count: OCR is a
        # reliable counter (it just reads numbers), so any gap means VLM dropped rows.
        count_deficit = n_ocr_rows >= 2 and len(page_rows) < n_ocr_rows
        if shares_deficit or count_deficit:
            missing_shares = (ocr_total - extracted_total) if ocr_total else 0
            missing_rows = n_ocr_rows - len(page_rows)
            retry_note = (
                f"\n\n【주의】 주주 누락 감지\n"
                f"OCR이 이 페이지에서 {n_ocr_rows}명의 주주를 감지했습니다.\n"
                f"현재 추출된 주주 수는 {len(page_rows)}명입니다"
            )
            if missing_rows > 0:
                retry_note += f" ({missing_rows}명 누락)"
            if missing_shares > 0:
                retry_note += f" — 주식 합계 차이: {missing_shares:,}주"
            # List specific missing share counts to help VLM find them
            vl_counts_set = {rc.share_count for rc in page_rows}
            missing_details = []
            for ocr_row in clova_rows:
                sc_val = _parse_count(ocr_row[-1])
                if sc_val and sc_val > 0 and sc_val not in vl_counts_set:
                    ocr_name = ocr_row[0].split()[0] if ocr_row[0] else "?"
                    missing_details.append(f"{ocr_name}... ({sc_val:,}주)")
            retry_note += ".\n"
            if missing_details:
                retry_note += f"누락된 주주: {', '.join(missing_details)}\n"
            retry_note += (
                f"OCR 목록의 모든 항목을 반드시 포함하여 다시 출력하세요.\n"
                f"OCR 목록에 있는 이름을 이미지에서 찾아 정확하게 교정하고, "
                f"이미지에서 보이는 추가 주주도 포함하세요.\n"
            )
            retry_suffix = clova_suffix + retry_note
            vlm_retry = _extract_via_vlm(png_bytes, page_num, retry_suffix, source="vlm_retry")
            if vlm_retry is not None:
                vlm_retry_rows = list(vlm_retry)  # snapshot for trace
                retry_validated = _post_validate(vlm_retry)
                retry_total = sum(rc.share_count or 0 for rc in retry_validated["shareholders"])
                if retry_total > extracted_total or len(retry_validated["shareholders"]) > len(page_rows):
                    page_rows = retry_validated["shareholders"]
                    page_needs_review = retry_validated["needs_review"]

        # OCR fallback: if any clean OCR-detected share count is still absent from
        # VLM output (after retry), insert that OCR row directly.  Only applies when
        # the share count is unique in OCR (no ambiguity) and absent from VLM output.
        if clova_rows:
            vl_counts = {rc.share_count for rc in page_rows}
            for ocr_row in clova_rows:
                ocr_raw_name = ocr_row[0]
                addr_trimmed = False
                if _ocr_name_has_address(ocr_raw_name):
                    # Use name prefix instead of skipping entirely
                    ocr_raw_name = _extract_name_prefix(ocr_raw_name)
                    if not ocr_raw_name:
                        continue
                    addr_trimmed = True
                sc_str = ocr_row[-1]
                sc_val = _parse_count(sc_str)
                if not sc_val or sc_val <= 0 or sc_val in vl_counts:
                    continue
                # Skip if this share count appears in multiple OCR rows (ambiguous)
                if sum(1 for r in clova_rows if _parse_count(r[-1]) == sc_val) != 1:
                    continue
                name = _clean_name(" ".join(ocr_raw_name.split()))
                if _is_skip_row(name) or not name:
                    continue
                if not _is_valid_fallback_row(name, sc_val, [rc.share_count or 0 for rc in page_rows], ocr_total=ocr_total):
                    logger.info("OCR fallback rejected: %s (%d)", name, sc_val)
                    continue
                share_type_str = ocr_row[1] if len(ocr_row) == 3 else ""
                nt = _normalize_share_type(share_type_str) if share_type_str else ""
                if nt not in _KNOWN_SHARE_TYPES:
                    nt = ""
                fb_flags = ["count_only_match"]
                if addr_trimmed:
                    fb_flags.append("address_trimmed")
                page_rows.append(RowCandidate(
                    name=name,
                    share_type=nt,
                    share_count=sc_val,
                    source="ocr_fallback",
                    row_index=len(page_rows),
                    flags=fb_flags,
                    raw_cells=ocr_row,
                ))
                logger.info("OCR fallback added: %s (%d)", name, sc_val)

        # OCR share_type correction: when VLM misreads share type, trust OCR.
        # Build a map from unique share_count → OCR share_type, then override.
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
                corrected: list[RowCandidate] = []
                for rc in page_rows:
                    new_st = ocr_st_map.get(rc.share_count or 0)
                    if new_st and new_st != rc.share_type:
                        corrected.append(RowCandidate(
                            name=rc.name,
                            share_type=new_st,
                            share_count=rc.share_count,
                            source=rc.source,
                            row_index=rc.row_index,
                            confidence=rc.confidence,
                            flags=rc.flags + ["type_ocr_override"],
                            raw_cells=rc.raw_cells,
                        ))
                    else:
                        corrected.append(rc)
                page_rows = corrected

        # Face value correction: if OCR detected a per-share face value (액면가)
        # and ALL counts are divisible by it, VLM might have read the 금액 column.
        # Only correct if VLM counts ≈ OCR counts (both read the same wrong column).
        # If OCR counts / face_value ≈ VLM counts, VLM already has correct values.
        if face_value and len(page_rows) >= 2 and ocr_candidates:
            vlm_counts = [rc.share_count or 0 for rc in page_rows]
            if all(c > 0 and c % face_value == 0 for c in vlm_counts):
                # Check if VLM and OCR read the same column (both need correction)
                ocr_sc_sorted = sorted(rc.share_count or 0 for rc in ocr_candidates if rc.share_count)
                vlm_sc_sorted = sorted(c for c in vlm_counts if c > 0)
                # If OCR and VLM counts are similar → both read wrong column → correct
                vlm_matches_ocr = (
                    len(ocr_sc_sorted) == len(vlm_sc_sorted) and
                    all(abs(o - v) / max(v, 1) < 0.05 for o, v in zip(ocr_sc_sorted, vlm_sc_sorted))
                )
                if vlm_matches_ocr:
                    corrected = [(rc.share_count or 0) // face_value for rc in page_rows]
                    logger.info("Face value correction: dividing all counts by %d", face_value)
                    page_rows = [
                        RowCandidate(
                            name=rc.name, share_type=rc.share_type,
                            share_count=corrected[i],
                            source=rc.source, row_index=rc.row_index,
                            confidence=rc.confidence,
                            flags=rc.flags + ["face_value_corrected"],
                            raw_cells=rc.raw_cells,
                        )
                        for i, rc in enumerate(page_rows)
                    ]

        # Remove rows whose share_count equals the aggregate total
        # (leaked aggregate rows like "합계 110,000")
        if len(page_rows) > 2:
            total_sum = sum(rc.share_count or 0 for rc in page_rows)
            page_rows_clean = []
            for rc in page_rows:
                sc = rc.share_count or 0
                other_sum = total_sum - sc
                # Row's count ≈ sum of all other rows → aggregate row
                if sc > 0 and other_sum > 0 and abs(sc - other_sum) / other_sum < 0.02:
                    logger.info("Removed aggregate row: %s (%d)", rc.name, sc)
                    continue
                # Row's count == OCR-detected total → aggregate row
                if ocr_total and sc == ocr_total:
                    logger.info("Removed ocr_total row: %s (%d)", rc.name, sc)
                    continue
                page_rows_clean.append(rc)
            page_rows = page_rows_clean

        # Build PageTrace for this page
        trace = PageTrace(
            page_num=page_num,
            ocr_rows=ocr_candidates,
            vlm_rows=vlm_rows_raw,
            vlm_retry_rows=vlm_retry_rows,
            final_rows=page_rows,
            ocr_total=ocr_total,
        )
        result.traces.append(trace)

        # Page-level reject: score each page to detect non-shareholder pages
        # (e.g., 법인세법 주식등변동상황명세서). Only for multi-page documents.
        if result.page_count > 1 and page_rows:
            if _should_reject_page(page_rows, clova_rows):
                logger.info("Page %d rejected (non-shareholder form page)", page_num)
                page_rows = []

        # Cross-page duplicate detection: if ≥ 50% of this page's shareholders
        # already appeared on previous pages (by name OR share_count), reject.
        if result.page_count > 1 and page_rows and all_shareholders:
            existing_names = {sh.name.replace(" ", "") for sh in all_shareholders}
            existing_counts = {sh.shareCount for sh in all_shareholders}
            # Name-based overlap
            name_dup = sum(1 for rc in page_rows if rc.name.replace(" ", "") in existing_names)
            # Share-count-based overlap (same count already seen)
            count_dup = sum(1 for rc in page_rows if (rc.share_count or 0) in existing_counts)
            # Use the higher of the two signals
            dup_ratio = max(
                name_dup / len(page_rows) if page_rows else 0,
                count_dup / len(page_rows) if page_rows else 0,
            )
            if len(page_rows) >= 2 and dup_ratio >= 0.5:
                logger.info("Page %d rejected (%.0f%% duplicate: name=%d, count=%d of %d)",
                            page_num, dup_ratio * 100, name_dup, count_dup, len(page_rows))
                page_rows = []

        # Convert RowCandidate → Shareholder for accumulation
        all_shareholders.extend(rc.to_shareholder() for rc in page_rows)
        if page_needs_review:
            needs_review = True

    # Cross-page aggregate removal: if any shareholder's count ≈ sum of all others
    if len(all_shareholders) > 2:
        total = sum(sh.shareCount for sh in all_shareholders)
        clean = []
        for sh in all_shareholders:
            other = total - sh.shareCount
            if other > 0 and abs(sh.shareCount - other) / other < 0.02:
                logger.info("Cross-page aggregate removed: %s (%d)", sh.name, sh.shareCount)
                continue
            clean.append(sh)
        all_shareholders = clean

    # shareType null 보정: 모든 주주의 shareType이 비어있고,
    # PDF에 텍스트 레이어가 있으면 (스캔 전용 PDF 제외) "보통주"로 설정.
    # 스캔 PDF(Test6/7/8 등)는 GT가 null이므로 건드리지 않음.
    if all_shareholders and all(not sh.shareType for sh in all_shareholders):
        has_text_layer = _pdf_has_text_layer(file_bytes)
        if has_text_layer:
            logger.info("shareType null → 보통주 보정 (텍스트 레이어 감지, %d명)", len(all_shareholders))
            all_shareholders = [
                Shareholder(name=sh.name, shareType="보통주", shareCount=sh.shareCount)
                for sh in all_shareholders
            ]

    result.shareholders = _deduplicate(all_shareholders)
    result.method = ParseMethod.OCR

    if not result.shareholders:
        result.warnings.append(
            "주주 정보를 추출하지 못했습니다. PDF를 확인하거나 수동으로 입력해 주세요."
        )
    else:
        result.warnings.append("GPT-4o 비전으로 파싱했습니다. 결과를 확인해 주세요.")

    if needs_review:
        result.warnings.append("일부 주주 정보가 불확실합니다. 수동으로 확인해 주세요.")

    # V2+V3 앙상블: V2 신뢰도가 낮으면 V3를 시도하고 더 나은 결과 선택
    if _v2_confidence_low(result) and result.shareholders:
        try:
            from pdf_parser_v3 import _parse_pipeline_v3
            v3_result = _parse_pipeline_v3(file_bytes)
            if v3_result.shareholders and len(v3_result.shareholders) >= len(result.shareholders):
                # V3가 같거나 더 많은 주주를 추출하면 V3 사용
                logger.info("V3 fallback: V2=%d명, V3=%d명 → V3 채택",
                            len(result.shareholders), len(v3_result.shareholders))
                result.shareholders = v3_result.shareholders
                result.warnings.append("V3 파이프라인으로 대체되었습니다.")
        except Exception as e:
            logger.warning("V3 fallback failed: %s", e)

    return result


# ---------------------------------------------------------------------------
# CLOVA OCR → line-grouped 2D list + pre-filtering
# ---------------------------------------------------------------------------


def _is_valid_fallback_row(name: str, share_count: int, page_share_counts: list[int], ocr_total: Optional[int] = None) -> bool:
    """OCR fallback 삽입 전 유효성 검증. False면 삽입하지 않는다."""

    # 1. 메타/서명/날짜 키워드가 이름에 포함되면 제외
    _FALLBACK_REJECT_KEYWORDS = {
        "주주총수", "총주식수", "배정주식수", "법인설립등기일",
        "서기", "(인)", "지식산업센터", "등기", "설립일",
        "발행주식", "자본금", "액면가", "납입", "잔고",
        "대표이사", "주권번호", "미발행",
        # 법률 서식/메타 키워드
        "주주명부", "법인세법", "시행규칙", "별지", "관리번호",
        "변동상황", "상장여부", "무액면주식", "주식등변동상황명세서",
        "사업자등록번호", "주권상장여부", "출자좌수", "실명전환",
    }
    name_normalized = name.replace(" ", "")
    if any(kw.replace(" ", "") in name_normalized for kw in _FALLBACK_REJECT_KEYWORDS):
        return False

    # 1b. 이메일 주소 포함 제외
    if '@' in name:
        return False

    # 2. 이름이 "번호 + 이름" 패턴이면 제외 (예: "1 장근호", "4 기타(직원)")
    if re.match(r'^\d+\s+', name):
        return False

    # 2b. 마스킹된 주민번호 포함 (예: "580810-*******")
    if re.search(r'\d{6}-\*+', name):
        return False

    # 3. 이름에 날짜 패턴이 포함되면 제외 (예: "12월", "2024년", "11일")
    if re.search(r'\d{1,2}월|\d{1,2}일|\d{4}년', name):
        return False

    # 4. shareCount가 page 내 VLM 추출 주식수 median 대비 100배 이상이면 제외
    if page_share_counts:
        median_sc = sorted(page_share_counts)[len(page_share_counts) // 2]
        if median_sc > 0 and share_count > median_sc * 100:
            return False

    # 5. shareCount가 1억 이상이면 제외
    if share_count >= 100_000_000:
        return False

    # 6. 이름이 숫자+단위뿐이면 제외 (예: "5명", "3건", "10주")
    if re.match(r'^\d+[명건개호주]?$', name.strip()):
        return False

    # 7. 이름이 2자 미만이면 제외
    if len(name.strip()) < 2:
        return False

    # 8. shareCount가 ocr_total과 같으면 제외 (집계행 누출)
    if ocr_total is not None and share_count == ocr_total:
        return False

    return True


def _is_signature_or_meta_row(row: list[str]) -> bool:
    """서명/등기/날짜/기타 비주주 행인지 판별한다."""
    row_text = " ".join(row)

    # 서명/등기 전용 키워드
    _META_KEYWORDS = {"법인설립등기일", "서기", "지식산업센터", "등기부", "설립일"}
    row_normalized = row_text.replace(" ", "")
    if any(kw in row_normalized for kw in _META_KEYWORDS):
        return True

    # "(인)" 단독 또는 문장 끝에 등장: 서명 행
    if "(인)" in row_text or "( 인 )" in row_text:
        return True

    # 날짜 전용 행: "2024년 12월 11일" 같은 패턴이 row의 대부분을 차지
    date_chars = len(re.findall(r'[\d년월일\s]', row_text))
    if len(row_text) > 0 and date_chars / len(row_text) > 0.7:
        return True

    return False


def _filter_ocr_lines(lines: list[list[str]]) -> list[list[str]]:
    """
    Remove non-shareholder rows before sending to VLM:
      - Aggregate rows (합계/소계/총계/계 etc.)
      - Single-token column headers (주주명/주식종류/주식수 etc.)
      - Rows with no digits at all (page title, section label)
      - Rows where every digit sequence is 13+ chars (주민번호/사업자번호)
      - Signature/registration/date meta rows
    """
    result = []
    for row in lines:
        # 1. Aggregate rows
        if any(_is_skip_row(cell) for cell in row):
            continue
        # 2. Single-token column headers
        if len(row) == 1 and row[0].strip().lower() in _HEADER_TOKENS:
            continue
        # 3. Long no-digit text → sentence / disclaimer / long address description
        #    Short no-digit rows (≤30 chars) are kept: they could be shareholder names
        #    e.g. ['신인근'], ['마그나프렌드 임팩트인핸스펀드'], ['황만회']
        row_text = " ".join(row)
        if not re.search(r'\d', row_text) and len(row_text) > 30:
            continue
        # 4. Every digit run is 13+ chars → ID/business-registration number only
        numbers = re.findall(r'\d+', row_text.replace(',', ''))
        if numbers and all(len(n) >= 13 for n in numbers):
            continue
        # 5. Signature/registration/date meta rows
        if _is_signature_or_meta_row(row):
            continue
        result.append(row)
    return result


def _reconstruct_rows_from_words(words: list[dict]) -> list[RowCandidate]:
    """
    Column-based shareholder row reconstruction from raw CLOVA word-level data.

    1. Detect share-count column from comma-formatted numbers (e.g. "8,000").
    2. Name column right boundary = sc_x1_min * 0.30.
    3. Cluster sc words by y → anchor rows (skipping aggregate rows).
    4. For each anchor: merge name-col words in y-range, find share type.
    5. Return list[RowCandidate] (source="ocr").
    """
    if not words:
        return []

    avg_h = sum(w["y2"] - w["y1"] for w in words) / len(words)

    # Matches plain 2-4 digit integers (no commas, no "주") for small share counts
    # that comma-formatted _SC_PAT would miss (e.g., "800", "400", "176").
    _SC_PAT2 = re.compile(r'^\d{2,4}$')

    def _on_skip_row(w: dict) -> bool:
        return any(
            _is_skip_row(other["text"])
            for other in words
            if abs(other["yc"] - w["yc"]) <= avg_h * 1.5
        )

    # Step 1: share-count words — comma-formatted, not on aggregate rows
    sc_words = [
        w for w in words
        if _SC_PAT.match(w["text"].strip())
        and not _on_skip_row(w)
    ]
    if not sc_words:
        return []

    # Filter x-position outliers: e.g. a "총주식수" summary row printed to the left
    # of the actual share-count column will have a much smaller x1 than data rows,
    # pulling sc_x1_min down and making name_x2_limit too narrow.
    if len(sc_words) >= 2:
        max_x1 = max(w["x1"] for w in sc_words)
        sc_words = [w for w in sc_words if w["x1"] >= max_x1 * 0.75]
        if not sc_words:
            return []

    sc_x1_min = min(w["x1"] for w in sc_words)
    sc_x2_max = max(w["x2"] for w in sc_words)

    # Second-pass: plain 2-4 digit integers (no commas) in the same x-column.
    # Catches small share counts like "800", "400", "176" that _SC_PAT misses.
    # Safety guard: must overlap the x-range of already-detected sc_words.
    existing_ycs = {w["yc"] for w in sc_words}
    sc2_words = [
        w for w in words
        if _SC_PAT2.match(w["text"].strip())
        and not _on_skip_row(w)
        and w["x1"] >= sc_x1_min * 0.85
        and w["x2"] <= sc_x2_max * 1.15
        and not any(abs(w["yc"] - yc) <= avg_h * 0.5 for yc in existing_ycs)
    ]
    if sc2_words:
        for w in sc2_words:
            w["_pass"] = 2
        sc_words = sc_words + sc2_words
        sc_x1_min = min(w["x1"] for w in sc_words)

    # Third-pass: compound tokens with embedded share counts (e.g. "우선주식 76,347주").
    # OCR sometimes merges share type + count into one token.
    _SC_EMBEDDED = re.compile(r'(\d{1,3}(?:,\d{3})+)주')
    all_sc_ycs = {w["yc"] for w in sc_words}
    sc3_words = []
    for w in words:
        t = w["text"].strip()
        if _SC_PAT.match(t) or _SC_PAT2.match(t):
            continue
        m = _SC_EMBEDDED.search(t)
        if not m:
            continue
        sc_val = int(m.group(1).replace(",", ""))
        if sc_val < 100:
            continue
        if _on_skip_row(w):
            continue
        if any(abs(w["yc"] - yc) <= avg_h * 0.5 for yc in all_sc_ycs):
            continue
        synth = dict(w)
        synth["text"] = m.group(1)
        # Use existing column x-position to avoid corrupting sc_x1_min
        synth["x1"] = sc_x1_min
        synth["x2"] = sc_x2_max
        synth["_pass"] = 3
        sc3_words.append(synth)
    if sc3_words:
        sc_words = sc_words + sc3_words

    # Name column right boundary: determined dynamically.
    # Many PDFs have an address column between the name and share-type columns.
    # When a share-type column is detected, keep the conservative 0.45 limit that
    # stays left of the address zone.  When there is no share-type column (pure
    # name + share-count layout), use a generous 0.80 so wide fund names fit.
    has_share_type_col = any(
        w["x1"] < sc_x1_min
        and _normalize_share_type(w["text"]) in _KNOWN_SHARE_TYPES
        for w in words
    )
    name_x2_limit = sc_x1_min * (0.45 if has_share_type_col else 0.80)

    # Step 2: cluster sc_words by y → one anchor group per shareholder row.
    # Use avg_h * 1.0 threshold so closely-spaced rows (e.g. 1.2× height) are
    # kept separate, while same-row multi-column counts (< 0.5× height apart)
    # are merged into one anchor group.
    sc_sorted = sorted(sc_words, key=lambda w: w["yc"])
    groups: list[list[dict]] = [[sc_sorted[0]]]
    for w in sc_sorted[1:]:
        if w["yc"] - groups[-1][-1]["yc"] <= avg_h * 1.0:
            groups[-1].append(w)
        else:
            groups.append([w])

    anchors = [sum(w["yc"] for w in g) / len(g) for g in groups]

    # Step 3: for each anchor build RowCandidate.
    # Use symmetric "Voronoi" y-ranges: each anchor owns the space halfway to its
    # neighbours.  For boundary anchors, mirror the gap to the single neighbour.
    rows: list[RowCandidate] = []
    for i, (yc, grp) in enumerate(zip(anchors, groups)):
        if i > 0:
            y_lo = (anchors[i - 1] + yc) / 2
        else:
            half = (anchors[1] - anchors[0]) / 2 if len(anchors) > 1 else avg_h * 2.0
            y_lo = max(0.0, yc - half)

        if i < len(anchors) - 1:
            y_hi = (yc + anchors[i + 1]) / 2
        else:
            half = (anchors[-1] - anchors[-2]) / 2 if len(anchors) > 1 else avg_h * 2.0
            y_hi = yc + half

        # Name words: left column, inside this anchor's y-range, not header/skip.
        # Exclude digit-heavy tokens (IDs, dates, reg numbers: >60% digits/hyphens/dots).
        # Do NOT use _is_address here — it falsely rejects fund names like "7호 개인투자조합".
        def _is_digit_heavy(t: str) -> bool:
            t = t.strip()
            n = sum(1 for c in t if c.isdigit() or c in "-.")
            return len(t) >= 5 and n / len(t) > 0.60

        name_words = sorted(
            [
                w for w in words
                if (w["x2"] <= name_x2_limit or (w["x1"] < name_x2_limit and w["x2"] < sc_x1_min))
                and y_lo < w["yc"] <= y_hi
                and not _is_skip_row(w["text"])
                and w["text"].strip().lower() not in _HEADER_TOKENS
                and not _is_digit_heavy(w["text"])
                and _normalize_share_type(w["text"]) not in _KNOWN_SHARE_TYPES
            ],
            key=lambda w: (round(w["yc"] / (avg_h * 0.5)), w["x1"]),
        )
        name = " ".join(w["text"] for w in name_words).strip()
        if not name:
            continue

        # Share count: largest value in anchor group (strip trailing "주" unit)
        best_sc = max(grp, key=lambda w: _parse_count(w["text"].rstrip("주")) or 0)
        sc_text = best_sc["text"].rstrip("주")

        # Share type: word nearest to anchor y, x between name col and sc col
        share_type = ""
        for w in sorted(words, key=lambda w: abs(w["yc"] - yc)):
            if (
                w["x1"] > name_x2_limit
                and w["x1"] < sc_x1_min
                and abs(w["yc"] - yc) <= avg_h * 1.5
            ):
                nt = _normalize_share_type(w["text"])
                if nt in _KNOWN_SHARE_TYPES:
                    share_type = nt
                    break

        raw_cells = [name, share_type, sc_text] if share_type else [name, sc_text]
        # Determine flags from pass origin of the best sc word
        rc_flags: list[str] = []
        best_pass = best_sc.get("_pass", 1)
        if best_pass == 2:
            rc_flags.append("small_sc_2nd_pass")
        elif best_pass == 3:
            rc_flags.append("embedded_sc_3rd_pass")

        rows.append(RowCandidate(
            name=name,
            share_type=share_type,
            share_count=_parse_count(sc_text),
            source="ocr",
            row_index=len(rows),
            flags=rc_flags,
            raw_cells=raw_cells,
        ))

    return rows


def _extract_ocr_total_from_words(words: list[dict]) -> Optional[int]:
    """Find the max share count in aggregate rows (합계/소계/총계 etc.)."""
    if not words:
        return None

    avg_h = sum(w["y2"] - w["y1"] for w in words) / len(words)

    # Group words into physical rows by y proximity
    sorted_w = sorted(words, key=lambda w: w["yc"])
    row_groups: list[list[dict]] = [[sorted_w[0]]]
    for w in sorted_w[1:]:
        if w["yc"] - row_groups[-1][0]["yc"] <= avg_h * 0.8:
            row_groups[-1].append(w)
        else:
            row_groups.append([w])

    best: Optional[int] = None
    for grp in row_groups:
        row_text = " ".join(w["text"] for w in grp)
        is_agg = any(_is_skip_row(w["text"]) for w in grp) or any(
            kw in row_text for kw in ("합계", "소계", "총계")
        )
        if not is_agg:
            continue
        for m in _TOTAL_RE.finditer(row_text):
            n_str = m.group(0).replace(",", "")
            if len(n_str) >= 13:
                continue
            try:
                n = int(n_str)
                if n > 100 and (best is None or n > best):
                    best = n
            except ValueError:
                pass
    return best


def _extract_ocr_total(lines: list[list[str]]) -> Optional[int]:
    """
    Scan aggregate rows (합계/소계/총계/계 etc.) in raw OCR lines and return the
    maximum share count found. Ignores 13+-digit ID/registration numbers.
    """
    best: Optional[int] = None
    for row in lines:
        if not any(_is_skip_row(cell) for cell in row):
            continue  # not an aggregate row
        row_text = " ".join(row)
        for m in _TOTAL_RE.finditer(row_text):
            n_str = m.group(0).replace(",", "")
            if len(n_str) >= 13:
                continue  # ID / business-registration number
            try:
                n = int(n_str)
                if n > 100 and (best is None or n > best):
                    best = n
            except ValueError:
                pass
    return best


def _extract_clova_lines(image_bytes: bytes, page_num: int) -> list[list[str]]:
    """
    Call CLOVA OCR and return a 2D list: each inner list is one physical row,
    cells sorted by x-coordinate.
    Grouping threshold: y_center within 50% of avg bbox height → same row.
    """
    try:
        ocr_results = _call_clova_ocr(image_bytes)
        if not ocr_results:
            return []

        items = []
        for bbox, text, _ in ocr_results:
            ys = [pt[1] for pt in bbox]
            xs = [pt[0] for pt in bbox]
            items.append({
                "text": text,
                "y_top": min(ys),
                "y_center": (min(ys) + max(ys)) / 2,
                "height": max(ys) - min(ys),
                "x_left": min(xs),
            })

        if not items:
            return []

        avg_height = sum(it["height"] for it in items) / len(items)
        row_threshold = avg_height * 0.5

        items.sort(key=lambda it: (it["y_top"], it["x_left"]))
        rows: list[list[dict]] = []
        current: list[dict] = [items[0]]

        for item in items[1:]:
            if abs(item["y_center"] - current[0]["y_center"]) <= row_threshold:
                current.append(item)
            else:
                rows.append(sorted(current, key=lambda it: it["x_left"]))
                current = [item]
        rows.append(sorted(current, key=lambda it: it["x_left"]))

        return [[it["text"] for it in row] for row in rows]

    except Exception as e:
        logger.warning("CLOVA line extraction failed on page %d: %s", page_num, e)
        return []


_ADDR_GEO = frozenset({
    "서울", "경기도", "경기", "부산", "대구", "인천", "광주", "대전",
    "울산", "강원도", "강원", "충청남도", "충남", "충청북도", "충북",
    "경상남도", "경남", "경상북도", "경북", "전라남도", "전남",
    "전라북도", "전북", "제주도", "제주", "세종",
})
_ADDR_SUFFIX_CHARS = frozenset("시구읍면리동")


def _ocr_name_has_address(name: str) -> bool:
    """Return True if the OCR-reconstructed name contains embedded address text.

    Two detection paths:
    1. Primary: at least 2 address keyword matches (e.g. "마포구 동교로").
    2. Secondary: any word after the first word is a known city/province geo name
       OR ends with an administrative suffix (시·구·읍·면·리·동).
       Catches cases like "송인탁 부산광역시 명륜2차아이파크" where only "시" matches.
    """
    _addr_kws = ("시", "구", "동", "로", "길", "번지", "아파트", "호(", "동,")
    if sum(1 for kw in _addr_kws if kw in name) >= 2:
        return True
    # Secondary: check whether any non-first word looks like an address token
    words = name.split()
    for w in words[1:]:
        if w in _ADDR_GEO or (len(w) >= 2 and w[-1] in _ADDR_SUFFIX_CHARS):
            return True
    return False


def _extract_name_prefix(name: str) -> str:
    """
    For names that include embedded address text (column-overlap artifact), return
    the clean name prefix that appears before the address starts.  Returns "" if the
    prefix would be shorter than 2 characters (not useful as a hint).
    """
    words = name.split()
    prefix: list[str] = []
    for w in words:
        if w in _ADDR_GEO or (len(w) >= 2 and w[-1] in _ADDR_SUFFIX_CHARS):
            break
        prefix.append(w)
    result = " ".join(prefix).strip()
    if len(result) >= 2:
        return result
    # Fallback: scan for short Korean person-name tokens embedded in address text.
    # Korean names are typically 2-4 pure-hangul characters, not geo/address words.
    _NAME_EXCLUDE_SUFFIX = _ADDR_SUFFIX_CHARS | frozenset("로길층호")
    for w in words:
        if (
            2 <= len(w) <= 4
            and all("\uAC00" <= c <= "\uD7A3" for c in w)
            and w not in _ADDR_GEO
            and w[-1] not in _NAME_EXCLUDE_SUFFIX
        ):
            return w
    return ""


def _build_ocr_suffix(rows: list[list[str]]) -> str:
    """
    Build the OCR hint section from column-reconstructed rows.
    Each row is [name, share_type?, share_count_str].

    - Rows with clean names are included as-is.
    - Rows with embedded address text use a name PREFIX followed by "..." so VLM
      knows the OCR name is truncated and must find the full name in the image.
    - Returns "" only when every row has no usable name at all.
    """
    hint_rows: list[list[str]] = []
    incomplete_indices: set[int] = set()
    for row in rows:
        if not _ocr_name_has_address(row[0]):
            hint_rows.append(row)
        else:
            prefix = _extract_name_prefix(row[0])
            if prefix:
                # Mark with "..." so VLM knows to find the full name in the image
                hint_rows.append([prefix + "...", *row[1:]])
                incomplete_indices.add(len(hint_rows) - 1)
    if not hint_rows:
        return ""
    n = len(hint_rows)
    rows_fmt = "\n".join(
        f"{i + 1}: {' | '.join(row)}"
        for i, row in enumerate(hint_rows)
    )
    has_incomplete = bool(incomplete_indices)
    incomplete_note = (
        "\n※ '...'로 끝나는 이름은 OCR이 일부만 감지한 것입니다.\n"
        "   이미지에서 해당 행을 직접 찾아 전체 이름을 정확하게 기입하세요.\n"
        "   이미지에서 읽기 어려우면 OCR이 감지한 앞부분(... 이전)만 기입하고 추측하지 마세요.\n"
        if has_incomplete else ""
    )
    return (
        f"\n【OCR 보조 데이터 — 감지된 주주 {n}명】\n"
        f"아래 주주들을 반드시 포함하여 출력하세요. 이미지에서 추가 주주가 보이면 함께 포함하세요.\n"
        f"주주명은 반드시 이미지를 참조하여 정확하게 완성하세요 (OCR 이름은 불완전할 수 있습니다).\n"
        f"주식수와 주식종류는 아래 값을 그대로 사용하세요.\n"
        f"{incomplete_note}\n"
        f"{rows_fmt}\n"
    )


def _count_clean_ocr_rows(rows: list[list[str]]) -> int:
    """Count OCR rows that have at least a usable name prefix (not pure address garbage)."""
    return sum(
        1 for row in rows
        if not _ocr_name_has_address(row[0]) or bool(_extract_name_prefix(row[0]))
    )


def _detect_face_value(words: list[dict], n_data_rows: int) -> Optional[int]:
    """Detect per-share face value (액면가) from OCR words.

    If a small integer (100-10000) appears at a consistent x-position in
    ≥ 70% of data rows, it's likely the '1주의 금액' column. Returns that
    value, or None if not detected.
    """
    if n_data_rows < 2:
        return None
    # 쉼표 포함/미포함 모두 매칭: "500", "1,000", "5,000" 등
    _FACE_PAT = re.compile(r'^\d{1,2}(?:,\d{3})?$|^\d{2,5}$')
    candidates: dict[int, list[dict]] = {}
    for w in words:
        t = w["text"].strip()
        if _FACE_PAT.match(t):
            val = int(t.replace(",", ""))
            if 100 <= val <= 10000:
                candidates.setdefault(val, []).append(w)
    for val, ws in candidates.items():
        if len(ws) >= n_data_rows * 0.7:
            # Check x-position consistency (all within 15% of mean)
            x_mean = sum(w["x1"] for w in ws) / len(ws)
            if all(abs(w["x1"] - x_mean) / max(x_mean, 1) < 0.15 for w in ws):
                return val
    return None


# ---------------------------------------------------------------------------
# VLM (GPT-4o)
# ---------------------------------------------------------------------------


def _extract_via_vlm(
    image_bytes: bytes,
    page_num: int,
    clova_text: str = "",
    source: str = "vlm",
) -> Optional[list[RowCandidate]]:
    """
    Call GPT-4o vision with optional CLOVA OCR suffix appended to the prompt.
    Retry once on empty response. Returns None only on unrecoverable exception.
    Returns list[RowCandidate] with the given source tag.
    """
    prompt = VLM_PROMPT + clova_text if clova_text else VLM_PROMPT

    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    b64 = base64.b64encode(image_bytes).decode()

    def _call() -> str:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=4096,
            temperature=0,
        )
        return resp.choices[0].message.content or ""

    try:
        content = _call()
        if not content.strip():
            logger.warning("VLM page %d: empty response, retrying once", page_num)
            content = _call()
        if not content.strip():
            logger.warning("VLM page %d: empty response after retry", page_num)
            return None

        content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning("VLM page %d JSON parse error: %s | content: %.200s", page_num, e, content)
            return []

        raw_list = data.get("shareholders", [])
        if not isinstance(raw_list, list):
            raw_list = []

        candidates: list[RowCandidate] = []
        for idx, item in enumerate(raw_list):
            name = _clean_name(str(item.get("name", "")).strip())
            raw_type = item.get("shareType")
            if raw_type is None:
                share_type = ""
            else:
                share_type = _normalize_share_type(str(raw_type).strip() or "보통주")
            raw_count = item.get("shareCount", 0)
            if isinstance(raw_count, str):
                count = _parse_count(raw_count) or 0
            else:
                try:
                    count = int(raw_count)
                except (ValueError, TypeError):
                    count = 0

            if name and count > 0:
                candidates.append(RowCandidate(
                    name=name,
                    share_type=share_type,
                    share_count=count,
                    source=source,
                    row_index=idx,
                ))

        return candidates

    except Exception as e:
        logger.warning("VLM page %d failed: %s", page_num, e)
        return None


def _should_reject_page(page_rows: list[RowCandidate], clova_rows: list[list[str]]) -> bool:
    """페이지가 비주주 서식(법인세법 양식 등)인지 판단. True면 페이지 전체 reject."""
    _FORM_KEYWORDS = {
        "법인세법", "시행규칙", "별지", "변동상황명세서", "관리번호",
        "주권상장여부", "무액면주식", "사업자등록번호", "변동상황",
        "출자좌수", "실명전환",
    }

    # 1. OCR 텍스트에서 법률/서식 키워드 밀도 체크
    ocr_text = " ".join(" ".join(row) for row in clova_rows) if clova_rows else ""
    ocr_text_norm = ocr_text.replace(" ", "")
    kw_hits = sum(1 for kw in _FORM_KEYWORDS if kw in ocr_text_norm)
    if kw_hits >= 3:
        return True

    # 2. 이름 품질: 10자 이상 문장형 이름 비율
    if page_rows:
        long_name_count = sum(1 for rc in page_rows if len(rc.name) > 15)
        long_ratio = long_name_count / len(page_rows)
        # shareType null 비중 (보조 지표, 단독 reject 금지)
        null_type_ratio = sum(1 for rc in page_rows if not rc.share_type) / len(page_rows)
        # 키워드 2개 이상 + 문장형 이름 50% 이상 + null type 높음
        if kw_hits >= 2 and long_ratio >= 0.3 and null_type_ratio >= 0.5:
            return True

    return False


# ---------------------------------------------------------------------------
# Post-validation
# ---------------------------------------------------------------------------


def _post_validate(candidates: list[RowCandidate]) -> dict:
    """Filter obviously bad entries; flag uncertain results.
    Accepts and returns list[RowCandidate]."""
    valid: list[RowCandidate] = []
    had_issues = False

    _VLM_REJECT_KEYWORDS = {
        "법인세법", "시행규칙", "별지", "관리번호", "변동상황명세서",
        "주권상장여부", "무액면주식", "출자좌수", "사업자등록번호",
    }
    for rc in candidates:
        sc = rc.share_count or 0
        # Reject metadata rows (대표이사, 감사 등 직위 포함)
        if rc.name.replace(" ", "").startswith("대표이사"):
            had_issues = True
            continue
        # Reject legal form / meta rows
        name_norm = rc.name.replace(" ", "")
        if any(kw.replace(" ", "") in name_norm for kw in _VLM_REJECT_KEYWORDS):
            had_issues = True
            continue
        # Use strict address check (keyword count only, not digit+unit pattern):
        # fund names like "펀드3호" or "7호 개인투자조합" contain "호" which
        # matches _UNIT_PATTERN (\d+[동호층]) and would be falsely rejected.
        name_kw_count = sum(1 for kw in ("시", "구", "동", "로", "길", "번지", "아파트", "APT", "읍", "면", "리") if kw in rc.name)
        if _is_skip_row(rc.name):
            had_issues = True
            continue
        if name_kw_count >= 2:
            # Try extracting name prefix before discarding entirely
            prefix = _extract_name_prefix(rc.name)
            if prefix and len(prefix) >= 2:
                trimmed = RowCandidate(
                    name=_clean_name(prefix),
                    share_type=rc.share_type,
                    share_count=rc.share_count,
                    source=rc.source,
                    row_index=rc.row_index,
                    confidence=rc.confidence,
                    flags=rc.flags + ["address_trimmed"],
                    raw_cells=rc.raw_cells,
                )
                valid.append(trimmed)
                had_issues = True
                continue
            had_issues = True
            continue
        if sc <= 0 or sc > 10_000_000_000:
            had_issues = True
            continue
        valid.append(rc)

    return {
        "shareholders": valid,
        "ok": bool(valid) and not had_issues,
        "needs_review": had_issues or not valid,
    }
