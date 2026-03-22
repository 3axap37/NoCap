"""
Characterization tests for pdf_parser_v2.py core functions.

These tests pin the CURRENT behavior of critical functions so that
refactoring can be verified against them.  All tests must pass both
before and after any structural changes.

Run:  cd backend && python -m pytest test_parser_v2.py -v
"""

import pytest

from models import Shareholder
from pdf_parser_v2 import (
    _clean_name,
    _collapse_single_char_spaces,
    _deduplicate,
    _detect_face_value,
    _is_skip_row,
    _is_valid_fallback_row,
    _normalize_share_type,
    _parse_count,
    _strip_org_parenthetical,
)


# =========================================================================
# 1. _clean_name
# =========================================================================

class TestCleanName:
    """Pin _clean_name behavior: whitespace, numbering, 주민번호, roman numerals, spacing."""

    # --- 일반 한글 이름 ---
    def test_plain_korean_name(self):
        assert _clean_name("홍길동") == "홍길동"

    def test_plain_korean_name_with_extra_spaces(self):
        assert _clean_name("  홍길동  ") == "홍길동"

    def test_multi_word_name(self):
        assert _clean_name("한양대학교 산학협력단") == "한양대학교 산학협력단"

    # --- 번호 접두사 제거 ---
    def test_numbered_prefix_dot(self):
        assert _clean_name("1. 홍길동") == "홍길동"

    def test_numbered_prefix_paren(self):
        assert _clean_name("3) 김철수") == "김철수"

    # --- 주민번호 접미사 제거 ---
    def test_resident_id_suffix(self):
        assert _clean_name("장고든(910223)") == "장고든"

    def test_resident_id_masked(self):
        assert _clean_name("장고든(910223-*******)") == "장고든"

    def test_resident_id_partial_mask(self):
        assert _clean_name("이영희(850101-2)") == "이영희"

    # --- Unicode 로마숫자 → ASCII ---
    def test_roman_numeral_iii(self):
        assert _clean_name("500 코리아 \u2162 투자조합") == "500 코리아 III 투자조합"

    def test_roman_numeral_ii(self):
        assert _clean_name("펀드 \u2161호") == "펀드 II호"

    def test_roman_numeral_iv(self):
        assert _clean_name("테스트 \u2163 펀드") == "테스트 IV 펀드"

    def test_roman_numeral_lowercase(self):
        assert _clean_name("펀드 \u2172호") == "펀드 iii호"

    # --- 글자 단위 공백 제거 (_collapse_single_char_spaces) ---
    def test_single_char_spaces_korean(self):
        assert _clean_name("박 미 영") == "박미영"

    def test_single_char_spaces_mixed(self):
        """2글자 이상 단어는 분리 유지."""
        assert _clean_name("한양대학교 산학협력단") == "한양대학교 산학협력단"

    def test_single_char_leading_then_multichar(self):
        """한 글자 뒤에 여러 글자 단어가 오는 경우."""
        assert _clean_name("김 미래에셋") == "김 미래에셋"

    # --- 탭/여러 공백 정규화 ---
    def test_multiple_spaces(self):
        assert _clean_name("홍   길동") == "홍 길동"

    def test_tab_normalization(self):
        assert _clean_name("홍\t길동") == "홍 길동"

    # --- 빈 입력 ---
    def test_empty_string(self):
        assert _clean_name("") == ""

    def test_whitespace_only(self):
        assert _clean_name("   ") == ""


# =========================================================================
# 1b. _strip_org_parenthetical (dead code이지만 behavior 고정)
# =========================================================================

