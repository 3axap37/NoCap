# Shareholder PDF Parser — Autonomous Improvement Protocol (Phase 5 / V2.3)

## Project Overview
주주명부 PDF에서 주주명, 주식종류, 주식수를 추출하는 파서.
V2 파이프라인(CLOVA OCR + GPT-4o VLM)의 정확도를 eval-driven으로 개선한다.

## Project Structure
```
C:\W\Coding\PjtKai\
├── backend/
│   ├── pdf_parser_v2.py        ← 주요 수정 대상
│   ├── pdf_parser_v3.py        ← V3 (앙상블 fallback)
│   ├── models.py
│   └── parser_types.py
├── eval/
│   ├── run_eval.py             ← eval 실행
│   ├── ground_truth.jsonl      ← 정답 데이터 (58건)
│   ├── improvement_log.md      ← 개선 기록 (반드시 업데이트)
│   └── pdfs/
│       └── Test1.pdf ~ Test59.pdf
```

## Eval Execution
```bash
cd C:\W\Coding\PjtKai\eval
python run_eval.py
```
- 58건 테스트
- Phase 4 최종: **48/58 PASS (83%)**
- Phase 5 목표: **49~50/58 PASS (84~86%)**
- 이번이 규칙/routing 기반 개선의 마지막 Phase. 이후는 운영 투입 + 아키텍처 변경.

---

## 📍 Phase 5 Context

### 어디까지 왔는가
| Phase | 결과 | 주요 기법 |
|-------|------|----------|
| Phase 1 | 23→29/36 | 규칙 기반 후처리 |
| Phase 2 | 29→31/36 | shareType 보정, V3 앙상블 |
| eval 확대 | 36→58건 | 45/58 baseline |
| Phase 3 | 45→47/58 | 괄호 제거, 서식 차단, 액면가 확장 |
| Phase 4 | 47→48/58 | page scoring, seed/prompt 실험 (실패→revert) |

### Phase 4에서 확인된 금기 사항
- **❌ VLM seed 파라미터 변경**: 48→34 치명적 regression. vision 모델에서 seed는 품질을 바꿈.
- **❌ VLM 프롬프트 전역 수정 (OCR 신뢰도 강조)**: 48→21 치명적 regression. VLM의 이미지 인식 능력 파괴.
- **❌ 전역 프롬프트 튜닝 전반**: 작은 문구 변경도 전체 테스트에 파급. 절대 하지 않는다.

### 남은 FAIL 분류

**Reachable (이번 Phase에서 노릴 것) — 2~3건:**
| Test | accuracy | 핵심 문제 | 접근 |
|------|----------|----------|------|
| Test49 | 89% | VLM Page 1 비결정성 + Page 2/3 서식 유입 | page routing 미세 조정 |
| Test32 | 71% | VLM 비결정성, 다중줄 펀드명 분할 | multi-shot best-of-N |
| Test43 | 비결정적 | VLM 비결정성 | multi-shot best-of-N |

**Residual (코드로 해결 불가) — 4건:**
| Test | 핵심 문제 |
|------|----------|
| Test34 | VLM 한글 1글자 오독 "티브스"→"텀스" |
| Test37 | VLM 이름 오독 "셰르파"→"세트3" |
| Test40 | VLM 이름 오독 + GT 검수 필요 |
| Test44 | VLM 이름 오독 "셰르파"→"제르마" |

**Architecture Change (Phase 6 이월) — 4건:**
| Test | 핵심 문제 |
|------|----------|
| Test10 | VLM 표 구조 전면 오독 (accuracy 0%) |
| Test15 | VLM 다중 페이지 데이터 혼동 (accuracy 0%) |
| Test28 | VLM 복합 표 전체 누락 (accuracy 0%) |
| Test58 | 36명 대규모 표, VLM 매핑 오류 |

---

## 📋 Task Queue

### Task 1: Test49 page routing 미세 조정 [medium risk, +0~1 PASS]

**현황**: Phase 4에서 `_should_reject_page()` + cross-page duplicate detection을 넣었음.
Page 2(중복 reject)와 Page 3(서식 키워드 reject)은 성공했으나,
VLM이 Page 1에서도 비결정적으로 extra rows를 생성하는 경우가 있어 불안정.

**추가 조정 방향**:

1. Page 1 결과에서 **OCR 합계 총계와의 괴리** 체크:
   - OCR에서 감지한 합계(ocr_total) 대비, 추출된 주식수 합이 120% 초과하면
     가장 합계와 동떨어진 행들을 의심 → 제거 후보로 마킹
   
2. Page 1 결과에서 **다른 페이지 소속 행** 감지:
   - 같은 PDF의 다른 페이지 GT와 이름이 겹치는 행이 있으면 cross-page leakage
   - 이건 GT 없이도 가능: 같은 이름이 여러 페이지 결과에 등장하면 중복 제거

3. **VLM이 같은 주주를 이름만 다르게 2번 추출**하는 패턴 감지:
   - 주식수가 동일한 행이 여러 개 있고 이름만 다르면 의심

**구현 위치**: `_parse_pipeline_v2()` 내 post-processing

**주의**: 
- Test49는 VLM 비결정성이 강해서 1회 eval로 PASS 판정하지 말 것
- 3회 실행하여 2회 이상 PASS여야 "안정" 판정

**regression 체크**: 
- Test47 (Phase 3에서 해결) 유지
- Test6, Test7, Test27, Test31 유지
- 전체 48개 PASS 유지

---

### Task 2: Multi-shot best-of-N for 비결정적 테스트 [low risk, +0~2 PASS]

