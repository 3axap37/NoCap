from pydantic import BaseModel
from typing import Optional


class Shareholder(BaseModel):
    name: str
    shareType: str
    shareCount: int


class CoInvestor(BaseModel):
    name: str
    amount: int


class ParsePdfResponse(BaseModel):
    shareholders: list[Shareholder]
    parseWarning: Optional[str] = None


class GenerateExcelRequest(BaseModel):
    companyName: str
    round: str
    preMoney: int
    shareholders: list[Shareholder]
    leadInvestorAmount: int
    coInvestors: list[CoInvestor] = []


# --- Async job models ---


class JobCreatedResponse(BaseModel):
    jobId: str


class JobStatusResponse(BaseModel):
    status: str  # "processing" | "completed" | "failed"
    shareholders: Optional[list[Shareholder]] = None
    parseWarning: Optional[str] = None
    error: Optional[str] = None
