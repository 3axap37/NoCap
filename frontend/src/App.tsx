import { useState } from "react";
import {
  parsePdf,
  generateExcel,
  type Shareholder,
  type CoInvestor,
} from "./api";
import PdfUpload from "./components/PdfUpload";
import ShareholderTable from "./components/ShareholderTable";
import ValuationForm from "./components/ValuationForm";
import LeadInvestorForm from "./components/LeadInvestorForm";
import CoInvestorList from "./components/CoInvestorList";

type Step = 1 | 2 | 3 | 4;

export default function App() {
  const [step, setStep] = useState<Step>(1);

  // Step 1
  const [parseLoading, setParseLoading] = useState(false);
  const [parseWarning, setParseWarning] = useState<string | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);

  // Step 1 → 2
  const [shareholders, setShareholders] = useState<Shareholder[]>([]);

  // Step 2
  const [companyName, setCompanyName] = useState("");
  const [round, setRound] = useState("Series A");
  const [preMoney, setPreMoney] = useState("");

  // Step 3
  const [leadAmount, setLeadAmount] = useState("");
  const [coInvestors, setCoInvestors] = useState<CoInvestor[]>([]);

  // Step 4
  const [downloadLoading, setDownloadLoading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  // ------------------------------------------------------------------ //

  async function handlePdfParsed(file: File) {
    setParseLoading(true);
    setParseError(null);
    setParseWarning(null);
    try {
      const res = await parsePdf(file);
      setShareholders(res.shareholders);
      setParseWarning(res.parseWarning ?? null);
      setStep(2);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : String(e));
    } finally {
      setParseLoading(false);
    }
  }

  function step1Valid() {
    return shareholders.length > 0 && shareholders.every((s) => s.name && s.shareCount > 0);
  }

  function step2Valid() {
    return (
      companyName.trim() !== "" &&
      round !== "" &&
      Number(preMoney) > 0
    );
  }

  function step3Valid() {
    return (
      Number(leadAmount) > 0 &&
      coInvestors.every((inv) => inv.name.trim() !== "" && inv.amount > 0)
    );
  }

  async function handleDownload() {
    setDownloadLoading(true);
    setDownloadError(null);
    try {
      await generateExcel({
        companyName: companyName.trim(),
        round,
        preMoney: Number(preMoney),
        shareholders,
        leadInvestorAmount: Number(leadAmount),
        coInvestors,
      });
    } catch (e) {
      setDownloadError(e instanceof Error ? e.message : String(e));
    } finally {
      setDownloadLoading(false);
    }
  }

  // ------------------------------------------------------------------ //

  const STEPS = [
    "PDF 업로드",
    "기업 정보",
    "투자 정보",
    "다운로드",
  ];

  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Cap Table Generator</h1>
          <p className="text-gray-500 mt-1">주주명부 PDF → Cap Table Excel 변환</p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center justify-between mb-8 px-2">
          {STEPS.map((label, i) => {
            const num = (i + 1) as Step;
            const active = num === step;
            const done = num < step;
            return (
              <div key={i} className="flex-1 flex flex-col items-center">
                <div
                  className={`w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm transition-colors ${
                    active
                      ? "bg-blue-600 text-white"
                      : done
                      ? "bg-green-500 text-white"
                      : "bg-gray-200 text-gray-500"
                  }`}
                >
                  {done ? "✓" : num}
                </div>
                <span
                  className={`text-xs mt-1 ${
                    active ? "text-blue-600 font-semibold" : "text-gray-400"
                  }`}
                >
                  {label}
                </span>
                {i < STEPS.length - 1 && (
                  <div className="absolute" />
                )}
              </div>
            );
          })}
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-6 space-y-6">

          {/* ---- Step 1: Upload PDF ---- */}
          {step === 1 && (
            <>
              <h2 className="text-lg font-semibold text-gray-800">
                Step 1: 주주명부 PDF 업로드
              </h2>
              <PdfUpload onParsed={handlePdfParsed} loading={parseLoading} />
              {parseError && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {parseError}
                </div>
              )}
            </>
          )}

          {/* ---- Step 2: Shareholder table + company info ---- */}
          {step === 2 && (
            <>
              <h2 className="text-lg font-semibold text-gray-800">
                Step 2: 주주 목록 확인 및 기업 정보 입력
              </h2>

              {parseWarning && (
                <div className="rounded-lg bg-yellow-50 border border-yellow-300 px-4 py-3 text-sm text-yellow-800">
                  ⚠️ {parseWarning}
                </div>
              )}

              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">
                  주주 목록 ({shareholders.length}명) — 오류가 있으면 직접 수정하세요
                </p>
                <ShareholderTable
                  shareholders={shareholders}
                  onChange={setShareholders}
                />
              </div>

              <ValuationForm
                companyName={companyName}
                round={round}
                preMoney={preMoney}
                onCompanyName={setCompanyName}
                onRound={setRound}
                onPreMoney={setPreMoney}
              />

              <div className="flex justify-between pt-2">
                <button
                  onClick={() => setStep(1)}
                  className="px-5 py-2 rounded-lg border text-gray-600 hover:bg-gray-50 text-sm"
                >
                  이전
                </button>
                <button
                  disabled={!step1Valid() || !step2Valid()}
                  onClick={() => setStep(3)}
                  className="px-5 py-2 rounded-lg bg-blue-600 text-white font-semibold disabled:opacity-40 hover:bg-blue-700 text-sm"
                >
                  다음
                </button>
              </div>
            </>
          )}

          {/* ---- Step 3: Investor details ---- */}
          {step === 3 && (
            <>
              <h2 className="text-lg font-semibold text-gray-800">
                Step 3: 투자 정보 입력
              </h2>

              <LeadInvestorForm amount={leadAmount} onAmount={setLeadAmount} />
              <CoInvestorList coInvestors={coInvestors} onChange={setCoInvestors} />

              <div className="flex justify-between pt-2">
                <button
                  onClick={() => setStep(2)}
                  className="px-5 py-2 rounded-lg border text-gray-600 hover:bg-gray-50 text-sm"
                >
                  이전
                </button>
                <button
                  disabled={!step3Valid()}
                  onClick={() => setStep(4)}
                  className="px-5 py-2 rounded-lg bg-blue-600 text-white font-semibold disabled:opacity-40 hover:bg-blue-700 text-sm"
                >
                  다음
                </button>
              </div>
            </>
          )}

          {/* ---- Step 4: Download ---- */}
          {step === 4 && (
            <>
              <h2 className="text-lg font-semibold text-gray-800">
                Step 4: Cap Table 다운로드
              </h2>

              <div className="rounded-lg bg-gray-50 border border-gray-200 px-5 py-4 space-y-2 text-sm text-gray-700">
                <div className="flex justify-between">
                  <span className="font-medium">기업명</span>
                  <span>{companyName}</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-medium">라운드</span>
                  <span>{round}</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-medium">Pre-money</span>
                  <span>{Number(preMoney).toLocaleString("ko-KR")} 원</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-medium">주주 수</span>
                  <span>{shareholders.length}명</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-medium">리드 투자금액</span>
                  <span>{Number(leadAmount).toLocaleString("ko-KR")} 원</span>
                </div>
                {coInvestors.length > 0 && (
                  <div className="flex justify-between">
                    <span className="font-medium">공동 투자자</span>
                    <span>{coInvestors.length}명</span>
                  </div>
                )}
              </div>

              {downloadError && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {downloadError}
                </div>
              )}

              <div className="flex justify-between pt-2">
                <button
                  onClick={() => setStep(3)}
                  className="px-5 py-2 rounded-lg border text-gray-600 hover:bg-gray-50 text-sm"
                >
                  이전
                </button>
                <button
                  disabled={downloadLoading}
                  onClick={handleDownload}
                  className="px-6 py-3 rounded-lg bg-green-600 text-white font-semibold disabled:opacity-40 hover:bg-green-700 text-sm flex items-center gap-2"
                >
                  {downloadLoading ? "생성 중…" : "📥 Cap Table 다운로드"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