class TestStripOrgParenthetical:
    """Pin _strip_org_parenthetical: 제거 대상 vs 보존 대상 괄호."""

    # --- 제거 대상 ---
    def test_remove_업무집행조합원(self):
        assert _strip_org_parenthetical("펀드A (업무집행조합원 홍길동)") == "펀드A"

    def test_remove_주식회사(self):
        assert _strip_org_parenthetical("테스트 (주식회사 ABC)") == "테스트"

    def test_remove_재단법인(self):
        assert _strip_org_parenthetical("펀드 (재단법인 XYZ)") == "펀드"

    def test_remove_유한회사(self):
        assert _strip_org_parenthetical("사업체 (유한회사)") == "사업체"

    def test_remove_사업자등록번호(self):
        assert _strip_org_parenthetical("펀드A (123-45-67890)") == "펀드A"

    # --- 보존 대상 ---
    def test_preserve_주(self):
        assert _strip_org_parenthetical("삼성전자(주)") == "삼성전자(주)"

    def test_preserve_SUP(self):
        assert _strip_org_parenthetical("테크펀드(SUP)") == "테크펀드(SUP)"

    def test_preserve_자기주식(self):
        assert _strip_org_parenthetical("홍길동(자기주식)") == "홍길동(자기주식)"

    def test_preserve_대표이사(self):
        assert _strip_org_parenthetical("김철수(대표이사)") == "김철수(대표이사)"

    def test_preserve_english_name(self):
        assert _strip_org_parenthetical("홍길동(JIN HAILIAN)") == "홍길동(JIN HAILIAN)"

    def test_preserve_DHP(self):
        assert _strip_org_parenthetical("펀드(DHP)") == "펀드(DHP)"

    # --- 복합 케이스: 제거 대상 + 보존 대상 ---
    def test_nested_remove_then_preserve(self):
        """끝 괄호만 검사하므로 (주) 뒤에 (업무집행조합원)이 오면 뒤만 제거."""
        result = _strip_org_parenthetical("테스트(주) (업무집행조합원 홍)")
        assert result == "테스트(주)"

    # --- 괄호 없는 이름 ---
    def test_no_parenthetical(self):
        assert _strip_org_parenthetical("홍길동") == "홍길동"


# =========================================================================
# 1c. _collapse_single_char_spaces (직접 테스트)
# =========================================================================

class TestCollapseSingleCharSpaces:
    def test_all_single_chars(self):
        assert _collapse_single_char_spaces("박 미 영") == "박미영"

    def test_no_single_chars(self):
        assert _collapse_single_char_spaces("한양대학교 산학협력단") == "한양대학교 산학협력단"

    def test_mixed(self):
        """한 글자 한글 + 여러 글자 단어 혼합."""
        assert _collapse_single_char_spaces("김 미래에셋") == "김 미래에셋"

    def test_single_hangul_then_multi(self):
        """연속된 한 글자 한글이 끝난 뒤 여러 글자 단어."""
        result = _collapse_single_char_spaces("이 해 성 펀드")
        assert result == "이해성 펀드"

    def test_english_single_chars_not_collapsed(self):
        """영문 한 글자는 한글이 아니므로 collapse하지 않음."""
        assert _collapse_single_char_spaces("A B C") == "A B C"

    def test_empty(self):
        assert _collapse_single_char_spaces("") == ""

    def test_number_single_char(self):
        """숫자 한 글자는 한글이 아니므로 collapse하지 않음."""
        assert _collapse_single_char_spaces("1 2 3") == "1 2 3"


# =========================================================================
# 2. _normalize_share_type
# =========================================================================

class TestNormalizeShareType:
    """Pin _normalize_share_type: 주식종류 표준화."""

    def test_보통주(self):
        assert _normalize_share_type("보통주") == "보통주"

    def test_우선주(self):
        assert _normalize_share_type("우선주") == "우선주"

    def test_상환전환우선주(self):
        assert _normalize_share_type("상환전환우선주") == "우선주"

    def test_전환우선주(self):
        assert _normalize_share_type("전환우선주") == "우선주"

    def test_RCPS(self):
        assert _normalize_share_type("RCPS") == "RCPS"

    def test_종류주식(self):
        assert _normalize_share_type("종류주식") == "종류주식"

    def test_empty_returns_보통주(self):
        assert _normalize_share_type("") == "보통주"

    def test_whitespace_only_returns_보통주(self):
        assert _normalize_share_type("   ") == "보통주"

    def test_보통_partial(self):
        assert _normalize_share_type("보통") == "보통주"

    def test_우선_partial(self):
        assert _normalize_share_type("우선") == "우선주"

    def test_unknown_passthrough(self):
        """알 수 없는 값은 그대로 반환."""
        assert _normalize_share_type("특수주") == "특수주"

    def test_leading_trailing_spaces(self):
        assert _normalize_share_type("  보통주  ") == "보통주"

    def test_의결권없는주식(self):
        assert _normalize_share_type("의결권없는주식") == "의결권없는주식"


# =========================================================================
# 3. _is_valid_fallback_row
# =========================================================================

