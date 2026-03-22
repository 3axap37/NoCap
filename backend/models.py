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
