# pdf_parser_v2.py 리팩토링 진단 리포트

**파일**: `backend/pdf_parser_v2.py` (1,679줄)
**작성일**: 2026-03-21
**목적**: 코드 변경 없이 구조 분석 및 리팩토링 기회 식별

---

## 1. 파일 구조 맵

### 1.1 전체 함수 목록

| # | 함수명 | 줄 범위 | 줄 수 | 역할 |
|---|--------|---------|-------|------|
| 1 | `_parse_count` | 78–89 | 12 | 문자열에서 정수 추출 (쉼표/소수점 처리) |
| 2 | `_collapse_single_char_spaces` | 92–119 | 28 | PDF 글자 단위 공백 제거 ("박 미 영"→"박미영") |
| 3 | `_strip_org_parenthetical` | 140–158 | 19 | 펀드명 뒤 조직 부가정보 괄호 제거 |
| 4 | `_clean_name` | 161–172 | 12 | 주주명 정리 (번호 접두사, 주민번호, 로마숫자, 공백) |
| 5 | `_normalize_share_type` | 175–192 | 18 | 주식종류 표준화 (우선주 계열 통일) |
| 6 | `_is_address` | 195–200 | 6 | 주소 텍스트 판별 |
| 7 | `_is_skip_row` | 203–208 | 6 | 집계행(합계/소계 등) 판별 |
| 8 | `_deduplicate` | 211–244 | 34 | 중복 주주 제거 (이름+주식수+종류 기준) |
| 9 | `_call_clova_ocr` | 253–334 | 82 | CLOVA OCR API 호출 + line/cell 병합 |
| 10 | `_append_cell` | 337–345 | 9 | word 그룹 → 단일 cell 병합 헬퍼 |
| 11 | `_call_clova_ocr_words` | 348–397 | 50 | CLOVA OCR API 호출 (raw word-level dict 반환) |
| 12 | `_safe_dpi` | 518–527 | 10 | 페이지 크기 기반 안전 DPI 계산 |
| 13 | `_choose_document_dpi` | 530–556 | 27 | PDF 전체 DPI 결정 |
| 14 | `_pdf_has_text_layer` | 559–570 | 12 | PDF 텍스트 레이어 존재 여부 확인 |
| 15 | `parse_shareholders_from_pdf` | 494–499 | 6 | **공개 API** — PDF bytes → (shareholders, warning) |
| 16 | `_v2_confidence_low` | 502–510 | 9 | V2 결과 신뢰도 판단 (V3 fallback 트리거) |
| 17 | **`_parse_pipeline_v2`** | 578–924 | **347** | **핵심 파이프라인** — 페이지별 OCR+VLM+후처리 전체 흐름 |
| 18 | `_is_valid_fallback_row` | 932–988 | 57 | OCR fallback 삽입 전 유효성 검증 (10개 규칙) |
| 19 | `_is_signature_or_meta_row` | 991–1010 | 20 | 서명/등기/날짜 행 판별 |
| 20 | `_filter_ocr_lines` | 1013–1044 | 32 | 비주주 OCR 행 제거 (VLM 전달 전) |
| 21 | **`_reconstruct_rows_from_words`** | 1047–1244 | **198** | OCR word → 주주 행 재구성 (3-pass column detection) |
| 22 | `_extract_ocr_total_from_words` | 1247–1281 | 35 | word-level에서 합계 행의 최대 주식수 추출 |
| 23 | `_extract_ocr_total` | 1284–1304 | 21 | line-level에서 합계 행의 최대 주식수 추출 |
| 24 | `_extract_clova_lines` | 1307–1352 | 46 | CLOVA OCR → 2D 행 리스트 (y 기반 그룹핑) |
| 25 | `_ocr_name_has_address` | 1364–1381 | 18 | OCR 이름에 주소 포함 여부 판별 |
| 26 | `_extract_name_prefix` | 1384–1410 | 27 | 주소 포함 이름에서 이름 접두사 추출 |
| 27 | `_build_ocr_suffix` | 1413–1455 | 43 | OCR 데이터 → VLM 프롬프트 suffix 생성 |
| 28 | `_count_clean_ocr_rows` | 1458–1463 | 6 | 유효한 OCR 행 수 카운트 |
| 29 | `_detect_face_value` | 1466–1490 | 25 | 액면가(1주의 금액) 컬럼 자동 감지 |
| 30 | `_extract_via_vlm` | 1498–1587 | 90 | GPT-4o VLM 호출 + JSON 파싱 → RowCandidate 리스트 |
| 31 | `_should_reject_page` | 1590–1615 | 26 | 비주주 서식 페이지 reject 판단 |
| 32 | `_post_validate` | 1623–1679 | 57 | VLM 결과 후검증 (주소/메타/범위 필터링) |

