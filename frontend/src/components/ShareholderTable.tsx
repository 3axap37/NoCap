import { Shareholder } from "../api";

interface Props {
  shareholders: Shareholder[];
  onChange: (shareholders: Shareholder[]) => void;
}

const SHARE_TYPES = ["보통주", "우선주", "RCPS", "전환우선주", "상환전환우선주"];

export default function ShareholderTable({ shareholders, onChange }: Props) {
  function update(index: number, field: keyof Shareholder, value: string | number) {
    const next = shareholders.map((sh, i) =>
      i === index ? { ...sh, [field]: value } : sh
    );
    onChange(next);
  }

  function addRow() {
    onChange([...shareholders, { name: "", shareType: "보통주", shareCount: 0 }]);
  }

  function removeRow(index: number) {
    onChange(shareholders.filter((_, i) => i !== index));
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full text-sm">
          <thead className="bg-gray-100 text-gray-600 uppercase text-xs">
            <tr>
              <th className="px-3 py-2 text-left">주주명</th>
              <th className="px-3 py-2 text-left">주식종류</th>
              <th className="px-3 py-2 text-right">주식수</th>
              <th className="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {shareholders.map((sh, i) => (
              <tr key={i} className="hover:bg-gray-50">
                <td className="px-3 py-1.5">
                  <input
                    value={sh.name}
                    onChange={(e) => update(i, "name", e.target.value)}
                    className="w-full border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                  />
                </td>
                <td className="px-3 py-1.5">
                  <select
                    value={sh.shareType}
                    onChange={(e) => update(i, "shareType", e.target.value)}
                    className="w-full border rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-blue-400"
                  >
                    {SHARE_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </td>
                <td className="px-3 py-1.5">
                  <input
                    type="number"
                    min={0}
                    value={sh.shareCount}
                    onChange={(e) => update(i, "shareCount", parseInt(e.target.value) || 0)}
                    className="w-full border rounded px-2 py-1 text-right focus:outline-none focus:ring-1 focus:ring-blue-400"
                  />
                </td>
                <td className="px-2 py-1.5 text-center">
                  <button
                    onClick={() => removeRow(i)}
                    className="text-red-400 hover:text-red-600 font-bold text-lg leading-none"
                    title="삭제"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        onClick={addRow}
        className="text-sm text-blue-600 hover:text-blue-800 font-medium"
      >
        + 주주 추가
      </button>
    </div>
  );
}
