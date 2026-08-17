export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type KBDocStatus = {
  total: number;
  processing: number; // queued + parsing + indexing
  done: number;
  failed: number;
};

export type KB = {
  id: string;
  name: string;
  description: string;
  config: {
    locale?: string;
    verify?: boolean;
    instructions?: string;
    escalation_contact?: string;
  };
  created_at: string;
  doc_status?: KBDocStatus | null; // set by the list endpoint only
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
  /** this source's text is the parser model's reading of a picture, not text
   *  extracted from the page */
  from_figure: boolean;
  /** pulled in because it neighbours a retrieved source, not because search
   *  found it - a reader must be able to tell the two apart */
  expanded: boolean;
};

/** Why an answer deserves a second look, and who to ask. `reasons` are stable
 *  machine keys rendered into French by the UI, never prose from the model. */
export type Caution = {
  reasons: string[];
  contact: string | null;
};

/** Printed on a page the answer used, offered to be LOOKED at. Never a source:
 *  the model was not shown it and cannot have used it, so it is never numbered
 *  beside the citations — a figure's numbers live in its drawing, and its
 *  description loses to the page's own prose for a question phrased in that
 *  prose's words, so ranking alone will not surface it. */
export type SeeAlso = {
  kind: "figure" | "table";
  doc_id: string;
  filename: string;
  page: number;
  element_id: string;
  crop_image_path: string | null;
  context: string;
};

export type Verification = {
  enabled: boolean;
  status: "ok" | "warnings";
  numbers: { raw: string; value: number; status: "verified" | "computed" | "unverified" }[];
  unverified: string[];
};

export type ChatEvent =
  | { type: "citations"; citations: Citation[] }
  | { type: "caution"; caution: Caution }
  | { type: "token"; content: string }
  | {
      type: "done";
      session_id: string;
      message_id: string;
      verification: Verification | null;
      see_also?: SeeAlso[];
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
  /** everything ingestion recorded about this element. A figure's
   *  `description` lives here — `text` below is the INDEXED blob, which is the
   *  heading above it and its measured palette prefixed to that description. */
  meta: Record<string, unknown> | null;
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
  description: string | null;
  decorative: boolean;
  chart_check: string | null;
  /** how many edits can still be taken back */
  undo_steps: number;
  ocr: boolean;
  layout_suspect: boolean;
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

// ---------- auth / audit (Phase 5) ----------

export type Me = { username: string; email: string | null; is_admin: boolean };

export const getMe = () =>
  fetch(`${API_URL}/api/me`, { cache: "no-store" }).then((r) => jsonOrThrow<Me>(r));

export type AuditEvent = {
  actor: string;
  action: string;
  kb_id: string | null;
  doc_id: string | null;
  detail: Record<string, unknown> | null;
  created_at: string;
};

export const getAudit = () =>
  fetch(`${API_URL}/api/audit`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<{ events: AuditEvent[] }>(r),
  );

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

export const reprocessDoc = (docId: string) =>
  fetch(`${API_URL}/api/documents/${docId}/reprocess`, { method: "POST" }).then(
    (r) => jsonOrThrow<Doc>(r),
  );

/** Re-run ingestion for several documents. They are queued, not run at once —
 * the worker takes them one at a time. Documents already in flight are skipped. */
export const bulkReprocessDocs = (kbId: string, docIds: string[]) =>
  fetch(`${API_URL}/api/kbs/${kbId}/documents/bulk-reprocess`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_ids: docIds }),
  }).then((r) => jsonOrThrow<{ queued: number; skipped: number }>(r));

export const pageImageUrl = (docId: string, page: number) =>
  `${API_URL}/api/documents/${docId}/pages/${page}/image`;

/** Everything ingestion produced for a document, as plain text — the raw
 * HTML, records and chunks, for showing a parse to someone who can act on it. */
export const documentExportUrl = (docId: string) =>
  `${API_URL}/api/documents/${docId}/export`;

