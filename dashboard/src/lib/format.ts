export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("es-VE", { day: "2-digit", month: "short", year: "numeric" });
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("es-VE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatSimilarity(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export function formatClass(n: number | null): string {
  if (n === null) return "—";
  return n === 0 ? "LC" : String(n);
}

export function statusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: "Pendiente",
    extracting: "Extrayendo",
    extracted: "Extraído",
    hermes_pending: "Esperando Hermes",
    hermes_done: "Hermes completado",
    failed: "Error",
  };
  return map[status] ?? status;
}

export function stepLabel(step: string | null | undefined): string {
  if (!step) return "";
  const map: Record<string, string> = {
    extracting_text: "Leyendo texto del PDF",
    parsing_entries: "Parseando entradas de marcas",
    matching: "Comparando con watchlist y portfolio",
    notifying: "Enviando notificaciones",
    done: "Procesamiento completado",
    failed: "Procesamiento con errores",
  };
  return map[step] ?? step;
}

export function isHermesInProgress(b: {
  status: string;
  needs_hermes_review: boolean;
  hermes_processed_at?: string | null;
}): boolean {
  return (
    b.status === "extracted" &&
    b.needs_hermes_review &&
    !b.hermes_processed_at
  );
}

export function statusColor(status: string): string {
  const map: Record<string, string> = {
    pending: "bg-gray-100 text-gray-700",
    extracting: "bg-blue-100 text-blue-700",
    extracted: "bg-green-100 text-green-700",
    hermes_pending: "bg-yellow-100 text-yellow-700",
    hermes_done: "bg-emerald-100 text-emerald-700",
    failed: "bg-red-100 text-red-700",
  };
  return map[status] ?? "bg-gray-100 text-gray-700";
}

export function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    pdfplumber_text: "Parser",
    hermes_llm: "Hermes LLM",
    hermes_vision: "Hermes Visión",
  };
  return map[source] ?? source;
}

/** Etiqueta legible del tipo de disposición administrativa. */
export function disposicionLabel(tipo: string | null | undefined): string {
  const map: Record<string, string> = {
    NEGACION: "Negada",
    CONCESION: "Concedida",
    CADUCA: "Caducada",
    REVOCA: "Revocada",
    INADMISIBLE: "Inadmisible",
    DEVOLUCION_FORMA: "Devolución de forma",
    DEVOLUCION_FONDO: "Devolución de fondo",
  };
  return tipo ? (map[tipo] ?? tipo) : "";
}

/** Color del badge según el tipo de disposición. */
export function disposicionColor(tipo: string | null | undefined): string {
  const map: Record<string, string> = {
    NEGACION: "bg-red-100 text-red-700",
    CONCESION: "bg-green-100 text-green-700",
    CADUCA: "bg-gray-100 text-gray-700",
    REVOCA: "bg-blue-100 text-blue-700",
    INADMISIBLE: "bg-gray-100 text-gray-700",
    DEVOLUCION_FORMA: "bg-yellow-100 text-yellow-700",
    DEVOLUCION_FONDO: "bg-orange-100 text-orange-700",
  };
  return map[tipo ?? ""] ?? "bg-gray-100 text-gray-700";
}

/** Etiqueta legible de un lapso legal. */
export function lapseKeyLabel(key: string): string {
  const map: Record<string, string> = {
    pago_concesion: "Pago de concesión",
    subsanar_forma: "Subsanación de forma",
    subsanar_fondo: "Subsanación de fondo",
    recurso_negacion: "Recurso de negación",
    recurso_caducidad: "Recurso de caducidad",
    recurso_inadmisible: "Recurso de inadmisibilidad",
    oposicion: "Oposición a publicación",
  };
  return map[key] ?? key;
}

/** Etiqueta legible del estado de una alerta de lapso. */
export function alertEstadoLabel(estado: string): string {
  const map: Record<string, string> = {
    pendiente: "Pendiente",
    vencida: "Vencida",
    cumplida: "Cumplida",
    descartada: "Descartada",
  };
  return map[estado] ?? estado;
}

/** Color del badge según el estado de una alerta de lapso. */
export function alertEstadoColor(estado: string): string {
  const map: Record<string, string> = {
    pendiente: "bg-blue-100 text-blue-700",
    vencida: "bg-red-100 text-red-700",
    cumplida: "bg-emerald-100 text-emerald-700",
    descartada: "bg-gray-100 text-gray-700",
  };
  return map[estado] ?? "bg-gray-100 text-gray-700";
}

/** Cuenta regresiva en días hábiles para una alerta pendiente. */
export function alertCountdown(diasRestantes: number | null): string {
  if (diasRestantes === null) return "—";
  if (diasRestantes < 0) return `${Math.abs(diasRestantes)}d vencido`;
  if (diasRestantes === 0) return "vence hoy";
  return `${diasRestantes}d`;
}
