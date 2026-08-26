export interface User {
  id: number;
  email: string;
  role: "admin" | "agent";
  active: boolean;
  created_at: string;
}

export interface Watchlist {
  id: number;
  user_id: number;
  name: string;
  class_nice: number | null;
  notes: string | null;
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
  uploaded_by: number;
  filename: string;
  file_path: string;
  file_sha256: string;
  bulletin_number: number | null;
  period: string | null;
  pages: number | null;
  status: BoletinStatus;
  needs_hermes_review: boolean;
  uploaded_at: string;
  processed_at: string | null;
  error: string | null;
  entries_matcheables: number;
  entries_hermes_pending: number;
  entries_figura: number;
  entries_lema: number;
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
  entries_matcheables: number;
  entries_figura: number;
  entries_lema: number;
  entries_hermes_pending: number;
  error: string | null;
}
