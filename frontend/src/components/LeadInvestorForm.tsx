const LEAD_INVESTOR_NAME = "한투 바른동행 셰르파 제4호 펀드";

interface Props {
  amount: string;
  onAmount: (v: string) => void;
}

export default function LeadInvestorForm({ amount, onAmount }: Props) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3">
        <p className="text-xs text-blue-600 font-medium uppercase tracking-wide mb-0.5">
          리드 투자자
        </p>
        <p className="font-semibold text-gray-800">{LEAD_INVESTOR_NAME}</p>
      </div>

      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">
          투자금액 (원)
        </label>
        <input
          type="number"
          min={0}
          step={1000000}
          value={amount}
          onChange={(e) => onAmount(e.target.value)}
          placeholder="500000000"
          className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        {amount && !isNaN(Number(amount)) && Number(amount) > 0 && (
          <p className="text-xs text-gray-500">
            {Number(amount).toLocaleString("ko-KR")} 원
          </p>
        )}
      </div>
    </div>
  );
}