class TestIsValidFallbackRow:
    """Pin _is_valid_fallback_row: OCR fallback 삽입 전 10개 규칙."""

    # --- 정상 케이스 → True ---
    def test_normal_shareholder(self):
        assert _is_valid_fallback_row("홍길동", 1000, [500, 1500]) is True

    def test_normal_fund_name(self):
        assert _is_valid_fallback_row("크립톤 엔젤링크 7호 개인투자조합", 5000, [3000, 7000]) is True

    # --- 메타 키워드 → False ---
    def test_reject_법인세법(self):
        assert _is_valid_fallback_row("법인세법 시행규칙", 1000, [500]) is False

    def test_reject_주주명부(self):
        assert _is_valid_fallback_row("주주명부", 1000, [500]) is False

    def test_reject_대표이사(self):
        assert _is_valid_fallback_row("대표이사 홍길동", 1000, [500]) is False

    def test_reject_발행주식(self):
        assert _is_valid_fallback_row("발행주식 총수", 1000, [500]) is False

    def test_reject_사업자등록번호(self):
        assert _is_valid_fallback_row("사업자등록번호 123-45-67890", 1000, [500]) is False

    def test_reject_액면가(self):
        assert _is_valid_fallback_row("액면가 500원", 1000, [500]) is False

    def test_reject_변동상황명세서(self):
        assert _is_valid_fallback_row("주식등변동상황명세서", 1000, [500]) is False

    # --- 이메일 → False ---
    def test_reject_email(self):
        assert _is_valid_fallback_row("hong@example.com", 1000, [500]) is False

    # --- 주민번호 마스킹 → False ---
    def test_reject_masked_resident_id(self):
        assert _is_valid_fallback_row("580810-*******", 1000, [500]) is False

    def test_reject_masked_resident_id_in_name(self):
        assert _is_valid_fallback_row("홍길동 580810-*******", 1000, [500]) is False

    # --- 날짜 패턴 → False ---
    def test_reject_date_month(self):
        assert _is_valid_fallback_row("12월 정기주총", 1000, [500]) is False

    def test_reject_date_year(self):
        assert _is_valid_fallback_row("2024년 주주명부", 1000, [500]) is False

    def test_reject_date_day(self):
        assert _is_valid_fallback_row("11일 기준", 1000, [500]) is False

    # --- 번호+이름 패턴 → False ---
    def test_reject_numbered_name(self):
        assert _is_valid_fallback_row("1 장근호", 1000, [500]) is False

    def test_reject_numbered_name_long(self):
        assert _is_valid_fallback_row("4 기타(직원)", 1000, [500]) is False

    # --- 숫자+단위만 → False ---
    def test_reject_count_only_명(self):
        assert _is_valid_fallback_row("5명", 1000, [500]) is False

    def test_reject_count_only_건(self):
        assert _is_valid_fallback_row("3건", 1000, [500]) is False

    def test_reject_count_only_주(self):
        assert _is_valid_fallback_row("10주", 1000, [500]) is False

    def test_reject_pure_number(self):
        assert _is_valid_fallback_row("5", 1000, [500]) is False

    # --- 이름 2자 미만 → False ---
    def test_reject_single_char(self):
        assert _is_valid_fallback_row("홍", 1000, [500]) is False

    # --- share_count 이상치 → False ---
    def test_reject_100x_median(self):
        """median 대비 100배 이상이면 제외."""
        assert _is_valid_fallback_row("홍길동", 100_001, [1000]) is False

    def test_accept_below_100x_median(self):
        assert _is_valid_fallback_row("홍길동", 99_999, [1000]) is True

    def test_reject_over_100m(self):
        """1억 이상이면 제외."""
        assert _is_valid_fallback_row("홍길동", 100_000_000, [1000]) is False

    def test_reject_under_100m_but_over_100x_median(self):
        """99,999,999 < 1억이지만 median(1000) × 100 = 100,000 초과 → False."""
        assert _is_valid_fallback_row("홍길동", 99_999_999, [1000]) is False

    # --- ocr_total과 같으면 → False ---
    def test_reject_equals_ocr_total(self):
        assert _is_valid_fallback_row("합계주주", 50000, [1000], ocr_total=50000) is False

    def test_accept_not_equals_ocr_total(self):
        assert _is_valid_fallback_row("홍길동", 1000, [500], ocr_total=50000) is True

    # --- 빈 page_share_counts → 100x median 체크 건너뜀 ---
    def test_empty_page_counts(self):
        assert _is_valid_fallback_row("홍길동", 999_999, []) is True


# =========================================================================
# 4. _deduplicate
# =========================================================================

