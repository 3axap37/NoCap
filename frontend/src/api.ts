const BASE_URL = import.meta.env.VITE_API_URL || "";

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

// --- Async job types ---

interface JobCreatedResponse {
  jobId: string;
}

interface JobStatusResponse {
  status: "processing" | "completed" | "failed";
  shareholders?: Shareholder[];
  parseWarning?: string | null;
  error?: string;
}

// --- Helpers ---

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// --- API functions ---

export async function parsePdf(
  file: File,
  onStatusMessage?: (msg: string) => void,
): Promise<ParsePdfResponse> {
  // 1. Submit job
  onStatusMessage?.("PDF 업로드 중...");
  const form = new FormData();
  form.append("file", file);

  const submitRes = await fetch(`${BASE_URL}/api/parse-pdf`, {
    method: "POST",
    body: form,
  });
  if (!submitRes.ok) {
    const err = await submitRes.json().catch(() => ({ detail: submitRes.statusText }));
    throw new Error(err.detail ?? "PDF 업로드 실패");
  }

  const { jobId } = (await submitRes.json()) as JobCreatedResponse;

  // 2. Poll for result
  onStatusMessage?.("주주명부 분석 중...");
  const startTime = Date.now();
  const POLL_INTERVAL = 2000;
  const LONG_WAIT_MS = 30_000;
  const TIMEOUT_MS = 180_000;

  while (true) {
    await sleep(POLL_INTERVAL);

    const elapsed = Date.now() - startTime;
    if (elapsed > TIMEOUT_MS) {
      throw new Error("처리에 실패했을 수 있습니다. 다시 시도해주세요.");
    }
    if (elapsed > LONG_WAIT_MS) {
      onStatusMessage?.("대용량 문서를 처리 중입니다. 잠시만 기다려주세요.");
    }

    const statusRes = await fetch(`${BASE_URL}/api/status/${jobId}`);
    if (!statusRes.ok) {
      throw new Error("상태 조회 실패");
    }

    const status = (await statusRes.json()) as JobStatusResponse;

    if (status.status === "completed") {
      onStatusMessage?.("완료!");
      return {
        shareholders: status.shareholders ?? [],
        parseWarning: status.parseWarning ?? null,
      };
    }

    if (status.status === "failed") {
      throw new Error(status.error ?? "PDF 파싱 실패");
    }
  }
}

export async function generateExcel(req: GenerateExcelRequest): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/generate-excel`, {
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