### 1.2 함수 간 호출 관계

```
parse_shareholders_from_pdf()          ← 공개 API (유일한 진입점)
  └─ _parse_pipeline_v2()              ← 메인 파이프라인
       ├─ _choose_document_dpi()
       │    └─ _safe_dpi()
       ├─ convert_from_bytes()          [pdf2image]
       │
       │  ── per page loop ──
       ├─ _call_clova_ocr_words()       ← CLOVA OCR 호출
       ├─ _extract_ocr_total_from_words()
       ├─ _reconstruct_rows_from_words()
       │    ├─ _is_skip_row()
       │    ├─ _normalize_share_type()
       │    └─ _parse_count()
       ├─ _detect_face_value()
       ├─ _build_ocr_suffix()
       │    ├─ _ocr_name_has_address()
       │    └─ _extract_name_prefix()
       ├─ _extract_via_vlm()            ← GPT-4o VLM 호출
       │    ├─ _clean_name()
       │    │    ├─ _collapse_single_char_spaces()
       │    │    └─ _ROMAN_MAP
       │    ├─ _normalize_share_type()
       │    └─ _parse_count()
       ├─ _post_validate()
       │    ├─ _is_skip_row()
       │    ├─ _extract_name_prefix()
       │    └─ _clean_name()
       ├─ _count_clean_ocr_rows()
       │    ├─ _ocr_name_has_address()
       │    └─ _extract_name_prefix()
       ├─ _is_valid_fallback_row()      ← OCR fallback 검증
       ├─ _ocr_name_has_address()
       ├─ _extract_name_prefix()
       ├─ _should_reject_page()         ← 페이지 reject
       ├─ _pdf_has_text_layer()
       ├─ _deduplicate()
       └─ _v2_confidence_low()
            └─ pdf_parser_v3._parse_pipeline_v3()  [외부 모듈]
```

**사용되지 않는 함수들:**
- `_call_clova_ocr()` (L253–334): `_call_clova_ocr_words()`로 대체됨. 호출하는 곳 없음.
- `_extract_ocr_total()` (L1284–1304): `_extract_ocr_total_from_words()`로 대체됨. 호출하는 곳 없음.
- `_extract_clova_lines()` (L1307–1352): 호출하는 곳 없음.
- `_filter_ocr_lines()` (L1013–1044): 호출하는 곳 없음.
- `_is_address()` (L195–200): `_post_validate`에서 직접 keyword count로 대체됨. 호출하는 곳 없음.
- `_strip_org_parenthetical()` (L140–158): 호출하는 곳 없음.

### 1.3 데이터 플로우

