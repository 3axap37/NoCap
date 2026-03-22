# Parser V2 전체 분석 리포트

## 1. 전체 요약
- 전체: 58건
- PASS: 45건 (78%)
- FAIL: 13건
- PASS 테스트: Test1, Test2, Test3, Test4, Test5, Test6, Test7, Test8, Test9, Test11, Test12, Test13, Test14, Test16, Test17, Test18, Test19, Test20, Test21, Test22, Test23, Test24, Test25, Test26, Test27, Test29, Test30, Test31, Test33, Test35, Test36, Test38, Test39, Test42, Test43, Test45, Test46, Test50, Test51, Test52, Test53, Test55, Test56, Test57, Test58
- FAIL 테스트: Test10, Test15, Test28, Test32, Test34, Test37, Test40, Test41, Test44, Test47, Test48, Test49, Test54

## 2. 에러 유형별 집계

| 에러 유형 | 발생 건수 | 영향 테스트 수 | 영향 테스트 | 해결 가능성 |
|----------|----------|-------------|-----------|-----------|
| name_corruption | 29건 | 10개 | Test10, Test15, Test32, Test34, Test37, Test40, Test44, Test48, Test49, Test54 | medium |
| name_truncation | 2건 | 2개 | Test10, Test32 | medium |
| share_type_mismatch | 6건 | 2개 | Test10, Test15 | high |
| share_count_mismatch | 8건 | 1개 | Test41 | high |
| row_omission | 21건 | 4개 | Test10, Test15, Test28, Test40 | low |
| row_hallucination | 22건 | 5개 | Test10, Test15, Test28, Test47, Test49 | high |

## 3. FAIL 케이스 상세

### Test10 — FAIL (accuracy: 0%)

- 에러 유형: name_truncation, name_corruption, share_type_mismatch, row_omission, row_hallucination
- 상세:
  - [name_truncation] GT: 김창규(대표이사) / 보통주 / 237,600 → 파서: 김창규 / 보통주 / 237,600
  - [name_corruption] GT: 하나증권(주) / 보통주 / 16,000 → 파서: 포스코파트너스 / 보통주 / 16,000
  - [name_corruption] GT: (주)스마트시티도시개발 / 보통주 / 48,000 → 파서: 하나은행 / 우선주 / 48,000
  - [name_corruption] GT: (주)포커스자산운용 / 보통주 / 16,000 → 파서: 유한회사 / 보통주 / 16,000
  - [share_type_mismatch] GT: (주)스마트시티도시개발 / 보통주 / 48,000 → 파서: 하나은행 / 우선주 / 48,000
  - [row_omission] GT: 박창국(CFO) / 보통주 / 29,200 → 파서: (없음)
  - [row_omission] GT: (주)하나은행 / 보통주 / 32,000 → 파서: (없음)
  - [row_omission] GT: (주)광양에스에이 / 보통주 / 12,000 → 파서: (없음)
  - [row_omission] GT: (주)이노핏파트너스 / 보통주 / 16,000 → 파서: (없음)
  - [row_omission] GT: (주)하늘사랑 / 보통주 / 16,000 → 파서: (없음)
  - [row_omission] GT: 박흥수 / 보통주 / 8,000 → 파서: (없음)
  - [row_hallucination] GT: (없음) → 파서: 하나은행 / 보통주 / 1,600,000
  - [row_hallucination] GT: (없음) → 파서: 스마트도시개발 / 보통주 / 240,000
  - [row_hallucination] GT: (없음) → 파서: 광양씨엠에스 / 보통주 / 80,000
  - [row_hallucination] GT: (없음) → 파서: 포스코자산운용 / 보통주 / 80,000
- 원인 분석: 다중 페이지 PDF에서 VLM/OCR이 비주주 행(서식, 헤더, 주소 등)을 주주로 오인
- 수정 가능성: **medium** — OCR fallback 가드레일 강화

### Test15 — FAIL (accuracy: 0%)