export const documentOriginalUrl = (docId: string) =>
  `${API_URL}/api/documents/${docId}/original`;

export type BoilerplateCandidate = {
  element_id: string;
  page: number;
  reason: string;
  text: string;
};

/** Drop everything parsed from one page (a cover, a signature page, a list of
 * repealed agreements). The original file stays, so Reprocess brings it back. */
export const deletePage = (docId: string, page: number) =>
  fetch(`${API_URL}/api/documents/${docId}/pages/${page}`, {
    method: "DELETE",
  }).then((r) => jsonOrThrow<{ deleted: number; page: number }>(r));

/** Drop one parsed element. Reversible by reprocessing the document. */
export const deleteElement = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}`, { method: "DELETE" }).then(
    (r) => {
      if (!r.ok && r.status !== 204) throw new Error(`delete failed: ${r.status}`);
    },
  );

export const scanBoilerplate = (docId: string) =>
  fetch(`${API_URL}/api/documents/${docId}/boilerplate-scan`, {
    method: "POST",
  }).then((r) => jsonOrThrow<BoilerplateCandidate[]>(r));

export const excludeBoilerplate = (docId: string, elementIds: string[]) =>
  fetch(`${API_URL}/api/documents/${docId}/boilerplate-exclude`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ element_ids: elementIds }),
  }).then((r) => jsonOrThrow<{ excluded: number }>(r));

// ---------- elements (citation click-through) ----------

export const getElement = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<ElementDetail>(r),
  );

export type AssistTurn = { role: "user" | "assistant"; content: string };

/** Editing assistant for the content open in the editor. It may rearrange what
 * you give it but never add facts; when it changes something it returns the
 * complete new version as a proposal you apply by hand. */
export const assistElementEdit = (
  elementId: string,
  body: {
    instruction: string;
    format: "html" | "text" | "records" | "summary";
    content: string;
    history: AssistTurn[];
  },
) =>
  fetch(`${API_URL}/api/elements/${elementId}/assist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => jsonOrThrow<{ reply: string; proposal: string | null }>(r));

/** Rebuild a table's records and summary from HTML being edited (unsaved).
 * Records come out deterministically from the HTML; the summary is regenerated
 * because it describes a table that just changed. A proposal, not a write. */
export const deriveFromHtml = (elementId: string, html: string) =>
  fetch(`${API_URL}/api/elements/${elementId}/derive`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html }),
  }).then((r) =>
    jsonOrThrow<{
      records: RecordEdit[];
      summary: string;
      rows: number;
      cols: number;
    }>(r),
  );

export type TableRecheck = {
  html: string;
  records: RecordEdit[];
  confidence: number;
  signals: Record<string, number>;
  second_read: boolean;
  findings: string;
  clean: boolean;
  dpi: number | null;
  stitched: boolean;
  grid_hint: boolean;
  error: string | null;
};

/** Parse a table again, harder: double the ingest DPI, the text-layer grid as a
 * hint, and two independent reads scored against each other. A PROPOSAL —
 * nothing is written until the reviewer saves it. */
export const recheckElement = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}/recheck`, { method: "POST" }).then(
    (r) => jsonOrThrow<TableRecheck>(r),
  );

/** "This is not a table": demote a wrongly detected table to a text element.
 * Its cells' own words become the text and it is re-indexed; reprocessing the
 * document restores the table if detection was right after all. */
export const convertElementToText = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}/convert-to-text`, {
    method: "POST",
  }).then((r) => jsonOrThrow<ElementDetail>(r));

/** "These are two tables": break a region detection drew around both. The
 * model is asked only where the seam is; each part is re-parsed and gets its
 * own bbox and crop. Undo puts the single table back. */
