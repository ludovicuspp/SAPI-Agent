import { useCallback, useRef, useState } from "react";

interface UploadZoneProps {
  onUploaded: (boletinId: number) => void;
}

interface UploadHandle {
  promise: Promise<{ boletin_id: number }>;
  abort: () => void;
}

export function UploadZone({ onUploaded }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<{
    loaded: number;
    total: number;
  } | null>(null);
  const xhrRef = useRef<XMLHttpRequest | null>(null);

  const upload = useCallback(
    (file: File): UploadHandle => {
      setError("");
      setProgress({ loaded: 0, total: file.size });

      const xhr = new XMLHttpRequest();
      xhrRef.current = xhr;
      xhr.open("POST", `${import.meta.env.VITE_API_BASE_URL}/api/boletines/upload`);
      const token = localStorage.getItem("sapi-token");
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);

      const promise = new Promise<{ boletin_id: number }>((resolve, reject) => {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            setProgress({ loaded: e.loaded, total: e.total });
          }
        };
        xhr.onload = () => {
          if (xhr.status === 202) {
            try {
              const data = JSON.parse(xhr.responseText) as { boletin_id: number };
              resolve(data);
            } catch {
              reject(new Error("Respuesta inválida del servidor"));
            }
          } else {
            let detail = "Error al subir";
            try {
              const body = JSON.parse(xhr.responseText) as { detail?: string };
              if (body.detail) detail = body.detail;
            } catch {
              /* ignore */
            }
            reject(new Error(detail));
          }
        };
        xhr.onerror = () => reject(new Error("Error de red al subir"));
        xhr.onabort = () => reject(new Error("Subida cancelada"));

        const formData = new FormData();
        formData.append("file", file);
        xhr.send(formData);
      });

      return {
        promise,
        abort: () => xhr.abort(),
      };
    },
    [],
  );

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
      const handle = upload(file);
      try {
        const data = await handle.promise;
        onUploaded(data.boletin_id);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Error al subir");
      } finally {
        xhrRef.current = null;
        setProgress(null);
      }
    },
    [upload, onUploaded],
  );

  const pct = progress && progress.total > 0
    ? Math.min(100, Math.round((progress.loaded / progress.total) * 100))
    : 0;
  const uploadedMB = progress ? (progress.loaded / 1024 / 1024).toFixed(1) : "0.0";
  const totalMB = progress ? (progress.total / 1024 / 1024).toFixed(1) : "0.0";

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) void handleFile(file);
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
            if (file) void handleFile(file);
            e.target.value = "";
          }}
        />
        <label htmlFor="upload-input" className="cursor-pointer text-sm text-gray-600">
          {progress ? (
            "Subiendo…"
          ) : (
            <>
              Arrastra un PDF aquí o <span className="font-medium text-brand-600">haz clic</span> para seleccionar
            </>
          )}
        </label>
        {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
      </div>

      {progress && (
        <div className="space-y-1">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
            <div
              className="h-full rounded-full bg-brand-500 transition-[width] duration-150"
              style={{ width: `${pct}%` }}
              data-testid="upload-progress-bar"
            />
          </div>
          <div className="flex justify-between text-xs text-gray-500">
            <span>{uploadedMB} MB / {totalMB} MB</span>
            <span>{pct}%</span>
          </div>
        </div>
      )}
    </div>
  );
}
