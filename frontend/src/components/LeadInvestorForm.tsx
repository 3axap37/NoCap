const SHARE_TYPES = ["보통주", "우선주", "RCPS"] as const;

interface Props {
  name: string;
  amount: string;
  shareType: string;
  onName: (v: string) => void;
  onAmount: (v: string) => void;
  onShareType: (v: string) => void;
}

export default function LeadInvestorForm({
  name,
  amount,
  shareType,
  onName,
  onAmount,
  onShareType,
}: Props) {
  return (
    <div className="space-y-4">
      <div className="rounded-lg bg-blue-50 border border-blue-200 px-4 py-3">
        <p className="text-xs text-blue-600 font-medium uppercase tracking-wide">
          당사 투자 펀드
        </p>
      </div>

      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">
          펀드명
        </label>
        <input
          value={name}
          onChange={(e) => onName(e.target.value)}
          placeholder="한투 바른동행 셰르파 제4호 펀드"
          className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </div>

      <div className="flex gap-3">
        <div className="flex-1 space-y-1">
          <label className="block text-sm font-medium text-gray-700">
            투자금액 (백만원)
          </label>
          <input
            type="number"
            min={0}
            step={1}
            value={amount}
            onChange={(e) => onAmount(e.target.value)}
            placeholder="500"
            className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          {amount && !isNaN(Number(amount)) && Number(amount) > 0 && (
            <p className="text-xs text-gray-500">
              {(Number(amount) * 1_000_000).toLocaleString("ko-KR")} 원
            </p>
          )}
        </div>

        <div className="w-32 space-y-1">
          <label className="block text-sm font-medium text-gray-700">
            주식종류
          </label>
          <select
            value={shareType}
            onChange={(e) => onShareType(e.target.value)}
            className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            {SHARE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