- 에러 유형: name_corruption, share_type_mismatch, row_omission, row_hallucination
- 상세:
  - [name_corruption] GT: 박상혁 / 보통주 / 300,000 → 파서: 박혁(HYUK PARK) / 보통주 / 300,000
  - [name_corruption] GT: 엠에스티원라이프스타일펀드 / 우선주 / 7,875 → 파서: 유안타증권(주) / 보통주 / 7,875
  - [name_corruption] GT: 이지홍 / 우선주 / 3,938 → 파서: 메리츠증권(주) / 보통주 / 3,938
  - [name_corruption] GT: 송재화 / 우선주 / 7,875 → 파서: 이재용 / 보통주 / 7,875
  - [name_corruption] GT: 강동석 / 우선주 / 3,938 → 파서: 송호창 / 보통주 / 3,938
  - [name_corruption] GT: 권병민 / 우선주 / 1,969 → 파서: 데일리 골든아워 바이오 헬스케어 펀드3호 / 보통주 / 1,969
  - [share_type_mismatch] GT: 엠에스티원라이프스타일펀드 / 우선주 / 7,875 → 파서: 유안타증권(주) / 보통주 / 7,875
  - [share_type_mismatch] GT: 이지홍 / 우선주 / 3,938 → 파서: 메리츠증권(주) / 보통주 / 3,938
  - [share_type_mismatch] GT: 송재화 / 우선주 / 7,875 → 파서: 이재용 / 보통주 / 7,875
  - [share_type_mismatch] GT: 강동석 / 우선주 / 3,938 → 파서: 송호창 / 보통주 / 3,938
  - [share_type_mismatch] GT: 권병민 / 우선주 / 1,969 → 파서: 데일리 골든아워 바이오 헬스케어 펀드3호 / 보통주 / 1,969
  - [row_omission] GT: 한투바른동행셰르파제1호펀드 / 우선주 / 15,750 → 파서: (없음)
  - [row_omission] GT: 이재윤 / 우선주 / 1,969 → 파서: (없음)
  - [row_omission] GT: 디에이치피(DHP)개인투자조합제6호 / 우선주 / 7,154 → 파서: (없음)
  - [row_omission] GT: 에스브이아이씨 [57]호 신기술사업투자조합 / 우선주 / 38,961 → 파서: (없음)
  - [row_hallucination] GT: (없음) → 파서: 한국투자증권(주) / 보통주 / 157,500
  - [row_hallucination] GT: (없음) → 파서: 크립톤-엔젤링크 7호 개인투자조합 / 보통주 / 1,754
  - [row_hallucination] GT: (없음) → 파서: 557, 60, 역삼로 주소 태봉로 (우면동,황금빌딩) / (null) / 172
- 원인 분석: 다중 페이지 PDF에서 VLM/OCR이 비주주 행(서식, 헤더, 주소 등)을 주주로 오인
- 수정 가능성: **medium** — OCR fallback 가드레일 강화

### Test28 — FAIL (accuracy: 0%)

- 에러 유형: row_omission, row_hallucination
- 상세:
  - [row_omission] GT: 김현태 / 보통주 / 152,000 → 파서: (없음)
  - [row_omission] GT: 김현태 / 우선주 / 1,010 → 파서: (없음)
  - [row_omission] GT: 김윤석 / 보통주 / 40,000 → 파서: (없음)
  - [row_omission] GT: 김윤석 / 우선주 / 1,010 → 파서: (없음)
  - [row_omission] GT: 미래지주-IBKVC 딥테크 제1호 투자조합 / 우선주 / 20,203 → 파서: (없음)
  - [row_omission] GT: 하나테크밸류업펀드 2호 / 우선주 / 20,202 → 파서: (없음)
  - [row_omission] GT: 블루포인트 2022 개인투자조합 / 우선주 / 17,777 → 파서: (없음)
  - [row_omission] GT: 한투 바른동행 셰르파 제4호 펀드 / 우선주 / 10,102 → 파서: (없음)
  - [row_omission] GT: (주)엔딕 / 보통주 / 8,000 → 파서: (없음)
  - [row_omission] GT: (주)블루포인트파트너스 / 우선주 / 4,445 → 파서: (없음)
  - [row_hallucination] GT: (없음) → 파서: 딥테크제1호투자조합 / (null) / 32
- 원인 분석: VLM이 표의 일부 주주를 누락
- 수정 가능성: low — VLM 근본 한계

### Test32 — FAIL (accuracy: 71%)