```
PDF bytes
  │
  ▼
_choose_document_dpi() ──→ DPI 값
  │
  ▼
convert_from_bytes() ──→ [PIL Image, ...]  (페이지별 이미지)
  │
  │  ╔══════════════════ per page ══════════════════╗
  │  ║                                               ║
  ▼  ║  img → JPEG → _call_clova_ocr_words()        ║
     ║         │                                     ║
     ║         ▼                                     ║
     ║    raw_words: list[dict]                      ║
     ║         │                                     ║
     ║    ┌────┴────────┬──────────────┐             ║
     ║    ▼             ▼              ▼             ║
     ║  _extract_     _reconstruct_  _detect_        ║
     ║  ocr_total_    rows_from_     face_value()    ║
     ║  from_words()  words()                        ║
     ║    │             │              │             ║
     ║    ▼             ▼              │             ║
     ║  ocr_total    ocr_candidates   face_value    ║
     ║    (int)      (RowCandidate[]) (int|None)    ║
     ║                  │                            ║
     ║                  ▼                            ║
     ║         _build_ocr_suffix()                   ║
     ║                  │                            ║
     ║                  ▼                            ║
     ║            clova_suffix (str)                 ║
     ║                  │                            ║
     ║    img → PNG ────┤                            ║
     ║                  ▼                            ║
     ║         _extract_via_vlm()  ← 1차 VLM 호출    ║
     ║                  │                            ║
     ║                  ▼                            ║
     ║         _post_validate()                      ║
     ║                  │                            ║
     ║                  ▼                            ║
     ║         page_rows (RowCandidate[])            ║
     ║                  │                            ║
     ║    ┌─── deficit check ───┐                    ║
     ║    │ shares_deficit?     │                    ║
     ║    │ count_deficit?      │                    ║
     ║    └────────┬────────────┘                    ║
     ║             │ yes                             ║
     ║             ▼                                 ║
     ║    _extract_via_vlm()  ← retry VLM (2차)     ║
     ║             │                                 ║
     ║             ▼                                 ║
     ║    better? → page_rows 교체                   ║
     ║                  │                            ║
     ║    ┌─── OCR fallback ───┐                    ║
     ║    │ VLM 누락 행 보충     │                    ║
     ║    └────────┬───────────┘                    ║
     ║             ▼                                 ║
     ║    ┌─── share_type OCR 보정 ───┐             ║
     ║    └────────┬──────────────────┘             ║
     ║             ▼                                 ║
     ║    ┌─── face_value 보정 ───┐                 ║
     ║    └────────┬──────────────┘                 ║
     ║             ▼                                 ║
     ║    ┌─── aggregate row 제거 ───┐              ║
     ║    └────────┬─────────────────┘              ║
     ║             ▼                                 ║
     ║    _should_reject_page()                      ║
     ║    cross-page duplicate detection             ║
     ║             │                                 ║
     ║             ▼                                 ║
     ║    → all_shareholders에 누적                  ║
     ║                                               ║
     ╚═══════════════════════════════════════════════╝
  │
  ▼
cross-page aggregate removal
  │
  ▼
shareType null → "보통주" 보정 (텍스트 레이어 있을 때)
  │
  ▼
_deduplicate()
  │
  ▼
_v2_confidence_low() → V3 fallback (optional)
  │
  ▼
ParseResult (shareholders: list[Shareholder])
```

---

## 2. 코드 스멜 / 리팩토링 기회

### 2.1 과도하게 긴 함수

| 함수 | 줄 수 | 문제 |
|------|-------|------|
| **`_parse_pipeline_v2`** | **347줄** | 한 함수에 7개 이상의 후처리 단계가 인라인. 읽기 어렵고 개별 단계 테스트 불가. |
| **`_reconstruct_rows_from_words`** | **198줄** | 3-pass 감지 + 앵커링 + 이름/주식수/주식종류 매핑이 한 함수. 내부에 함수 정의(`_is_digit_heavy`)까지 포함. |
| `_extract_via_vlm` | 90줄 | API 호출 + JSON 파싱 + RowCandidate 변환이 한 함수. 허용 가능 범위이나 경계선. |

### 2.2 죽은 코드 (Dead Code)

총 **6개 함수, ~230줄**이 어디서도 호출되지 않음:

| 함수 | 줄 수 | 추정 경위 |
|------|-------|----------|
| `_call_clova_ocr()` | 82 | word-level API(`_call_clova_ocr_words`)로 전환 후 미삭제 |
| `_extract_ocr_total()` | 21 | word-level 버전으로 전환 후 미삭제 |
| `_extract_clova_lines()` | 46 | word-level 재구성으로 전환 후 미삭제 |
| `_filter_ocr_lines()` | 32 | `_build_ocr_suffix`가 자체 필터링으로 전환 후 미삭제 |
| `_is_address()` | 6 | `_post_validate`에서 직접 구현으로 대체 |
| `_strip_org_parenthetical()` | 19 | 과거 Phase에서 사용 후 제거됨 |

