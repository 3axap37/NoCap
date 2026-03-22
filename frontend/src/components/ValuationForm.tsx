import RoundSelector from "./RoundSelector";

interface Props {
  companyName: string;
  round: string;
  preMoney: string;
  onCompanyName: (v: string) => void;
  onRound: (v: string) => void;
  onPreMoney: (v: string) => void;
}

export default function ValuationForm({
  companyName,
  round,
  preMoney,
  onCompanyName,
  onRound,
  onPreMoney,
}: Props) {
  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">기업명</label>
        <input
          value={companyName}
          onChange={(e) => onCompanyName(e.target.value)}
          placeholder="주식회사 ○○○"
          className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </div>

      <RoundSelector value={round} onChange={onRound} />

      <div className="space-y-1">
        <label className="block text-sm font-medium text-gray-700">
          투자 전 기업 가치 (Pre-money, 원)
        </label>
        <input
          type="number"
          min={0}
          step={1000000}
          value={preMoney}
          onChange={(e) => onPreMoney(e.target.value)}
          placeholder="9500000000"
          className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        {preMoney && !isNaN(Number(preMoney)) && Number(preMoney) > 0 && (
          <p className="text-xs text-gray-500">
            {Number(preMoney).toLocaleString("ko-KR")} 원
          </p>
        )}
      </div>
    </div>
  );
}