- 에러 유형: name_truncation, name_corruption
- 상세:
  - [name_truncation] GT: 인터밸류 5호 Next Unicorn 청년창업 투자조합 / 우선주 / 53 → 파서: 인터밸류 5호 Next Unicorn / 우선주 / 53
  - [name_corruption] GT: 신한-씨제이 기술혁신펀드 제1호 / 우선주 / 53 → 파서: 청년창업 투자조합 신한-씨제이 기술혁신펀드 제1호 / 우선주 / 53
- 원인 분석: VLM 한글 오독 또는 OCR 이름 오류
- 수정 가능성: medium — OCR-VLM 이름 교차 검증 가능성

### Test34 — FAIL (accuracy: 91%)

- 에러 유형: name_corruption
- 상세:
  - [name_corruption] GT: 부산지역혁신 티브스 투자조합 1호 / 우선주 / 2,143 → 파서: 부산지역혁신 텀스 투자조합 1호 / 우선주 / 2,143
- 원인 분석: VLM 한글 오독 또는 OCR 이름 오류
- 수정 가능성: medium — OCR-VLM 이름 교차 검증 가능성

### Test37 — FAIL (accuracy: 60%)

- 에러 유형: name_corruption
- 상세:
  - [name_corruption] GT: 한투 바른동행 셰르파 제3호펀드 / 우선주 / 600 → 파서: 한투 바른동행 세트3호펀드 / 우선주 / 600
  - [name_corruption] GT: 스마일게이트 로켓부스터3호 / 우선주 / 600 → 파서: 스마일게이트 로켓3호 / 우선주 / 600
- 원인 분석: VLM 한글 오독 또는 OCR 이름 오류
- 수정 가능성: medium — OCR-VLM 이름 교차 검증 가능성

### Test40 — FAIL (accuracy: 89%)

- 에러 유형: name_corruption, row_omission
- 상세:
  - [name_corruption] GT: Dong wuk Kim / 보통주 / 50 → 파서: 조인식 / 보통주 / 50
  - [row_omission] GT: 조인식 / 우선주 / 3 → 파서: (없음)
- 원인 분석: VLM 한글 오독 또는 OCR 이름 오류
- 수정 가능성: medium — OCR-VLM 이름 교차 검증 가능성

### Test41 — FAIL (accuracy: 0%)

- 에러 유형: share_count_mismatch
- 상세:
  - [share_count_mismatch] GT: 전예찬 / 보통주 / 2,758 → 파서: 전예찬 / 보통주 / 2,758,000
  - [share_count_mismatch] GT: 포항공과대학교 / 보통주 / 150 → 파서: 포항공과대학교 / 보통주 / 150,000
  - [share_count_mismatch] GT: 조태일 / 보통주 / 60 → 파서: 조태일 / 보통주 / 60,000
  - [share_count_mismatch] GT: 한투바른동행셰르파제1호펀드 / 보통주 / 75 → 파서: 한투바른동행셰르파제1호펀드 / 보통주 / 75,000
  - [share_count_mismatch] GT: 한투바른동행셰르파제2호펀드 / 우선주 / 114 → 파서: 한투바른동행셰르파제2호펀드 / 우선주 / 114,000
  - [share_count_mismatch] GT: 스파크랩코리아 액셀러레이터 제4호 투자조합 / 우선주 / 150 → 파서: 스파크랩코리아 액셀러레이터 제4호 투자조합 / 우선주 / 150,000
  - [share_count_mismatch] GT: 스마트 스파크랩 클라우드 제1호펀드 / 우선주 / 190 → 파서: 스마트 스파크랩 클라우드 제1호펀드 / 우선주 / 190,000
  - [share_count_mismatch] GT: 김영인 / 보통주 / 32 → 파서: 김영인 / 보통주 / 32,000
- 원인 분석: VLM이 금액 컬럼을 주식수로 오독 (일괄 1000배). 액면가 보정 로직 미적용 케이스
- 수정 가능성: **high** — 액면가 감지 로직 개선

### Test44 — FAIL (accuracy: 25%)