### 2.3 중복 로직

1. **CLOVA OCR API 호출 코드**: `_call_clova_ocr()`과 `_call_clova_ocr_words()`에서 payload 구성 + HTTP 호출 + word 파싱이 거의 동일. (단, `_call_clova_ocr`는 dead code.)

2. **합계 추출**: `_extract_ocr_total_from_words()`와 `_extract_ocr_total()`이 같은 로직을 word-level / line-level에서 각각 수행. (단, `_extract_ocr_total`는 dead code.)

3. **주소 판별**: `_is_address()`, `_ocr_name_has_address()`, `_post_validate()` 내 인라인 keyword count — 3곳에서 유사한 주소 키워드 매칭. 키워드 리스트도 미묘하게 다름:
   - `_is_address`: `_ADDRESS_KEYWORDS` 튜플
   - `_ocr_name_has_address`: `_addr_kws` 로컬 튜플
   - `_post_validate`: 인라인 튜플

4. **`_is_skip_row` 키워드 vs `_FALLBACK_REJECT_KEYWORDS`**: 집계행/메타행 판별 키워드가 여러 곳에 분산.

5. **`_FORM_KEYWORDS`**: `_should_reject_page()`와 `_VLM_REJECT_KEYWORDS`(`_post_validate()` 내부)에 겹치는 키워드 존재.

### 2.4 하드코딩된 값

| 위치 | 값 | 설명 |
|------|-----|------|
| L415 | `POPPLER_PATH = r"C:\poppler\Library\bin"` | Windows 경로 하드코딩. 환경변수화 필요. |
| L521 | `max_pixels=60_000_000` | 매직 넘버. 상수로 추출 가능. |
| L661 | `0.95` | shares deficit 임계값 |
| L663–664 | `n_ocr_rows >= 2` | count deficit 조건 |
| L788 | `face_value ... 0.05` | 허용 오차 |
| L821 | `0.02` | aggregate row 판별 오차 |
| L863 | `0.5` / `>= 2` | cross-page duplicate 임계값 |
| L969 | `median_sc * 100` | fallback 이상치 임계값 |
| L973 | `100_000_000` | 1억 이상 제외 |
| L1670 | `10_000_000_000` | 100억 이상 제외 |

### 2.5 한 함수가 너무 많은 책임을 지는 경우

**`_parse_pipeline_v2`** (L578–924) — 최소 **10가지 책임**:
1. PDF → 이미지 변환
2. CLOVA OCR 호출 + 전처리
3. VLM 호출 (1차)
4. 후검증 (_post_validate)
5. Deficit 감지 + VLM retry (2차)
6. OCR fallback 삽입
7. share_type OCR 보정
8. face_value 보정
9. aggregate row 제거
10. 페이지 reject + cross-page duplicate 감지
11. shareType null 보정
12. 중복 제거
13. V3 fallback

### 2.6 네이밍 이슈

| 현재 | 문제 | 제안 |
|------|------|------|
| `clova_suffix` | "suffix"가 무엇의 suffix인지 불명 | `vlm_ocr_hint` |
| `face_value` | 도메인 용어지만 코드 내 맥락 없이 등장 | `par_value_per_share` 또는 주석 보강 |
| `grp` (L1171) | 축약 | `anchor_group` |
| `sc_words`, `sc2_words`, `sc3_words` | 3-pass가 숫자 suffix로만 구분 | `sc_words_comma`, `sc_words_plain`, `sc_words_embedded` |
| `nt` | `_normalize_share_type` 결과의 약어 | `normalized_type` |
| `best_sc` | "best share count word"인데 축약이 모호 | `primary_sc_word` |
| `fb_flags` | "fb"가 무엇인지 불명 | `fallback_flags` |