export const splitElementTable = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}/split`, { method: "POST" }).then(
    (r) => jsonOrThrow<ElementDetail & { parts: number; reason: string }>(r),
  );

/** "These are one table": join the picked tables and re-parse, in document
 * order. The inverse of splitElementTable. The first keeps its identity and
 * undo restores it; the others are gone until the document is reprocessed. */
export const mergeElementTables = (ids: string[]) =>
  fetch(`${API_URL}/api/elements/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  }).then((r) => jsonOrThrow<ElementDetail & { reason: string }>(r));

/** "This text is a table": promote it, from markdown or HTML. The source is
 * what is open in the editor, unsaved, so it travels with the request. */
export const convertElementToTable = (elementId: string, source: string) =>
  fetch(`${API_URL}/api/elements/${elementId}/to-table`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source }),
  }).then((r) => jsonOrThrow<ElementDetail & { reason: string }>(r));

/** Draw repeated values as one merged cell, or as one cell per row. Display
 * only: records come from a forward-filled grid, so every row already carries
 * its own value whichever way the HTML is written. */
export const setElementRowMerging = (elementId: string, merged: boolean) =>
  fetch(
    `${API_URL}/api/elements/${elementId}/row-merging?merged=${merged}`,
    { method: "POST" },
  ).then((r) => jsonOrThrow<ElementDetail>(r));

/** Put an element back the way it was before its last edit, and re-index.
 * Reprocessing the document undoes anything, but re-runs the whole file and
 * discards every other correction made to it. */
export const undoElementEdit = (elementId: string) =>
  fetch(`${API_URL}/api/elements/${elementId}/undo`, { method: "POST" }).then(
    (r) => jsonOrThrow<ElementDetail & { undone: string }>(r),
  );

/** How the VLM should re-read a page: a faithful transcription that keeps a
 * grid as a markdown table, an explanation of what the page says, or both. */
export type RereadMode = "structure" | "summary" | "both";

/** Ask the parser VLM to re-read this element's page. Returns a PROPOSAL —
 * nothing is written until the reviewer saves it through the element editor. */
export const rereadElement = (elementId: string, mode: RereadMode = "structure") =>
  fetch(`${API_URL}/api/elements/${elementId}/reread?mode=${mode}`, {
    method: "POST",
  }).then((r) => jsonOrThrow<{ text: string; mode: RereadMode }>(r));

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

// ---------- multi-KB chat (Phase 5 router) ----------

export type RoutingInfo = {
  mode: "single" | "pinned" | "trivial" | "llm" | "fallback_all";
  kb_ids: string[];
  names?: string[] | null;
  candidates?: number;
};

export type MultiChatEvent =
  | { type: "citations"; citations: Citation[] }
  | { type: "caution"; caution: Caution }
  | { type: "token"; content: string }
  | {
      type: "done";
      session_id: string;
      message_id: string;
      routing: RoutingInfo | null;
      verification: Verification | null;
      see_also?: SeeAlso[];
    }
  | { type: "error"; message: string };

// kbIds null => let the router pick; a list => pin those KBs (manual override)
export async function* chatMultiStream(
  question: string,
  kbIds: string[] | null,
  sessionId: string | null,
): AsyncGenerator<MultiChatEvent> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, kb_ids: kbIds, session_id: sessionId }),
  });
  yield* sseStream<MultiChatEvent>(res);
}

// ---------- assistants (chat apps with their own KBs + prompt) ----------

export type Assistant = {
  id: string;
  name: string;
  description: string;
  instructions: string;
  kb_ids: string[];
  kb_names: string[];
  opening_message: string;
  verify: boolean | null;
  created_at: string;
};

export type AssistantInput = Partial<{
  name: string;
  description: string;
  instructions: string;
  kb_ids: string[];
  opening_message: string;
  verify: boolean | null;
}>;

export type Conversation = {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  verification: Verification | null;
  feedback: -1 | 0 | 1;
};

export const getAssistants = () =>
  fetch(`${API_URL}/api/assistants`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<Assistant[]>(r),
  );

