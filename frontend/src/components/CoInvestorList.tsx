import { CoInvestor } from "../api";

const SHARE_TYPES = ["보통주", "우선주", "RCPS"] as const;

interface Props {
  coInvestors: CoInvestor[];
  onChange: (list: CoInvestor[]) => void;
}

export default function CoInvestorList({ coInvestors, onChange }: Props) {
  function update(index: number, field: keyof CoInvestor, value: string | number) {
    const next = coInvestors.map((inv, i) =>
      i === index ? { ...inv, [field]: value } : inv
    );
    onChange(next);
  }

  function addRow() {
    onChange([...coInvestors, { name: "", amount: 0, shareType: "RCPS" }]);
  }

  function removeRow(index: number) {
    onChange(coInvestors.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-gray-700">
        공동 투자자 <span className="text-gray-400 font-normal">(선택)</span>
      </p>

      {coInvestors.length > 0 && (
        <div className="space-y-2">
          {coInvestors.map((inv, i) => (
            <div key={i} className="flex gap-2 items-center">
              <input
                value={inv.name}
                onChange={(e) => update(i, "name", e.target.value)}
                placeholder="투자자명"
                className="flex-1 border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
              <input
                type="number"
                min={0}
                step={1}
                value={inv.amount}
                onChange={(e) =>
                  update(i, "amount", parseInt(e.target.value) || 0)
                }
                placeholder="백만원"
                className="w-32 border rounded-lg px-3 py-2 text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
              <select
                value={inv.shareType}
                onChange={(e) => update(i, "shareType", e.target.value)}
                className="w-24 border rounded-lg px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              >
                {SHARE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <button
                onClick={() => removeRow(i)}
                className="text-red-400 hover:text-red-600 font-bold text-xl leading-none px-1"
                title="삭제"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <button
        onClick={addRow}
        className="text-sm text-blue-600 hover:text-blue-800 font-medium"
      >
        + 공동 투자자 추가
      </button>
    </div>
  );
}
