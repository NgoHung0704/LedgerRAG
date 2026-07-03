export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type KB = {
  id: string;
  name: string;
  description: string;
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
  doc_id: string;
  filename: string;
  page: number;
  snippet: string;
  score: number;
  needs_review: boolean;
};

export type ChatEvent =
  | { type: "citations"; citations: Citation[] }
  | { type: "token"; content: string }
  | { type: "done"; session_id: string; message_id: string }
  | { type: "error"; message: string };

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export const getKbs = () =>
  fetch(`${API_URL}/api/kbs`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<KB[]>(r),
  );

export const createKb = (name: string, description: string) =>
  fetch(`${API_URL}/api/kbs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
  }).then((r) => jsonOrThrow<KB>(r));

export const getKb = (kbId: string) =>
  fetch(`${API_URL}/api/kbs/${kbId}`, { cache: "no-store" }).then((r) =>
    jsonOrThrow<KB>(r),
  );

export const getDocs = (kbId: string) =>
  fetch(`${API_URL}/api/kbs/${kbId}/documents`, { cache: "no-store" }).then(
    (r) => jsonOrThrow<Doc[]>(r),
  );

export const uploadDoc = (kbId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return fetch(`${API_URL}/api/kbs/${kbId}/documents`, {
    method: "POST",
    body: form,
  }).then((r) => jsonOrThrow<Doc>(r));
};

export const pageImageUrl = (docId: string, page: number) =>
  `${API_URL}/api/documents/${docId}/pages/${page}/image`;

/** POST the question and yield parsed SSE events as they stream in. */
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
  if (!res.ok || !res.body) {
    throw new Error(`chat request failed: ${res.status}`);
  }
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
      if (line.startsWith("data:")) {
        yield JSON.parse(line.slice(5).trim()) as ChatEvent;
      }
    }
  }
}