---

## 3. 핵심 비즈니스 로직 식별

### 3.1 정확도에 직접 영향을 주는 함수 (regression 고위험)

| 위험도 | 함수 | 이유 |
|--------|------|------|
| 🔴 극고 | `_parse_pipeline_v2` 내 후처리 체인 (L646–870) | 7단계 후처리 순서와 조건이 정확도의 핵심. 순서 변경만으로 regression 가능. |
| 🔴 극고 | `_reconstruct_rows_from_words` | OCR → 구조화 데이터의 유일한 경로. 3-pass 로직, y-clustering, name boundary 계산 모두 민감. |
| 🔴 극고 | `VLM_PROMPT` (L423–486) | Phase 4에서 1단어 변경으로 48→21 regression 확인. **절대 수정 금지.** |
| 🟠 고 | `_extract_via_vlm` | VLM API 호출 파라미터(temperature=0, max_tokens=4096). 변경 시 전체 영향. |
| 🟠 고 | `_post_validate` | 모든 VLM 결과가 거치는 필터. 조건 하나 추가/제거 시 다수 테스트 영향. |
| 🟠 고 | `_build_ocr_suffix` | VLM에 전달되는 OCR 힌트 포맷. 포맷 변경 → VLM 행동 변경. |
| 🟡 중 | `_is_valid_fallback_row` | OCR fallback 삽입 기준. 너무 느슨하면 노이즈, 너무 빡빡하면 누락. |
| 🟡 중 | `_should_reject_page` | 페이지 단위 reject. 임계값 민감. |
| 🟡 중 | `_deduplicate` | 최종 결과의 중복 제거. 로직 버그 시 정상 행 삭제. |

### 3.2 Phase별 추가 로직 분산 위치

| Phase | 추가된 로직 | 위치 (줄) |
|-------|------------|----------|
| Phase 1 | `_clean_name`, `_normalize_share_type`, `_deduplicate` | L161–244 |
| Phase 1 | 기본 VLM 프롬프트 | L423–486 |
| Phase 2 | V3 앙상블 fallback | L910–923 |
| Phase 2 | share_type OCR 보정 | L748–780 |
| Phase 3 | `_strip_org_parenthetical` (현재 dead code) | L140–158 |
| Phase 3 | `_is_valid_fallback_row` 서식 차단 키워드 | L932–988 |
| Phase 3 | face_value 보정 | L786–810 |
| Phase 3 (eval 확대) | `_reconstruct_rows_from_words` 3-pass | L1047–1244 |
| Phase 4 | `_should_reject_page` page scoring | L1590–1615 |
| Phase 4 | cross-page duplicate detection | L849–866 |
| Phase 4 | aggregate row removal | L812–829 |

### 3.3 특히 주의가 필요한 상호 의존성

1. **OCR 합계 → deficit 판단 → retry → fallback 체인**:
   `ocr_total` 값이 deficit 감지(L661), retry 트리거(L665), OCR fallback(L719), aggregate 제거(L825)에 모두 사용됨. `_extract_ocr_total_from_words`의 정확도가 4개 하류 로직에 연쇄 영향.

2. **`_reconstruct_rows_from_words` → `_build_ocr_suffix` → VLM 프롬프트**:
   OCR row 재구성 품질이 VLM 힌트 품질을 결정하고, VLM 힌트가 VLM 출력 품질을 결정. 중간 단계의 미묘한 변경(예: name boundary 계산)이 VLM 결과를 예측 불가하게 변경.

3. **face_value 보정 ↔ aggregate row 제거 순서**:
   face_value 보정(L786)이 aggregate 제거(L812) 전에 실행됨. face_value 보정이 aggregate row의 값을 바꾸면 aggregate 감지에 영향. 현재는 문제없지만 순서 변경 시 위험.

4. **page reject ↔ cross-page duplicate 순서**:
   `_should_reject_page`(L844) 후에 cross-page duplicate(L851). reject된 페이지의 행은 `all_shareholders`에 안 들어가므로 다음 페이지의 duplicate 판단에 영향.

