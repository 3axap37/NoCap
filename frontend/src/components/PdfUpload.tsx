import { useRef, useState, DragEvent } from "react";

interface Props {
  onParsed: (file: File) => Promise<void>;
  loading: boolean;
}

export default function PdfUpload({ onParsed, loading }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      alert("PDF 파일만 업로드할 수 있습니다.");
      return;
    }
    setSelectedFile(file);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="space-y-4">
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors ${
          dragging
            ? "border-blue-500 bg-blue-50"
            : "border-gray-300 hover:border-blue-400 hover:bg-gray-50"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={handleChange}
        />
        <div className="text-5xl mb-3">📄</div>
        {selectedFile ? (
          <p className="font-medium text-gray-700">{selectedFile.name}</p>
        ) : (
          <>
            <p className="font-medium text-gray-700">
              주주명부 PDF를 여기에 드래그하거나 클릭하여 선택
            </p>
            <p className="text-sm text-gray-400 mt-1">PDF 파일만 가능</p>
          </>
        )}
      </div>

      <button
        disabled={!selectedFile || loading}
        onClick={() => selectedFile && onParsed(selectedFile)}
        className="w-full py-3 rounded-lg bg-blue-600 text-white font-semibold disabled:opacity-40 hover:bg-blue-700 transition-colors"
      >
        {loading ? "파싱 중…" : "PDF 파싱"}
      </button>
    </div>
  );
}
