export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type KB = {
  id: string;
  name: string;
  description: string;
  config: { locale?: string };
  created_at: string;
};

export type Doc = {
  id: string;
  kb_id: string;
  filename: string;
  status: "queued" | "parsing" | "indexing" | "done" | "failed";
  error: string | null;
  page_count: number | null;
  created_at: string;
};

export type Citation = {
  index: number;
  kind: "text" | "table";
  doc_id: string;
  element_id: string;
  filename: string;
  page: number;
  snippet: string;
  score: number;
  needs_review: boolean;
};

export type Verification = {
  enabled: boolean;
  status: "ok" | "warnings";
  numbers: { raw: string; value: number; status: "verified" | "computed" | "unverified" }[];
  unverified: string[];
};

export type ChatEvent =
  | { type: "citations"; citations: Citation[] }
  | { type: "token"; content: string }
  | {
      type: "done";
      session_id: string;
      message_id: string;
      verification: Verification | null;
    }
  | { type: "error"; message: string };

export type RecordEdit = {
  dimensions: Record<string, unknown>;
  metrics: Record<string, unknown>;
  raw_values: Record<string, unknown>;
};

export type ElementDetail = {
  id: string;
  doc_id: string;
  filename: string;
  page: number;
  type: "text" | "table" | "figure";
  confidence: number | null;
  needs_review: boolean;
  edited: boolean;
  crop_url: string;
  text: string | null;
  table: {
    html: string | null;
    summary: string | null;
    n_rows: number | null;
    n_cols: number | null;
    parse_strategy: string | null;
    records: RecordEdit[];
  } | null;
};

export type ElementEdit = {
  text?: string;
  html?: string;
  summary?: string;
  records?: RecordEdit[];
};

export type RecordPreview = {
  dimensions: Record<string, string>;
  metrics: Record<string, number | null>;
  raw_values: Record<string, string>;
};

export type ConfidenceDetail = {
  signals?: Record<string, number>;
  confidence?: number;
  arithmetic?: { checks: number; passed: number };
  agreement?: { cells_first: number; cells_second: number; agreed: number };
};

export type ElementView = {
  id: string;
  page: number;
  type: "text" | "table" | "figure";
  confidence: number | null;
  needs_review: boolean;
  parse_error: string | null;
  caption: string | null;
  ocr: boolean;
  unusable: boolean;
  edited: boolean;
  confidence_detail: ConfidenceDetail | null;
  span_pages: number[] | null;
  chunk_count: number;
  text_preview: string | null;
  crop_url: string;
  table: {
    html: string | null;
    summary: string | null;
    n_rows: number | null;
    n_cols: number | null;
    parse_strategy: string | null;
    records_count: number;
    records_preview: RecordPreview[];
  } | null;
};

export type DocumentView = { document: Doc; elements: ElementView[] };

export const getDocumentView = (docId: string) =>
  fetch(`${API_URL}/api/documents/${docId}/elements`, { cache: "no-store" }).then(
    (r) => jsonOrThrow<DocumentView>(r),
  );

export type ModelRole = {
  role: "parser" | "embedder" | "chat" | "reranker";
  provider: "ollama" | "openai_compat" | "disabled";
  base_url: string;
  model_name: string;
  overridden: boolean;
  ok: boolean;
  detail: string;
};

export type OllamaModel = {
  name: string;
  size_bytes: number | null;
  parameter_size: string | null;
};

export type PullEvent =
  | { type: "progress"; status: string; total: number | null; completed: number | null }
  | { type: "done"; name: string }
  | { type: "error"; message: string };

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = await res.text();
    try {
      detail = JSON.parse(detail).detail ?? detail;
    } catch {}
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---------- knowledge bases ----------

export const getKbs = () =>
  fetch(`${API_URL}/api/kbs`, { cache: "no-store" }).then((r) => jsonOrThrow<KB[]>(r));

export const getKb = (kbId: string) =>
  fetch(`${API_URL}/api/kbs/${kbId}`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<KB>(r),
  );

