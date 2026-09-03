export type UserRole = "admin" | "propietario" | "empresa" | "agent";

export interface UserAction {
  accion: string;
  timestamp: string;
}

export interface User {
  id: number;
  email: string;
  role: UserRole;
  nombre: string;
  acciones: UserAction[];
  created_at: string;
}

export interface Watchlist {
  id: number;
  user_id: number;
  name: string;
  class_nice: number | null;
  notes: string | null;
  productos_servicios: string | null;
  active: boolean;
  created_at: string;
}

export interface Portfolio {
  id: number;
  user_id: number;
  name: string;
  expediente: string | null;
  class_nice: number | null;
  status: string | null;
  last_checked_at: string | null;
  notes: string | null;
  created_at: string;
  pais: string | null;
  etiqueta: string | null;
  tipo_registro: string | null;
  bufete: string | null;
  solicitud: string | null;
  fecha_solicitud: string | null;
  registro: string | null;
  fecha_registro: string | null;
  fecha_vencimiento: string | null;
  titular: string | null;
  tramitante: string | null;
  empresa_licenciada: string | null;
  productos_servicios: string | null;
  comentarios: string | null;
  last_boletin_id: number | null;
  last_boletin_period: string | null;
  updated_at: string;
}

export interface PortfolioHistory {
  id: number;
  portfolio_id: number;
  boletin_id: number | null;
  boletin_period: string | null;
  boletin_number: number | null;
  estado: string | null;
  snapshot: Record<string, unknown>;
  created_at: string;
}

export interface PortfolioImportResult {
  created: number;
  updated: number;
  errors: string[];
}

export type BoletinStatus =
  | "pending"
  | "extracting"
  | "extracted"
  | "hermes_pending"
  | "hermes_done"
  | "failed";

export interface Boletin {
  id: number;
  uploaded_by: number | null;
  uploaded_by_name?: string | null;
  filename: string;
  file_path: string;
  file_sha256: string;
  bulletin_number: number | null;
  period: string | null;
  pages: number | null;
  status: BoletinStatus;
  needs_hermes_review: boolean;
  hermes_processed_at?: string | null;
  uploaded_at: string;
  processed_at: string | null;
  error: string | null;
  entries_matcheables: number;
  entries_hermes_pending: number;
  entries_figura: number;
  entries_lema: number;
  progress_step: string | null;
  progress_current_page: number | null;
  progress_total_pages: number | null;
  hermes_progress_step: string | null;
  hermes_progress_current_page: number | null;
  hermes_progress_total_pages: number | null;
  hermes_progress_updated_at: string | null;
}

export type MatchKind = "similar" | "own_status";
export type Source = "pdfplumber_text" | "hermes_llm" | "hermes_vision";
export type Confidence = "high" | "medium" | "low";

export interface Detection {
  id: number;
  boletin_id: number;
  user_id: number;
  watchlist_id: number | null;
  portfolio_id: number | null;
  expediente: string | null;
  mark_name: string;
  titular: string | null;
  class_nice: number | null;
  page: number | null;
  similarity: number;
  match_kind: MatchKind;
  source: Source;
  confidence: Confidence;
  raw_excerpt: string | null;
  matched_with: string | null;
  detected_at: string;
  notified_email: boolean;
  pais: string | null;
  fecha_inscripcion: string | null;
  fuente_parsing: string | null;
  es_figura: boolean;
  es_lema: boolean;
}

export interface Summary {
  watchlist_count: number;
  portfolio_count: number;
  boletines_count: number;
  detections_count: number;
  last_boletin_at: string | null;
  recent_detections: Detection[];
  recent_boletines: Boletin[];
}

export interface BoletinProgress {
  boletin_id: number;
  status: BoletinStatus;
  pages: number | null;
  progress_step: string | null;
  progress_current_page: number | null;
  progress_total_pages: number | null;
  needs_hermes_review?: boolean;
  hermes_processed_at?: string | null;
  entries_matcheables: number;
  entries_figura: number;
  entries_lema: number;
  entries_hermes_pending: number;
  error: string | null;
  hermes_progress_step: string | null;
  hermes_progress_current_page: number | null;
  hermes_progress_total_pages: number | null;
  hermes_progress_updated_at: string | null;
}

export interface BoletinEntry {
  id: number;
  boletin_id: number;
  expediente: string;
  marca: string | null;
  class_nice: number | null;
  clase_especial: string | null;
  titular: string | null;
  pais: string | null;
  fecha_inscripcion: string | null;
  estatus: string | null;
  page: number | null;
  is_matcheable: boolean;
  is_figura: boolean;
  is_lema: boolean;
  productos_servicios: string | null;
  fuente_parsing: string | null;
  source: string | null;
  excerpt: string | null;
}
