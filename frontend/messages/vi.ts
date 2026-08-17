import type { MessageKey } from "@/messages/en";

// Vietnamese does not mark plural number. The _one and _other forms below are
// identical on purpose — that is the language, not an unfinished translation.
export const vi: Record<MessageKey, string> = {
  "nav.assistants": "Trợ lý",
  "nav.ask": "Hỏi",
  "nav.knowledge_bases": "Kho tri thức",
  "nav.model_providers": "Nhà cung cấp mô hình",
  "nav.audit_log": "Nhật ký kiểm toán",
  "nav.diagnostics": "Chẩn đoán",
  "app.language": "Ngôn ngữ",
  "source.header": "Nguồn {index}: {filename}, trang {page}",
  "verify.checked_one": "Đã đối chiếu {count} con số với nguồn",
  "verify.checked_other": "Đã đối chiếu {count} con số với nguồn",
};