---

## 4. 리팩토링 우선순위 제안

### 4.1 ✅ 안전하게 정리 가능 (로직 변경 없음)

| 우선순위 | 항목 | 예상 효과 | 위험도 |
|---------|------|----------|--------|
| **1** | Dead code 삭제 (6개 함수, ~230줄) | 파일 14% 축소, 혼란 제거 | 거의 없음 |
| **2** | 주소 키워드 리스트 통합 (3곳 → 1개 상수) | 중복 제거, 향후 수정 시 일관성 | 거의 없음 |
| **3** | 매직 넘버를 모듈 상단 상수로 추출 | 가독성 향상, 튜닝 편의 | 거의 없음 |
| **4** | `POPPLER_PATH`를 `os.getenv("POPPLER_PATH", r"C:\poppler\Library\bin")`으로 변경 | 이식성 향상 | 거의 없음 |
| **5** | 변수명 개선 (`nt`→`normalized_type`, `fb_flags`→`fallback_flags` 등) | 가독성 | 거의 없음 |

### 4.2 ⚠️ 주의가 필요한 것 (로직은 동일하나 구조 재배치)

| 우선순위 | 항목 | 예상 효과 | 위험도 |
|---------|------|----------|--------|
| **6** | `_parse_pipeline_v2` 내 후처리 단계를 개별 함수로 추출 | 테스트 가능성 대폭 향상, 가독성 | 중 — 추출 시 변수 전달 누락 위험 |
| **7** | `_reconstruct_rows_from_words`의 3-pass를 각각 함수로 분리 | 가독성, 개별 pass 테스트 가능 | 중 — 공유 상태(sc_words, anchors) 분리 주의 |
| **8** | 후처리 단계 순서를 명시적 파이프라인으로 구조화 | 순서 의존성 문서화 | 중 — 순서가 곧 로직 |

**추출 후보 함수 (4.2-6에서):**
```
_parse_pipeline_v2 내부 → 별도 함수로 추출 가능한 블록:
  - _retry_vlm_if_deficit()       ← L652–701
  - _apply_ocr_fallback()         ← L706–746
  - _correct_share_types()        ← L748–780
  - _correct_face_value()         ← L786–810
  - _remove_aggregate_rows()      ← L812–829
  - _reject_non_shareholder_page() ← L843–866 (reject + duplicate)
  - _correct_null_share_types()   ← L885–895
```

### 4.3 🚫 건드리면 안 되는 것

| 항목 | 이유 |
|------|------|
| **`VLM_PROMPT` 텍스트** | Phase 4에서 1단어 변경으로 48→21 catastrophic regression. 절대 금지. |
| **`_extract_via_vlm` 내 API 파라미터** (temperature, seed, max_tokens, model) | Phase 4에서 seed 변경으로 48→34 regression. |
| **후처리 단계의 실행 순서** | 각 단계가 이전 단계의 결과에 의존. 순서 변경 = 로직 변경. |
| **`_reconstruct_rows_from_words` 내 임계값들** (avg_h * 1.0, 0.75, 0.85 등) | 58개 테스트의 다양한 PDF 레이아웃에 맞춰 튜닝된 값. |
| **`_is_valid_fallback_row`의 10개 검증 규칙** | 각 규칙이 특정 테스트 케이스의 오탐/미탐을 방지. |

---

## 요약

| 지표 | 현황 |
|------|------|
| 총 줄 수 | 1,679 |
| 함수 수 | 32 (6개 dead) |
| 가장 긴 함수 | `_parse_pipeline_v2` (347줄) |
| Dead code | ~230줄 (14%) |
| 안전 리팩토링으로 줄일 수 있는 양 | ~230줄 삭제 + 가독성 대폭 향상 |
| 위험 없이 추출 가능한 함수 수 | 7개 (후처리 단계) |
| 절대 건드리면 안 되는 영역 | VLM 프롬프트, API 파라미터, 후처리 순서, 임계값 |