- 에러 유형: name_corruption
- 상세:
  - [name_corruption] GT: 하나 ESG 더블 임팩트 매칭벤처투자조합 1호 / 우선주 / 714 → 파서: 하나 ESG 더블 임팩트 매칭벤처투자조합 1호 (재단법인 한국사회투자) / 우선주 / 714
  - [name_corruption] GT: 한투 바른동행 셰르파 제3호 펀드 / 우선주 / 2,143 → 파서: 한투 바른동행 제로마 제3호 펀드 (한국투자액셀러레이터 주식회사) / 우선주 / 2,143
  - [name_corruption] GT: 충북 창업 노마드 혁신펀드 / 우선주 / 714 → 파서: 충북 창업 노마드 혁신펀드 (충북창조경제혁신센터) / 우선주 / 714
- 원인 분석: VLM이 업무집행조합원 정보를 괄호로 이름에 포함. GT는 제외
- 수정 가능성: **high** — 괄호 내 업무집행조합원 정보 제거 후처리

### Test47 — FAIL (accuracy: 100%)

- 에러 유형: row_hallucination
- 상세:
  - [row_hallucination] GT: (없음) → 파서: 위 주주명부는 상호: 에이트스튜디오 / (null) / 31
- 원인 분석: 복합 에러
- 수정 가능성: medium

### Test48 — FAIL (accuracy: 33%)

- 에러 유형: name_corruption
- 상세:
  - [name_corruption] GT: 한투 바른동행 셰르파 제1호 펀드 / 우선주 / 7,986 → 파서: 한투 바른동행 셰르파 제1호 펀드(업무집행조합원 한국투자액셀러레이터 주식회사) / 우선주 / 7,986
  - [name_corruption] GT: 한국투자 Re-Up II 펀드 / 우선주 / 15,972 → 파서: 한국투자 Re-Up II펀드(업무집행조합원 한국투자파트너스 주식회사) / 우선주 / 15,972
  - [name_corruption] GT: 한국투자 Re-Up II 펀드 / 우선주 / 16,863 → 파서: 한국투자 Re-Up II펀드(업무집행조합원 한국투자파트너스 주식회사) / 우선주 / 16,863
  - [name_corruption] GT: 더케이아이 그로잉 스타 7호 투자조합 / 우선주 / 12,648 → 파서: 디케이아이 그로잉 스타 7호 투자조합(업무집행조합원 (주)대교인베스트먼트) / 우선주 / 12,648
  - [name_corruption] GT: 고려대-포스코 기술혁신 스케일업 벤처투자조합 제1호 / 우선주 / 4,216 → 파서: 고려대-포스코 기술혁신 스케일업 벤처투자조합 제1호(업무집행조합원 고려대학교기술지주 주식회사) / 우선주 / 4,216
  - [name_corruption] GT: 한투 바른동행 셰르파 제2호 펀드 / 우선주 / 4,216 → 파서: 한투 바른동행 셰르파 제2호 펀드(업무집행조합원 한국투자액셀러레이터 주식회사) / 우선주 / 4,216
  - [name_corruption] GT: 대웅인베스트먼트 바이오투자조합 1호 / 우선주 / 8,431 → 파서: 대웅인베스트먼트 바이오투자조합 1호(업무집행조합원 주식회사 대웅인베스트먼트) / 우선주 / 8,431
  - [name_corruption] GT: 차세대 지역뉴딜&바이오 투자조합 / 우선주 / 8,431 → 파서: 차세대 지역뉴딜&바이오 투자조합(업무집행조합원 주식회사 경남벤처투자) / 우선주 / 8,431
  - [name_corruption] GT: 에스유피(SUP)-유니콘육성투자조합 / 우선주 / 2,108 → 파서: 에스유피(SUP)-유니콘육성투자조합(업무집행조합원 유한책임회사 스케일업파트너스) / 우선주 / 2,108
  - [name_corruption] GT: 에스유피(SUP)-3호 벤처투자조합 / 우선주 / 2,108 → 파서: 에스유피(SUP)-3호 벤처투자조합(업무집행조합원 유한책임회사 스케일업파트너스) / 우선주 / 2,108
- 원인 분석: VLM이 업무집행조합원 정보를 괄호로 이름에 포함. GT는 제외
- 수정 가능성: **high** — 괄호 내 업무집행조합원 정보 제거 후처리

### Test49 — FAIL (accuracy: 89%)