class TestDeduplicate:
    """Pin _deduplicate: 완전 중복, 부분 중복(typed 우선) 동작."""

    def _sh(self, name: str, share_type: str, count: int) -> Shareholder:
        return Shareholder(name=name, shareType=share_type, shareCount=count)

    # --- 완전 동일 행 중복 제거 ---
    def test_exact_duplicate_removed(self):
        result = _deduplicate([
            self._sh("홍길동", "보통주", 1000),
            self._sh("홍길동", "보통주", 1000),
        ])
        assert len(result) == 1
        assert result[0].name == "홍길동"

    # --- 같은 이름+주식수, shareType만 다른 경우 → typed 유지 ---
    def test_typed_preferred_over_empty(self):
        """같은 (name, count)에서 shareType 있는 쪽이 유지되고 empty는 제거."""
        result = _deduplicate([
            self._sh("홍길동", "", 1000),
            self._sh("홍길동", "보통주", 1000),
        ])
        assert len(result) == 1
        assert result[0].shareType == "보통주"

    def test_typed_preferred_over_empty_reverse_order(self):
        """입력 순서와 무관하게 typed가 유지."""
        result = _deduplicate([
            self._sh("홍길동", "보통주", 1000),
            self._sh("홍길동", "", 1000),
        ])
        assert len(result) == 1
        assert result[0].shareType == "보통주"

    # --- 같은 이름, 다른 주식수 → 별도 유지 ---
    def test_same_name_different_count_kept(self):
        result = _deduplicate([
            self._sh("홍길동", "보통주", 1000),
            self._sh("홍길동", "보통주", 2000),
        ])
        assert len(result) == 2

    # --- 같은 이름, 같은 주식수, 다른 shareType → 둘 다 유지 ---
    def test_same_name_count_different_types_both_kept(self):
        """동일 주주가 보통주/우선주 보유 시 둘 다 유지."""
        result = _deduplicate([
            self._sh("홍길동", "보통주", 1000),
            self._sh("홍길동", "우선주", 1000),
        ])
        assert len(result) == 2
        types = {r.shareType for r in result}
        assert types == {"보통주", "우선주"}

    # --- 공백 차이만 있는 이름 (name_nospace로 매칭) ---
    def test_space_variant_name_dedup(self):
        """이름에 공백 차이만 있으면 같은 행으로 인식."""
        result = _deduplicate([
            self._sh("홍 길동", "보통주", 1000),
            self._sh("홍길동", "", 1000),
        ])
        assert len(result) == 1
        assert result[0].shareType == "보통주"

    # --- 모두 empty type이면 첫 번째만 유지 ---
    def test_all_empty_types_first_kept(self):
        result = _deduplicate([
            self._sh("홍길동", "", 1000),
            self._sh("홍길동", "", 1000),
        ])
        assert len(result) == 1

    # --- 빈 리스트 ---
    def test_empty_input(self):
        assert _deduplicate([]) == []

    # --- 여러 주주 혼합 ---
    def test_mixed_shareholders(self):
        result = _deduplicate([
            self._sh("홍길동", "보통주", 1000),
            self._sh("김철수", "보통주", 2000),
            self._sh("홍길동", "보통주", 1000),  # 중복
            self._sh("김철수", "우선주", 2000),  # 같은 이름+count, 다른 type
        ])
        assert len(result) == 3
        names = [r.name for r in result]
        assert names.count("홍길동") == 1
        assert names.count("김철수") == 2


# =========================================================================
# 5. _is_skip_row
# =========================================================================

class TestIsSkipRow:
    """Pin _is_skip_row: 집계행 판별."""

    # --- True 케이스 ---
    def test_합계(self):
        assert _is_skip_row("합계") is True

    def test_소계(self):
        assert _is_skip_row("소계") is True

    def test_총계(self):
        assert _is_skip_row("총계") is True

    def test_계(self):
        assert _is_skip_row("계") is True

    def test_합(self):
        assert _is_skip_row("합") is True

    def test_total(self):
        assert _is_skip_row("total") is True

    def test_합_계_with_space(self):
        assert _is_skip_row("합 계") is True

    def test_소_계_with_space(self):
        assert _is_skip_row("소 계") is True

    def test_발행주식총수(self):
        assert _is_skip_row("발행주식총수") is True

    def test_주주총수(self):
        assert _is_skip_row("주주총수") is True

    def test_총주식수(self):
        assert _is_skip_row("총주식수") is True

    def test_with_leading_trailing_space(self):
        assert _is_skip_row("  합계  ") is True

    # --- False 케이스 ---
    def test_normal_name(self):
        assert _is_skip_row("홍길동") is False

    def test_fund_name(self):
        assert _is_skip_row("크립톤 엔젤링크 7호 개인투자조합") is False

    def test_empty(self):
        assert _is_skip_row("") is False

    def test_partial_no_match(self):
        """'계' 한 글자는 _SKIP_CELLS에 있으므로 True."""
        assert _is_skip_row("계") is True


# =========================================================================
# 6. _detect_face_value
# =========================================================================