export const getAssistant = (id: string) =>
  fetch(`${API_URL}/api/assistants/${id}`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<Assistant>(r),
  );

export const createAssistant = (body: AssistantInput) =>
  fetch(`${API_URL}/api/assistants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => jsonOrThrow<Assistant>(r));

export const updateAssistant = (id: string, body: AssistantInput) =>
  fetch(`${API_URL}/api/assistants/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => jsonOrThrow<Assistant>(r));

export const deleteAssistant = (id: string) =>
  fetch(`${API_URL}/api/assistants/${id}`, { method: "DELETE" }).then((r) => {
    if (!r.ok && r.status !== 204) throw new Error(`delete failed: ${r.status}`);
  });

export async function* assistantChatStream(
  assistantId: string,
  question: string,
  sessionId: string | null,
): AsyncGenerator<MultiChatEvent> {
  const res = await fetch(`${API_URL}/api/assistants/${assistantId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  yield* sseStream<MultiChatEvent>(res);
}

export const getConversations = (assistantId: string) =>
  fetch(`${API_URL}/api/assistants/${assistantId}/conversations`, {
    cache: "no-store",
  }).then((r) => jsonOrThrow<Conversation[]>(r));

export const getConversationMessages = (sessionId: string) =>
  fetch(`${API_URL}/api/conversations/${sessionId}/messages`, {
    cache: "no-store",
  }).then((r) =>
    jsonOrThrow<{ session_id: string; title: string; messages: StoredMessage[] }>(r),
  );

export const renameConversation = (sessionId: string, title: string) =>
  fetch(`${API_URL}/api/conversations/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  }).then((r) => jsonOrThrow<Conversation>(r));

export const deleteConversation = (sessionId: string) =>
  fetch(`${API_URL}/api/conversations/${sessionId}`, { method: "DELETE" }).then(
    (r) => {
      if (!r.ok && r.status !== 204)
        throw new Error(`delete failed: ${r.status}`);
    },
  );

export type ReviewItem = {
  element_id: string;
  doc_id: string;
  filename: string;
  page: number;
  type: string;
  confidence: number | null;
};

export const getNeedsReview = (kbId: string) =>
  fetch(`${API_URL}/api/kbs/${kbId}/needs-review`, { cache: "no-store" }).then(
    (r) => jsonOrThrow<{ count: number; items: ReviewItem[] }>(r),
  );

export const sendFeedback = (messageId: string, value: -1 | 0 | 1) =>
  fetch(`${API_URL}/api/messages/${messageId}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ value }),
  }).then((r) => jsonOrThrow<{ value: number | null }>(r));

export const suggestDescription = (kbId: string) =>
  fetch(`${API_URL}/api/kbs/${kbId}/suggest-description`, {
    method: "POST",
  }).then((r) => jsonOrThrow<{ description: string }>(r));

export const updateKb = (
  kbId: string,
  changes: Partial<{
    name: string;
    description: string;
    locale: string;
    verify: boolean;
    instructions: string;
    escalation_contact: string;
  }>,
) =>
  fetch(`${API_URL}/api/kbs/${kbId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(changes),
  }).then((r) => jsonOrThrow<KB>(r));

export const deleteKb = (kbId: string) =>
  fetch(`${API_URL}/api/kbs/${kbId}`, { method: "DELETE" }).then((r) => {
    if (!r.ok && r.status !== 204) throw new Error(`delete failed: ${r.status}`);
  });

// ---------- global chat instructions (admin) ----------

export type ChatPersona = { identity: string; text: string };

export const getChatInstructions = () =>
  fetch(`${API_URL}/api/settings/chat-instructions`, { cache: "no-store" }).then(
    (r) => jsonOrThrow<ChatPersona>(r),
  );

export const setChatInstructions = (persona: ChatPersona) =>
  fetch(`${API_URL}/api/settings/chat-instructions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(persona),
  }).then((r) => jsonOrThrow<ChatPersona>(r));

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