- 에러 유형: name_corruption, row_hallucination
- 상세:
  - [name_corruption] GT: ㈜씨이텍(자기주식) / 보통주 / 102 → 파서: (주)씨이텍 / 보통주 / 102
  - [row_hallucination] GT: (없음) → 파서: 주식회사 씨이텍 / 보통주 / 10,200
  - [row_hallucination] GT: (없음) → 파서: 주식회사 씨이텍 / 우선주 / 765
  - [row_hallucination] GT: (없음) → 파서: 김해련 / 보통주 / 714
  - [row_hallucination] GT: (없음) → 파서: 안다현 / 보통주 / 102
  - [row_hallucination] GT: (없음) → 파서: 일련 20 21 22 23 19 주민등록번호 거주 거주지 구분 (법인명) ( 사업자번호) 지국 국코드 ( 출자좌수) / (null) / 41
  - [row_hallucination] GT: (없음) → 파서: 「법인세법」 제60조 및제 |119조, 같은 법 시행령 제97조 · 제 161조에 / (null) / 2,025
  - [row_hallucination] GT: (없음) → 파서: 유정균 / (null) / 510
  - [row_hallucination] GT: (없음) → 파서: 이광순 / (null) / 3,570
  - [row_hallucination] GT: (없음) → 파서: 이윤제 / (null) / 3,060
  - [row_hallucination] GT: (없음) → 파서: 한투바른동행세르과제2호펀드 / (null) / 765
  - [row_hallucination] GT: (없음) → 파서: 법인세법 시행규칙 [ 별지 제54호서식]<개정2016.3.7.> 관리번호 주식등변동상황명세서 1법인명 (주)씨이텍 2사업자등록번호 4상장변경일 5합병.분할일 / (null) / 318
  - [row_hallucination] GT: (없음) → 파서: 7주권상장여부 3. 비상장 8무액면주식발행여부 2. 부 변동상황(주 식수주주 · 기초 출자자 18 증가주식 수(출자 좌 수) / (null) / 42
  - [row_hallucination] GT: (없음) → 파서: 일련번호 19 20 21 22 23 24 25 26 27 28 29 30 31전환 32명의 주민등록번호 거주 거주지 사채 등 신탁 등 구분 국코드 양수 유상증자 무상증자 상속 증여 출자전환 기타 (법인명) ( 사업자번호) 지국 (출자좌수) 실명전환 / (null) / 41
- 원인 분석: 다중 페이지 PDF에서 VLM/OCR이 비주주 행(서식, 헤더, 주소 등)을 주주로 오인
- 수정 가능성: **medium** — OCR fallback 가드레일 강화

### Test54 — FAIL (accuracy: 86%)

- 에러 유형: name_corruption
- 상세:
  - [name_corruption] GT: 씨엔티테크 제 13 호 농식품 투자조합 / 우선주 / 1,867 → 파서: 씨엔티테크 제 13 호 농식품 투자조합(씨엔티테크 주식회사) / 우선주 / 1,867
- 원인 분석: VLM이 업무집행조합원 정보를 괄호로 이름에 포함. GT는 제외
- 수정 가능성: **high** — 괄호 내 업무집행조합원 정보 제거 후처리

## 4. 개선 우선순위 제안

### Priority 1: 괄호 내 업무집행조합원/사업자번호 정보 제거 [규칙 기반]
- 대상: Test44, Test48, Test54
- 예상 효과: **+3 PASS**
- 구현 난이도: **low**
- 접근 방법: `_clean_name()`에 `(업무집행조합원 ...)`, `(재단법인 ... NNN-NNNNNNN)`, `(충북창조경제혁신센터)` 등 괄호 내 부가정보 제거. 패턴: 펀드명 뒤 `(조합원/기관명 + 선택적 사업자번호)` 형태를 정규식으로 제거.
- 비고: Test1~36에서는 이 패턴이 없었으나 Test37~59에서 새로 등장. **overfit 아닌 신규 패턴.**

### Priority 2: 액면가 보정 로직 확장 [규칙 기반]
- 대상: Test41
- 예상 효과: **+1 PASS**
- 구현 난이도: **medium**
- 접근 방법: Test41은 1,000배 차이 (GT: 2,758 vs 파서: 2,758,000). 기존 `_detect_face_value()`는 OCR에서 face value를 감지하는데, Test41에서는 face value가 1,000원이고 OCR 감지가 안 되는 케이스. OCR word에서 "1,000" 패턴도 face value 후보로 검토 필요.

### Priority 3: 다중 페이지 hallucination 가드레일 강화 [규칙 기반]
- 대상: Test47, Test49
- 예상 효과: **+2 PASS**
- 구현 난이도: **medium**
- 접근 방법:
  - Test47: OCR fallback이 "위 주주명부는 상호: ..." (서명 행)을 삽입. `_is_valid_fallback_row()`에 "주주명부" 키워드 추가.
  - Test49: 다중 페이지 PDF에서 2페이지(법인세법 서식)의 데이터가 전부 유입. 페이지별 VLM 결과에 shareType이 없는 행이 다수면 해당 페이지 결과 전체 무시 로직 검토. OCR fallback에서 "법인세법", "시행규칙", "별지" 등 법률 서식 키워드 차단.

### Priority 4: 소규모 이름 오독 (1-2건 에러) [VLM/앙상블]
- 대상: Test32, Test34, Test37, Test40
- 예상 효과: +1~4 PASS (개별 수정 가능성에 따라)
- 구현 난이도: **medium~high**
- 접근 방법:
  - Test32: VLM이 다중줄 펀드명을 잘못 분할 (비결정적 — 때때로 PASS). VLM 재시도 또는 OCR 이름 교차 검증.
  - Test34: VLM 한글 1글자 오독 ("티브스"→"텀스"). 규칙으로 해결 불가.
  - Test37: VLM이 "셰르파"→"세트3", "로켓부스터"→"로켓" 오독. 규칙으로 해결 불가.
  - Test40: VLM이 "Dong wuk Kim"을 "조인식"으로 오독. GT 검수 필요 (PDF 확인).

### Priority 5: 복잡한 표 구조 / VLM 근본 한계 [아키텍처 변경]
- 대상: Test10, Test15, Test28
- 예상 효과: 불확실
- 구현 난이도: **high**
- 접근 방법: 이들은 accuracy 0%로 VLM이 표 전체를 오독. 표 영역 사전 분할(crop), 다중 VLM 호출, 또는 완전히 다른 파싱 전략 필요.

## 5. 해결 불가 케이스 (현재 아키텍처)

| 테스트 | accuracy | 핵심 문제 | 이유 |
|--------|----------|----------|------|
| Test10 | 0% | VLM 표 구조 전면 오독 | 복잡한 다단 레이아웃, VLM이 행 매핑 실패 |
| Test15 | 0% | VLM 이름/유형 전면 오독 | VLM이 다른 페이지의 데이터와 혼동 |
| Test28 | 0% | VLM 표 구조 전면 오독 | 복잡한 보통주+우선주 혼합 표, 전체 누락 |

이 3건은 VLM의 vision 인식 근본 한계로, 후처리 규칙이나 프롬프트 수정으로는 해결이 어려움. 표 영역 crop 분할 또는 별도 파서 아키텍처가 필요.

## 6. Test1~36 vs Test37~59 비교 (overfit 분석)

| 구간 | 전체 | PASS | PASS율 | 주요 FAIL 원인 |
|------|------|------|--------|---------------|
| Test1~36 | 36 | 31 | 86% | VLM 구조 오독(3), VLM 이름 오독(2) |
| Test37~59 | 22 | 14 | 64% | 괄호 부가정보(3), 액면가(1), hallucination(2), VLM 오독(3) |

**신규 패턴 발견:**
1. **괄호 내 업무집행조합원 정보** (Test44, 48, 54): Test1~36에서는 없었던 신규 패턴. 규칙 추가로 해결 가능.
2. **법인세법 서식 페이지 유입** (Test49): 다중 페이지 PDF에서 비주주명부 페이지가 포함된 신규 케이스.
3. **1,000배 액면가** (Test41): 기존 500배(Test35)와 다른 배율. 감지 로직 확장 필요.

**기존 패턴 재등장:**
- VLM 이름 오독 (Test37, 40): Phase 1~2에서도 해결 불가였던 유형. overfit 아닌 근본 한계.
- OCR fallback hallucination (Test47): Phase 1에서 가드레일 추가했으나 "주주명부" 키워드는 미포함.
