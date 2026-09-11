import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { request } from "@/lib/api";
import { watchBoletinProgress } from "@/lib/ws";
import { statusLabel, statusColor, stepLabel, isHermesInProgress, formatClass, disposicionLabel, disposicionColor } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import type { Boletin, BoletinEntry, BoletinProgress } from "@/types/api";

export default function BoletinDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [boletin, setBoletin] = useState<Boletin | null>(null);
  const [progress, setProgress] = useState<BoletinProgress | null>(null);
  const [entries, setEntries] = useState<BoletinEntry[]>([]);
  const [entryQuery, setEntryQuery] = useState("");
  const [page, setPage] = useState(1);
  const [selectedEntry, setSelectedEntry] = useState<BoletinEntry | null>(null);
  const PAGE_SIZE = 50;

  type EntryFilters = {
    marca: string;
    titular: string;
    tramitante: string;
    clase: string;
    pais: string;
    estatus: string;
    tomo: string;
  };
  const EMPTY_FILTERS: EntryFilters = {
    marca: "",
    titular: "",
    tramitante: "",
    clase: "",
    pais: "",
    estatus: "",
    tomo: "",
  };
  const [filters, setFilters] = useState<EntryFilters>(EMPTY_FILTERS);

  useEffect(() => {
    if (!id) return;
    request<Boletin>(`/api/boletines/${id}`).then(setBoletin).catch(console.error);
  }, [id]);

  useEffect(() => {
    if (!boletin || boletin.status !== "extracting") return;
    const unsub = watchBoletinProgress(boletin.id, (e) => {
      setProgress(e);
      if (e.status !== "extracting") {
        // refresh boletin data
        request<Boletin>(`/api/boletines/${id}`).then(setBoletin).catch(console.error);
      }
    });
    return unsub;
  }, [boletin?.status, id]);

  // Poll Hermes: cuando extracted y needs_hermes_review, refrescar cada 3 s
  // para detectar cuando Hermes termina.
  useEffect(() => {
    if (!boletin) return;
    const hermesActive =
      boletin.status === "extracted" &&
      boletin.needs_hermes_review &&
      !boletin.hermes_processed_at;
    if (!hermesActive) return;
    const t = window.setInterval(() => {
      request<Boletin>(`/api/boletines/${id}`).then(setBoletin).catch(console.error);
    }, 3000);
    return () => window.clearInterval(t);
  }, [boletin, id]);

  // Cargar las marcas extraídas del boletín (capa fuente).
  useEffect(() => {
    if (!id) return;
    request<BoletinEntry[]>(`/api/boletines/${id}/entries`)
      .then(setEntries)
      .catch(console.error);
  }, [id]);

  // Orden de tomos en romano (I, II, …, XXV) para ordenar el select.
  const TOMO_ORDER: Record<string, number> = (() => {
    const m: Record<string, number> = {};
    const romans = [
      "I","II","III","IV","V","VI","VII","VIII","IX","X",
      "XI","XII","XIII","XIV","XV","XVI","XVII","XVIII","XIX","XX",
      "XXI","XXII","XXIII","XXIV","XXV",
    ];
    romans.forEach((r, i) => { m[r] = i + 1; });
    return m;
  })();

  // Clave de búsqueda precomputada por entry (todos los campos en minúscula,
  // unidos en un solo string). Optimiza el filtrado: una sola pasada de
  // minúsculas por entry al cargar, en vez de 9 `toLowerCase()` × N entries
  // en cada keystroke.
  const searchKeys = useMemo(() => {
    const m = new Map<number, string>();
    for (const e of entries) {
      const cls =
        e.clase_especial === "LC" || e.class_nice === 0
          ? "LC"
          : e.class_nice != null
          ? String(e.class_nice)
          : "";
      m.set(
        e.id,
        [
          e.marca ?? "",
          e.expediente,
          e.titular ?? "",
          e.tramitante ?? "",
          cls,
          e.pais ?? "",
          e.estatus ?? "",
          e.tomo ?? "",
          e.productos_servicios ?? "",
        ]
          .join(" ")
          .toLowerCase(),
      );
    }
    return m;
  }, [entries]);

  // Valores únicos por filtro, ordenados para poblar los selects.
  const filterOptions = useMemo(() => {
    const collect = (fn: (e: BoletinEntry) => string | null): string[] => {
      const set = new Set<string>();
      for (const e of entries) {
        const v = fn(e);
        if (v) set.add(v);
      }
      return Array.from(set);
    };
    const alpha = (a: string, b: string) =>
      a.localeCompare(b, "es", { sensitivity: "base" });
    const clases = collect((e) => {
      if (e.clase_especial === "LC" || e.class_nice === 0) return "LC";
      return e.class_nice != null ? String(e.class_nice) : null;
    }).sort((a, b) => {
      if (a === "LC") return 1;
      if (b === "LC") return -1;
      return Number(a) - Number(b);
    });
    const tomos = collect((e) => e.tomo ?? null).sort(
      (a, b) => (TOMO_ORDER[a] ?? 9999) - (TOMO_ORDER[b] ?? 9999),
    );
    return {
      marcas: collect((e) => e.marca ?? null).sort(alpha),
      titulares: collect((e) => e.titular ?? null).sort(alpha),
      tramitantes: collect((e) => e.tramitante ?? null).sort(alpha),
      clases,
      paises: collect((e) => e.pais ?? null).sort(alpha),
      estatus: collect((e) => e.estatus ?? null).sort(alpha),
      tomos,
    };
  }, [entries]);

  const deferredQuery = useDeferredValue(entryQuery);

  // Búsqueda libre + filtros estructurados en una sola pasada.
  const filteredEntries = useMemo(() => {
    const q = deferredQuery.trim().toLowerCase();
    return entries.filter((e) => {
      if (q && !searchKeys.get(e.id)?.includes(q)) return false;
      if (filters.marca && e.marca !== filters.marca) return false;
      if (filters.titular && e.titular !== filters.titular) return false;
      if (filters.tramitante && e.tramitante !== filters.tramitante) return false;
      if (filters.pais && e.pais !== filters.pais) return false;
      if (filters.estatus && e.estatus !== filters.estatus) return false;
      if (filters.tomo && e.tomo !== filters.tomo) return false;
      if (filters.clase) {
        const cls =
          e.clase_especial === "LC" || e.class_nice === 0
            ? "LC"
            : e.class_nice != null
            ? String(e.class_nice)
            : "";
        if (cls !== filters.clase) return false;
      }
      return true;
    });
  }, [entries, searchKeys, deferredQuery, filters]);

  const setFilter = <K extends keyof EntryFilters>(k: K, v: EntryFilters[K]) =>
    setFilters((prev) => ({ ...prev, [k]: v }));
  const clearAllFilters = () => {
    setFilters(EMPTY_FILTERS);
    setEntryQuery("");
  };
  const anyFilterActive =
    entryQuery.trim() !== "" ||
    Object.values(filters).some((v) => v !== "");

  // Paginación sobre el conjunto ya filtrado.
  const entryTotalPages = Math.max(1, Math.ceil(filteredEntries.length / PAGE_SIZE));
  const safePage = Math.min(page, entryTotalPages);
  const pageStart = (safePage - 1) * PAGE_SIZE;
  const pageRows = filteredEntries.slice(pageStart, pageStart + PAGE_SIZE);

  // Volver a la página 1 cuando cambia la búsqueda o se recargan las marcas,
  // y corregir la página si excede el total (p.ej. tras filtrar).
  useEffect(() => {
    setPage((p) => Math.min(Math.max(1, p), Math.max(1, Math.ceil(filteredEntries.length / PAGE_SIZE))));
  }, [entryQuery, filteredEntries.length]);

  if (!boletin) return <div className="text-gray-500">Cargando…</div>;

  const isExtracting = boletin.status === "extracting" || progress?.status === "extracting";
  const displayStatus = progress?.status ?? boletin.status;

  const currentStep = progress?.progress_step ?? boletin.progress_step ?? null;
  const currentPage = progress?.progress_current_page ?? boletin.progress_current_page ?? null;
  const totalPages = progress?.progress_total_pages ?? boletin.progress_total_pages ?? null;
  const pctPages =
    progress?.progress_total_pages && progress?.progress_current_page != null
      ? Math.min(100, Math.round((progress.progress_current_page / progress.progress_total_pages) * 100))
      : boletin.progress_total_pages && boletin.progress_current_page != null
      ? Math.min(100, Math.round((boletin.progress_current_page / boletin.progress_total_pages) * 100))
      : null;

  const hermesActive = isHermesInProgress(boletin);

  const hermesStep = boletin.hermes_progress_step;
  const hermesCurrent = boletin.hermes_progress_current_page;
  const hermesTotal = boletin.hermes_progress_total_pages;
  const hermesPct =
    hermesTotal && hermesCurrent != null
      ? Math.min(100, Math.round((hermesCurrent / hermesTotal) * 100))
      : null;

  const handleDelete = async () => {
    if (!window.confirm(
      `¿Eliminar el boletín "${boletin.filename}" y todas sus detecciones? Esta acción no se puede deshacer.`,
    )) return;
    try {
      await request<void>(`/api/boletines/${boletin.id}`, { method: "DELETE" });
      navigate("/boletines");
    } catch (err) {
      window.alert(err instanceof Error ? err.message : "Error al eliminar");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Link to="/boletines" className="text-sm text-gray-500 hover:underline">← Boletines</Link>
        <h1 className="text-2xl font-bold">{boletin.filename}</h1>
      </div>

      {isExtracting && (
        <Card>
          <CardContent className="p-6 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{stepLabel(currentStep) || "Iniciando…"}</span>
              {currentPage != null && totalPages != null && (
                <span className="text-gray-500">
                  Página {currentPage} / {totalPages}
                </span>
              )}
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-200">
              <div
                className="h-full rounded-full bg-brand-500 transition-[width] duration-200"
                style={{ width: pctPages != null ? `${pctPages}%` : "10%" }}
                data-testid="extract-progress-bar"
              />
            </div>
            {pctPages != null && (
              <div className="text-xs text-gray-500">{pctPages}% completado</div>
            )}
          </CardContent>
        </Card>
      )}

      {hermesActive && (
        <Card className="border-purple-200 bg-purple-50">
          <CardContent className="p-6 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-purple-800">
                Analizando por Hermes Vision
              </span>
              <span className="inline-flex h-2 w-2 animate-pulse rounded-full bg-purple-500" />
            </div>
            <p className="text-xs text-purple-700">
              El boletín tiene páginas con imágenes o encoding roto.
              Hermes las está procesando con visión multimodal.
              Esta vista se actualiza automáticamente.
            </p>
            {(hermesCurrent != null && hermesTotal != null) && (
              <div className="space-y-1">
                <div className="flex items-center justify-between text-xs text-purple-700">
                  <span>
                    {hermesStep === "done" ? "Completado" : "Hermes página a página"}
                  </span>
                  <span>
                    Página {hermesCurrent} / {hermesTotal}
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-purple-100">
                  <div
                    className="h-full rounded-full bg-purple-500 transition-[width] duration-300"
                    style={{ width: hermesPct != null ? `${hermesPct}%` : "5%" }}
                    data-testid="hermes-progress-bar"
                  />
                </div>
                {hermesPct != null && hermesStep !== "done" && (
                  <div className="text-xs text-purple-700">{hermesPct}% completado</div>
                )}
              </div>
            )}
            {boletin.entries_hermes_pending > 0 && (
              <p className="text-xs text-purple-700">
                {boletin.entries_hermes_pending} entradas pendientes de revisión visual.
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Card className="p-4">
          <div className="text-sm text-gray-500">Status</div>
          <div className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${statusColor(displayStatus)}`}>
            {statusLabel(displayStatus)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-500">Páginas</div>
          <div className="mt-1 text-xl font-bold">{progress?.pages ?? boletin.pages ?? "…"}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-500">Tomo</div>
          <div className="mt-1 text-xl font-bold">{boletin.tomo ?? "—"}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-500">Entries matcheables</div>
          <div className="mt-1 text-xl font-bold">{progress?.entries_matcheables ?? boletin.entries_matcheables}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-gray-500">Figura / Lema</div>
          <div className="mt-1 text-xl font-bold">
            {progress?.entries_figura ?? boletin.entries_figura} / {progress?.entries_lema ?? boletin.entries_lema}
          </div>
        </Card>
      </div>

      {boletin.status === "extracted" && (
        <Card>
          <CardContent className="p-6 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Marcas extraídas</h2>
                <p className="text-xs text-gray-500">
                  Todas las marcas del boletín (no solo las que coinciden con tu
                  watchlist / portfolio).
                </p>
              </div>
              <Input
                placeholder="Buscar (marca, titular, expediente, país…)"
                value={entryQuery}
                onChange={(e) => setEntryQuery(e.target.value)}
                className="max-w-xs"
                aria-label="Buscar marcas"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                value={filters.marca}
                onChange={(e) => setFilter("marca", e.target.value)}
                className="h-9 max-w-[14rem] truncate rounded-md border border-input bg-transparent px-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                aria-label="Filtrar por marca"
              >
                <option value="">Marca: todas</option>
                {filterOptions.marcas.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <select
                value={filters.titular}
                onChange={(e) => setFilter("titular", e.target.value)}
                className="h-9 max-w-[14rem] truncate rounded-md border border-input bg-transparent px-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                aria-label="Filtrar por titular"
              >
                <option value="">Titular: todos</option>
                {filterOptions.titulares.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <select
                value={filters.tramitante}
                onChange={(e) => setFilter("tramitante", e.target.value)}
                className="h-9 max-w-[14rem] truncate rounded-md border border-input bg-transparent px-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                aria-label="Filtrar por tramitante"
              >
                <option value="">Tramitante: todos</option>
                {filterOptions.tramitantes.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <select
                value={filters.clase}
                onChange={(e) => setFilter("clase", e.target.value)}
                className="h-9 max-w-[8rem] rounded-md border border-input bg-transparent px-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                aria-label="Filtrar por clase"
              >
                <option value="">Clase: todas</option>
                {filterOptions.clases.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <select
                value={filters.pais}
                onChange={(e) => setFilter("pais", e.target.value)}
                className="h-9 max-w-[12rem] truncate rounded-md border border-input bg-transparent px-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                aria-label="Filtrar por país"
              >
                <option value="">País: todos</option>
                {filterOptions.paises.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              <select
                value={filters.estatus}
                onChange={(e) => setFilter("estatus", e.target.value)}
                className="h-9 max-w-[10rem] truncate rounded-md border border-input bg-transparent px-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                aria-label="Filtrar por estatus"
              >
                <option value="">Estatus: todos</option>
                {filterOptions.estatus.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <select
                value={filters.tomo}
                onChange={(e) => setFilter("tomo", e.target.value)}
                className="h-9 max-w-[8rem] rounded-md border border-input bg-transparent px-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500/30"
                aria-label="Filtrar por tomo"
              >
                <option value="">Tomo: todos</option>
                {filterOptions.tomos.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              {anyFilterActive && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={clearAllFilters}
                  aria-label="Limpiar filtros"
                >
                  Limpiar
                </Button>
              )}
            </div>

            <div className="text-sm text-gray-600">
              Mostrando {filteredEntries.length === 0 ? 0 : pageStart + 1}–
              {pageStart + pageRows.length} de {filteredEntries.length} marcas
            </div>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Marca</TableHead>
                  <TableHead>Expediente</TableHead>
                  <TableHead>Titular</TableHead>
                  <TableHead>Tramitante</TableHead>
                  <TableHead>Clase</TableHead>
                  <TableHead>País</TableHead>
                  <TableHead>Productos / Servicios</TableHead>
                  <TableHead>Estatus</TableHead>
                  <TableHead>Página</TableHead>
                  <TableHead>Tomo</TableHead>
                  <TableHead>Tipo</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageRows.map((e) => (
                  <TableRow
                    key={e.id}
                    className="cursor-pointer"
                    onClick={() => setSelectedEntry(e)}
                  >
                    <TableCell className="font-medium">{e.marca ?? "—"}</TableCell>
                    <TableCell>{e.expediente}</TableCell>
                    <TableCell>{e.titular ?? "—"}</TableCell>
                    <TableCell>{e.tramitante ?? "—"}</TableCell>
                    <TableCell>{formatClass(e.class_nice)}</TableCell>
                    <TableCell>{e.pais ?? "—"}</TableCell>
                    <TableCell className="max-w-xs">
                      <span className="line-clamp-2">
                        {e.productos_servicios || "—"}
                      </span>
                    </TableCell>
                    <TableCell>{e.estatus ?? "—"}</TableCell>
                    <TableCell>{e.page ?? "—"}</TableCell>
                    <TableCell>{e.tomo ?? "—"}</TableCell>
                    <TableCell>
                      {e.is_lema && <Badge variant="secondary">Lema</Badge>}
                      {e.is_figura && <Badge variant="outline">Figura</Badge>}
                      {e.tipo_disposicion && (
                        <span
                          className={`ml-1 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${disposicionColor(e.tipo_disposicion)}`}
                          title={e.disposicion ?? undefined}
                        >
                          {disposicionLabel(e.tipo_disposicion)}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {filteredEntries.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={11} className="text-center text-gray-500">
                      No hay marcas que coincidan
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            {filteredEntries.length > 0 && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">
                  Página {safePage} de {entryTotalPages}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={safePage <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    ‹ Anterior
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={safePage >= entryTotalPages}
                    onClick={() => setPage((p) => Math.min(entryTotalPages, p + 1))}
                  >
                    Siguiente ›
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {selectedEntry && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setSelectedEntry(null)}
        >
          <div
            className="w-full max-w-2xl rounded-lg bg-white p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-4 text-xl font-bold">{selectedEntry.marca ?? "Marca"}</h2>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <dt className="text-gray-500">Expediente:</dt><dd>{selectedEntry.expediente}</dd>
              <dt className="text-gray-500">Titular:</dt><dd>{selectedEntry.titular ?? "—"}</dd>
              <dt className="text-gray-500">Tramitante:</dt><dd>{selectedEntry.tramitante ?? "—"}</dd>
              <dt className="text-gray-500">Clase:</dt><dd>{formatClass(selectedEntry.class_nice)}</dd>
              <dt className="text-gray-500">País:</dt><dd>{selectedEntry.pais ?? "—"}</dd>
              <dt className="text-gray-500">Estatus:</dt><dd>{selectedEntry.estatus ?? "—"}</dd>
              <dt className="text-gray-500">Página:</dt><dd>{selectedEntry.page ?? "—"}</dd>
              <dt className="text-gray-500">Tomo:</dt><dd>{selectedEntry.tomo ?? "—"}</dd>
              {(selectedEntry.is_lema || selectedEntry.is_figura) && (
                <>
                  <dt className="text-gray-500">Tipo:</dt>
                  <dd>
                    {[selectedEntry.is_lema && "Lema", selectedEntry.is_figura && "Figurativa"]
                      .filter(Boolean)
                      .join(" / ")}
                  </dd>
                </>
              )}
            </dl>
            <div className="mt-4">
              <div className="text-sm text-gray-500">Productos / Servicios</div>
              <p className="mt-1 whitespace-pre-wrap text-sm text-gray-800">
                {selectedEntry.productos_servicios || "—"}
              </p>
            </div>
            {selectedEntry.tipo_disposicion && (
              <div className="mt-4">
                <div className="flex items-center gap-2">
                  <div className="text-sm text-gray-500">Disposición administrativa</div>
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ${disposicionColor(selectedEntry.tipo_disposicion)}`}>
                    {disposicionLabel(selectedEntry.tipo_disposicion)}
                  </span>
                </div>
                <p className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-700">
                  {selectedEntry.disposicion || "—"}
                </p>
              </div>
            )}
            {selectedEntry.excerpt && (
              <pre className="mt-4 max-h-60 overflow-auto rounded bg-gray-50 p-3 text-xs text-gray-700 whitespace-pre-wrap">
                {selectedEntry.excerpt}
              </pre>
            )}
            <button
              onClick={() => setSelectedEntry(null)}
              className="mt-4 text-sm text-brand-600 hover:underline"
            >
              Cerrar
            </button>
          </div>
        </div>
      )}

      {boletin.error && (
        <div className="rounded-md bg-red-50 p-4 text-sm text-red-700">{boletin.error}</div>
      )}

      {boletin.status === "extracted" && (
        <Link to={`/detections?boletin_id=${boletin.id}`}>
          <Button>Ver detecciones de este boletín</Button>
        </Link>
      )}

      {!isExtracting && !hermesActive && (
        <div className="border-t pt-6">
          <Button variant="destructive" onClick={handleDelete}>
            Eliminar boletín
          </Button>
          <p className="mt-2 text-xs text-gray-500">
            Se borra el registro, sus detecciones y el PDF si ningún otro boletín lo usa.
          </p>
        </div>
      )}
    </div>
  );
}
