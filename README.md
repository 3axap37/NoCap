# Cap Table Generator

주주명부 PDF를 업로드하고 투자 정보를 입력하면 `CapTableExample.xlsx`와 동일한 형식의 Cap Table Excel 파일을 생성합니다.

## 실행 방법

### 1. 백엔드 (FastAPI)

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

서버가 `http://localhost:8000`에서 실행됩니다.

### 2. 프론트엔드 (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:5173`을 열면 됩니다.

## 사용 방법

1. **Step 1**: 주주명부 PDF를 드래그하거나 클릭하여 업로드 → "PDF 파싱" 클릭
2. **Step 2**: 파싱된 주주 목록 확인/수정, 기업명 / 라운드 / Pre-money 입력
3. **Step 3**: 리드 투자자 투자금액 입력, 공동 투자자 추가(선택)
4. **Step 4**: "Cap Table 다운로드" 클릭 → `cap_table.xlsx` 저장

## 구조

```
PjtKai/
├── backend/
│   ├── main.py               # FastAPI 앱 (2개 엔드포인트)
│   ├── pdf_parser.py         # pdfplumber 기반 주주명부 파싱
│   ├── excel_generator.py    # openpyxl로 CapTableExample.xlsx 포맷 복제
│   ├── models.py             # Pydantic 모델
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.tsx           # 4-step 플로우
│   │   ├── api.ts            # fetch 래퍼
│   │   └── components/       # 각 스텝별 컴포넌트
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts        # /api → localhost:8000 프록시
└── CapTableExample.xlsx      # 참조 파일 (수정 금지)
```

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/parse-pdf` | PDF → 주주 목록 JSON |
| POST | `/api/generate-excel` | 투자 정보 → Cap Table .xlsx |
