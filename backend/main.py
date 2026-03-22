from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from excel_generator import generate_excel
from models import GenerateExcelRequest, ParsePdfResponse
from pdf_parser_v2 import parse_shareholders_from_pdf

app = FastAPI(title="Cap Table API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/parse-pdf", response_model=ParsePdfResponse)
async def parse_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일을 업로드해 주세요.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    try:
        shareholders, warning = parse_shareholders_from_pdf(content)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"PDF 파싱 중 오류가 발생했습니다: {exc}",
        )

    return ParsePdfResponse(shareholders=shareholders, parseWarning=warning)


@app.post("/api/generate-excel")
async def generate_excel_endpoint(req: GenerateExcelRequest):
    if not req.shareholders:
        raise HTTPException(status_code=400, detail="주주 목록이 비어 있습니다.")
    if req.preMoney <= 0:
        raise HTTPException(status_code=400, detail="투자 전 기업 가치를 입력해 주세요.")
    if req.leadInvestorAmount <= 0:
        raise HTTPException(status_code=400, detail="리드 투자자 투자금액을 입력해 주세요.")

    try:
        xlsx_bytes = generate_excel(req)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"엑셀 생성 중 오류가 발생했습니다: {exc}",
        )

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="cap_table.xlsx"'},
    )