**대상**: Test32, Test43 (VLM 비결정성으로 PASS/FAIL 변동)

**가설**: VLM을 같은 페이지에 대해 2~3회 호출하고,
가장 품질 좋은 결과를 채택하면 비결정적 테스트가 안정적으로 PASS될 수 있음.

**"best" 결과 선택 기준** (우선순위 순):
1. **OCR 합계와 가장 가까운 주식수 합** — OCR이 감지한 합계 총계에 근접할수록 good
2. **주주 수가 OCR 감지 행 수와 가장 가까운 것** — 누락/초과 최소화
3. **위 두 기준이 동률이면 주주 수가 가장 많은 것** — 누락보다 과포함이 나음

**구현**:
```python
def _extract_via_vlm_best_of_n(
    image_bytes, page_num, clova_text, n_trials=2, ocr_total=None, n_ocr_rows=0
):
    """VLM을 n_trials회 호출하고 best result를 반환."""
    results = []
    for _ in range(n_trials):
        candidates = _extract_via_vlm(image_bytes, page_num, clova_text)
        if candidates is not None:
            results.append(candidates)
    
    if not results:
        return None
    if len(results) == 1:
        return results[0]
    
    # Score each result
    def _score(candidates):
        total = sum(rc.share_count or 0 for rc in candidates)
        count = len(candidates)
        
        # OCR 합계와의 근접도 (가까울수록 좋음, 0이 최선)
        sum_gap = abs(total - ocr_total) if ocr_total else 0
        # OCR 행 수와의 근접도
        count_gap = abs(count - n_ocr_rows) if n_ocr_rows else 0
        
        # 낮을수록 좋음
        return (sum_gap, count_gap, -count)
    
    results.sort(key=_score)
    return results[0]
```

**적용 조건** — 무조건 multi-shot하면 API 비용이 2~3배:
- **기본값은 1회 호출** (기존과 동일)
- 아래 조건 중 하나를 만족하면 2회 호출:
  - 문서 전체 주주 수가 5명 이상 (복잡한 문서)
  - OCR 감지 행 수와 VLM 추출 수의 차이가 2 이상
  - 이전 retry에서 이미 불일치가 감지된 경우

**⚠️ 비용 관리**:
- n_trials=2로 시작 (비용 2배)
- n_trials=3은 +2 PASS 이상 효과가 확인된 후에만
- 단순 문서(주주 1~3명)는 multi-shot 하지 않음

**regression 체크**:
- multi-shot은 best result를 선택하므로, 기존 1회 호출보다 나빠질 가능성은 낮음
- 하지만 반드시 전체 eval로 확인
- API 비용 증가분 모니터링

---

## ⚠️ Guard Rails

1. **Regression 절대 불허**: 현재 PASS 48개 전수 확인.

2. **한 번에 한 Task만**: Task 1 → eval → 확인 → Task 2.

3. **VLM 전역 변경 금지**: 
   - seed 변경 ❌
   - VLM_PROMPT 전역 수정 ❌
   - temperature 변경 ❌
   - 이 세 가지는 Phase 4에서 치명적 regression 확인됨. 절대 재시도하지 않는다.

4. **비결정적 테스트는 3회 실행**:
   - Test32, Test43, Test49는 1회 결과로 판단하지 않음
   - 3회 중 2회 이상 PASS여야 "안정" 판정

5. **API 비용 모니터링**:
   - multi-shot 도입 시 eval 1회당 API 호출 증가분 확인
   - 비용이 과도하면 적용 조건을 더 제한적으로 조정

6. **모든 변경을 improvement_log.md에 기록**.

---

## 📊 Logging Template

```markdown
## Iteration N: [한 줄 설명]
- **가설**: 
- **변경**: 
- **기대 효과**: 
- **실제 결과**:
  - PASS: NN/58 → NN/58 (+N)
  - Fixed: TestX, TestY
  - Regressed: 없음 / TestZ
- **Error class impact**:
  - [track명]: N건 → N건
- **Risk**: low/medium/high
- **판단**: keep / revert / partial keep
- **메모**: 다음 실험에 주는 시사점
```

---

## 📊 Current PASS List (48/58 — 반드시 유지)

Test1, Test2, Test3, Test4, Test5, Test6, Test7, Test8, Test9,
Test11, Test12, Test13, Test14, Test16, Test17, Test18, Test19,
Test20, Test21, Test22, Test23, Test24, Test25, Test26, Test27,
Test29, Test30, Test31, Test33, Test35, Test36,
Test38, Test39, Test41, Test42, Test45, Test46, Test47,
Test48, Test50, Test51, Test52, Test53, Test54, Test55, Test56, Test57

## FAIL (10건)

| 분류 | 테스트 | Phase 5 Task |
|------|--------|-------------|
| Reachable | Test49 | Task 1 (page routing) |
| Reachable | Test32, Test43 | Task 2 (multi-shot) |
| Residual | Test34, Test37, Test40, Test44 | 해결 불가 |
| Architecture | Test10, Test15, Test28, Test58 | Phase 6 |

---

## 🏁 Phase 5 종료 후

이번 Phase가 끝나면:
1. **최종 PASS율 기록** + Reachable/Residual/Architecture 최종 분류
2. **운영 투입**: 자동 추출 → 사람 검수 워크플로우로 실무 적용
3. **새 실패 패턴 수집**: 운영 중 발견되는 신규 PDF 유형 → eval set 추가
4. **Phase 6 로드맵**: table crop, region split, OCR anchor reconstruction 설계