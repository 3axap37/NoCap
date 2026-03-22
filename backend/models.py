from pydantic import BaseModel
from typing import Optional


class Shareholder(BaseModel):
    name: str
    shareType: str
    shareCount: int


class CoInvestor(BaseModel):
    name: str
    amount: int
    shareType: str = "RCPS"


class ParsePdfResponse(BaseModel):
    shareholders: list[Shareholder]
    parseWarning: Optional[str] = None


class GenerateExcelRequest(BaseModel):
    companyName: str
    round: str
    preMoney: int
    shareholders: list[Shareholder]
    leadInvestorName: str
    leadInvestorAmount: int
    leadInvestorShareType: str = "RCPS"
    coInvestors: list[CoInvestor] = []


# --- Async job models ---


class JobCreatedResponse(BaseModel):
    jobId: str


class JobStatusResponse(BaseModel):
    status: str  # "processing" | "completed" | "failed"
    shareholders: Optional[list[Shareholder]] = None
    parseWarning: Optional[str] = None
    error: Optional[str] = None
