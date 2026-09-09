import { useState } from "react";
import { downloadFile } from "@/lib/api";
import { Button } from "@/components/ui/button";

type Dataset = "detections" | "portfolio" | "watchlist";

/** Botones de descarga (.csv / .md) para los datasets exportables. */
export function ExportButtons({ dataset }: { dataset: Dataset }) {
  const [busy, setBusy] = useState(false);

  const download = async (fmt: "csv" | "md") => {
    setBusy(true);
    try {
      await downloadFile(`/api/export/${dataset}.${fmt}`, `sapi-${dataset}.${fmt}`);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Error al descargar");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex gap-2" role="group" aria-label="Exportar datos">
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => download("csv")}
        title="Descargar en formato CSV (Excel)"
      >
        CSV
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy}
        onClick={() => download("md")}
        title="Descargar en formato Markdown"
      >
        Markdown
      </Button>
    </div>
  );
}