export const createKb = (
  name: string,
  description: string,
  locale: string | null,
  verify: boolean,
) =>
  fetch(`${API_URL}/api/kbs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, locale, verify }),
  }).then((r) => jsonOrThrow<KB>(r));

// ---------- documents ----------

export const getDocs = (kbId: string) =>
  fetch(`${API_URL}/api/kbs/${kbId}/documents`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<Doc[]>(r),
  );

export const uploadDoc = (kbId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API_URL}/api/kbs/${kbId}/documents`, {
    method: "POST",
    body: form,
  }).then((r) => jsonOrThrow<Doc>(r));
};

export const deleteDoc = (docId: string) =>
  fetch(`${API_URL}/api/documents/${docId}`, { method: "DELETE" }).then((r) => {
    if (!r.ok && r.status !== 204) throw new Error(`delete failed: ${r.status}`);
  });

export const pageImageUrl = (docId: string, page: number) =>
  `${API_URL}/api/documents/${docId}/pages/${page}/image`;

// ---------- elements (citation click-through) ----------

export const getElement = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<ElementDetail>(r),
  );

export const elementImageUrl = (elementId: string) =>
  `${API_URL}/api/elements/${elementId}/image`;

// review flow (Phase 3): approve clears the flag; unusable removes the
// element's records from retrieval while keeping the original image
export const approveElement = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}/approve`, { method: "POST" }).then(
    (r) => jsonOrThrow<unknown>(r),
  );

export const markElementUnusable = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}/unusable`, { method: "POST" }).then(
    (r) => jsonOrThrow<unknown>(r),
  );

export const editElement = (elementId: string, edit: ElementEdit) =>
  fetch(`${API_URL}/api/elements/${elementId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(edit),
  }).then((r) => jsonOrThrow<ElementDetail>(r));

export const bulkDeleteDocs = (kbId: string, docIds: string[]) =>
  fetch(`${API_URL}/api/kbs/${kbId}/documents/bulk-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_ids: docIds }),
  }).then((r) => jsonOrThrow<{ deleted: number }>(r));

// ---------- chat (SSE) ----------

async function* sseStream<T>(res: Response): AsyncGenerator<T> {
  if (!res.ok || !res.body) throw new Error(`request failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.trim();
      if (line.startsWith("data:")) yield JSON.parse(line.slice(5).trim()) as T;
    }
  }
}

export async function* chatStream(
  kbId: string,
  question: string,
  sessionId: string | null,
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_URL}/api/kbs/${kbId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  yield* sseStream<ChatEvent>(res);
}

// ---------- model roles ----------

export const getModelRoles = () =>
  fetch(`${API_URL}/api/models`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<ModelRole[]>(r),
  );

export const updateModelRole = (
  role: string,
  changes: Partial<Pick<ModelRole, "provider" | "base_url" | "model_name">>,
) =>
  fetch(`${API_URL}/api/models/${role}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  }).then((r) => jsonOrThrow<ModelRole>(r));

export const getAvailableModels = (role: string) =>
  fetch(`${API_URL}/api/models/${role}/available`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<OllamaModel[]>(r),
  );

export async function* pullModel(
  role: string,
  name: string,
): AsyncGenerator<PullEvent> {
  const res = await fetch(`${API_URL}/api/models/${role}/pull`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  yield* sseStream<PullEvent>(res);
}

// ---------- diagnostics ----------

export type DetectedTable = {
  bbox: number[];
  rows: number;
  cols: number;
  fill?: number;
  accept?: boolean;
  complex?: boolean;
};

export type PageDiagnostic = {
  width: number;
  height: number;
  text_chars: number;
  strategies: Record<
    string,
    { count?: number; tables?: DetectedTable[]; error?: string }
  >;
  kept: DetectedTable[];
};

export type VlmDetection = {
  page: number;
  count: number;
  boxes: number[][];
  raw: string;
};

export type TableDiagnostics = {
  filename: string;
  page_count: number;
  pages: PageDiagnostic[];
  vlm?: VlmDetection;
};

export const diagnoseTableDetection = (file: File, vlmPage?: number) => {
  const form = new FormData();
  form.append("file", file);
  if (vlmPage != null) form.append("vlm_page", String(vlmPage));
  return fetch(`${API_URL}/api/diagnostics/table-detection`, {
    method: "POST",
    body: form,
  }).then((r) => jsonOrThrow<TableDiagnostics>(r));
};

export const formatBytes = (n: number | null) => {
  if (!n) return "";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(1)} ${units[i]}`;
};
