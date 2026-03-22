import os
import uuid
import time
import threading
from fastapi import FastAPI, File, HTTPException, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from excel_generator import generate_excel
from models import GenerateExcelRequest, JobCreatedResponse, JobStatusResponse
from pdf_parser_v2 import parse_shareholders_from_pdf

app = FastAPI(title="Cap Table API")

# --- CORS (environment-variable driven) ---
_allowed_raw = os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
_origins = [o.strip() for o in _allowed_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory job store ---
_jobs: dict[str, dict] = {}
_JOB_TTL_SECONDS = 30 * 60  # 30 minutes


def _cleanup_old_jobs() -> None:
    """Remove jobs older than TTL."""
    now = time.time()
    expired = [jid for jid, j in _jobs.items() if now - j.get("created", 0) > _JOB_TTL_SECONDS]
    for jid in expired:
        _jobs.pop(jid, None)


def _run_parse(job_id: str, content: bytes) -> None:
    """Background task: run PDF parsing and store result."""
    try:
        shareholders, warning = parse_shareholders_from_pdf(content)
        _jobs[job_id].update({
            "status": "completed",
            "shareholders": [sh.dict() for sh in shareholders],
            "parseWarning": warning,
        })
    except Exception as e:
        _jobs[job_id].update({
            "status": "failed",
            "error": str(e),
        })


# --- Endpoints ---


@app.post("/api/parse-pdf", response_model=JobCreatedResponse)
async def parse_pdf(file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일을 업로드해 주세요.")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    # Cleanup old jobs periodically
    _cleanup_old_jobs()

    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "processing", "created": time.time()}
    background_tasks.add_task(_run_parse, job_id, content)

    return JobCreatedResponse(jobId=job_id)


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
async def get_status(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs[job_id]
    return JobStatusResponse(
        status=job["status"],
        shareholders=job.get("shareholders"),
        parseWarning=job.get("parseWarning"),
        error=job.get("error"),
    )


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
