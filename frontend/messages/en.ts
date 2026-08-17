/** The source of truth. Every other catalogue is typed against this one, so a
 *  key added here breaks the build until all four translations exist — which is
 *  the point: with ~96 keys the real risk is rot, not the first pass. */
export const en = {
  "nav.assistants": "Assistants",
  "nav.ask": "Ask",
  "nav.knowledge_bases": "Knowledge Bases",
  "nav.model_providers": "Model Providers",
  "nav.audit_log": "Audit log",
  "nav.diagnostics": "Diagnostics",
  "app.language": "Language",
  "source.header": "Source {index}: {filename}, page {page}",
  "verify.checked_one": "{count} number checked against sources",
  "verify.checked_other": "{count} numbers checked against sources",
} as const;

export type MessageKey = keyof typeof en;
