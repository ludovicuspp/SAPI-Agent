import { useCallback, useState } from "react";

interface UploadZoneProps {
  onUploaded: (boletinId: number) => void;
}

export function UploadZone({ onUploaded }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const handleFile = useCallback(
    async (file: File) => {
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        setError("Solo se aceptan archivos PDF");
        return;
      }
      if (file.size > 300 * 1024 * 1024) {
        setError("El archivo excede 300 MB");
        return;
      }
      setError("");
      setUploading(true);
      try {
        const formData = new FormData();
        formData.append("file", file);
        const token = localStorage.getItem("sapi-token");
        const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/boletines/upload`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({ detail: "Error al subir" }));
          throw new Error(body.detail);
        }
        const data = await res.json();
        onUploaded(data.boletin_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al subir");
      } finally {
        setUploading(false);
      }
    },
    [onUploaded],
  );

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const file = e.dataTransfer.files[0];
        if (file) handleFile(file);
      }}
      className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 text-center transition-colors ${
        dragging ? "border-brand-500 bg-brand-50" : "border-gray-300 bg-white"
      }`}
    >
      <input
        type="file"
        accept=".pdf"
        className="hidden"
        id="upload-input"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
      <label htmlFor="upload-input" className="cursor-pointer text-sm text-gray-600">
        {uploading ? (
          "Subiendo…"
        ) : (
          <>
            Arrastra un PDF aquí o <span className="font-medium text-brand-600">haz clic</span> para seleccionar
          </>
        )}
      </label>
      {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
    </div>
  );
}
