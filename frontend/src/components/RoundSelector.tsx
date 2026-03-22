interface Props {
  value: string;
  onChange: (value: string) => void;
}

const ROUNDS = ["Seed/Pre-A", "Series A", "Series B", "Series C+"];

export default function RoundSelector({ value, onChange }: Props) {
  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-gray-700">투자 라운드</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-400"
      >
        {ROUNDS.map((r) => (
          <option key={r} value={r}>{r}</option>
        ))}
      </select>
    </div>
  );
}