class TestDetectFaceValue:
    """Pin _detect_face_value: 액면가 감지."""

    def _make_word(self, text: str, x1: float, x2: float, y1: float, y2: float) -> dict:
        return {
            "text": text,
            "x1": x1, "x2": x2,
            "y1": y1, "y2": y2,
            "yc": (y1 + y2) / 2.0,
            "conf": 1.0,
        }

    def test_detect_500_face_value(self):
        """500원 액면가가 70% 이상 행에서 동일 x 위치에 등장 → 500 반환."""
        words = [
            # 3 data rows, 액면가 500이 3번 등장
            self._make_word("500", 300, 340, 100, 120),
            self._make_word("500", 300, 340, 150, 170),
            self._make_word("500", 300, 340, 200, 220),
            # 다른 단어들
            self._make_word("홍길동", 10, 80, 100, 120),
            self._make_word("김철수", 10, 80, 150, 170),
            self._make_word("이영희", 10, 80, 200, 220),
        ]
        result = _detect_face_value(words, n_data_rows=3)
        assert result == 500

    def test_detect_1000_face_value(self):
        """1,000원 액면가."""
        words = [
            self._make_word("1,000", 300, 360, 100, 120),
            self._make_word("1,000", 300, 360, 150, 170),
            self._make_word("1,000", 300, 360, 200, 220),
            self._make_word("홍길동", 10, 80, 100, 120),
            self._make_word("김철수", 10, 80, 150, 170),
            self._make_word("이영희", 10, 80, 200, 220),
        ]
        result = _detect_face_value(words, n_data_rows=3)
        assert result == 1000

    def test_no_face_value_when_not_enough(self):
        """70% 미만이면 None."""
        words = [
            self._make_word("500", 300, 340, 100, 120),
            # 2번째는 다른 값
            self._make_word("1000", 300, 360, 150, 170),
            self._make_word("홍길동", 10, 80, 100, 120),
            self._make_word("김철수", 10, 80, 150, 170),
        ]
        result = _detect_face_value(words, n_data_rows=3)
        assert result is None

    def test_no_face_value_insufficient_rows(self):
        """n_data_rows < 2이면 None."""
        words = [self._make_word("500", 300, 340, 100, 120)]
        result = _detect_face_value(words, n_data_rows=1)
        assert result is None

    def test_no_face_value_inconsistent_x(self):
        """x 위치가 일관되지 않으면 None."""
        words = [
            self._make_word("500", 300, 340, 100, 120),
            self._make_word("500", 100, 140, 150, 170),  # x1이 크게 다름
            self._make_word("500", 300, 340, 200, 220),
        ]
        result = _detect_face_value(words, n_data_rows=3)
        assert result is None

    def test_no_face_value_empty_words(self):
        assert _detect_face_value([], n_data_rows=3) is None

    def test_ignores_values_outside_range(self):
        """100 미만 또는 10000 초과 값은 무시."""
        words = [
            self._make_word("50", 300, 340, 100, 120),
            self._make_word("50", 300, 340, 150, 170),
            self._make_word("50", 300, 340, 200, 220),
        ]
        result = _detect_face_value(words, n_data_rows=3)
        assert result is None

    def test_detect_5000_face_value(self):
        """5,000원 액면가."""
        words = [
            self._make_word("5,000", 300, 370, 100, 120),
            self._make_word("5,000", 300, 370, 150, 170),
            self._make_word("5,000", 300, 370, 200, 220),
        ]
        result = _detect_face_value(words, n_data_rows=3)
        assert result == 5000


# =========================================================================
# Bonus: _parse_count (기초 유틸)
# =========================================================================

class TestParseCount:
    """Pin _parse_count: 문자열 → 정수 변환."""

    def test_plain_number(self):
        assert _parse_count("1234") == 1234

    def test_comma_formatted(self):
        assert _parse_count("1,234,567") == 1234567

    def test_with_주_suffix(self):
        assert _parse_count("8,000주") == 8000

    def test_with_spaces(self):
        assert _parse_count("  1000  ") == 1000

    def test_zero_returns_none(self):
        assert _parse_count("0") is None

    def test_negative_sign_stripped(self):
        """마이너스 부호는 non-digit으로 strip되어 100이 반환됨."""
        assert _parse_count("-100") == 100

    def test_empty_returns_none(self):
        assert _parse_count("") is None

    def test_none_returns_none(self):
        # _parse_count checks `if not raw` which catches None
        assert _parse_count(None) is None

    def test_float_truncated(self):
        assert _parse_count("1234.56") == 1234

    def test_no_digits(self):
        assert _parse_count("abc") is None
