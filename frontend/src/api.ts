export interface Shareholder {
  name: string;
  shareType: string;
  shareCount: number;
}

export interface CoInvestor {
  name: string;
  amount: number;
}

export interface ParsePdfResponse {
  shareholders: Shareholder[];
  parseWarning: string | null;
}

export interface GenerateExcelRequest {
  companyName: string;
  round: string;
  preMoney: number;
  shareholders: Shareholder[];
  leadInvestorAmount: number;
  coInvestors: CoInvestor[];
}

export async function parsePdf(file: File): Promise<ParsePdfResponse> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch("/api/parse-pdf", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "PDF 파싱 실패");
  }
  return res.json();
}

export async function generateExcel(req: GenerateExcelRequest): Promise<void> {
  const res = await fetch("/api/generate-excel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "엑셀 생성 실패");
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "cap_table.xlsx";
  a.click();
  URL.revokeObjectURL(url);
}
