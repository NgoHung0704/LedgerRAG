# SPEC — Nền tảng RAG tài liệu đa ngôn ngữ (codename: LedgerRAG)

> *LedgerRAG* là codename tạm, đổi tùy ý. Đây là một **nền tảng** self-hosted mở
> (theo mô hình Dify/RAGFlow): kỹ sư triển khai tự chọn model, chọn local hay API,
> chọn phần cứng. Spec mô tả *khả năng của nền tảng*, không giả định một cấu hình
> cứng — ngoại trừ Phụ lục A ghi lại **cấu hình tham chiếu** thực tế đang dùng trên
> máy nội bộ của chủ dự án (đúng, nhưng chỉ là một ví dụ trong nhiều cấu hình khả dĩ).

> Tài liệu này là nguồn sự thật duy nhất (single source of truth) cho việc triển khai.
> Người thực thi (Claude Code) phải đọc toàn bộ trước khi viết code, và tuân thủ
> **thứ tự phase** — không được làm trước phase sau khi phase trước chưa đạt
> Definition of Done (DoD).

---

## 0. Bối cảnh & mục tiêu sản phẩm

### 0.1 Sản phẩm là gì

Một nền tảng RAG self-hosted (kiểu Dify/RAGFlow) cho phép người dùng **không phải
engineer** upload tài liệu PDF **đa ngôn ngữ** vào các knowledge base (KB), sau đó
chat hỏi đáp với citation. Điểm khác biệt cạnh tranh (moat) duy nhất: **xử lý chính
xác bảng biểu phức tạp trong PDF** — bảng pivot lồng nhau, header phân cấp nhiều tầng,
ô gộp (rowspan/colspan), mỗi ô chứa nhiều chỉ số — thứ mà Dify và RAGFlow
(DeepDoc) hiện làm sai hoặc mất cấu trúc. Đa ngôn ngữ là năng lực nền (hỗ trợ tốt
các ngôn ngữ chính, xem C2); xử lý bảng là thứ tạo lợi thế.

### 0.2 Khách hàng & lộ trình domain

1. **HR** — *deployment tham chiếu đầu tiên = công ty của chính chủ dự án
   (thị trường Pháp, tài liệu tiếng Pháp)*: bảng đơn giản là chủ yếu, nhiều
   text chính sách. Đây là môi trường dogfood để tôi luyện, không phải giới hạn
   ngôn ngữ của sản phẩm.
2. Báo cáo doanh nghiệp (pivot lồng nhau — sweet spot của moat).
3. Tài liệu kỹ thuật (bảng rộng, đơn vị đo quan trọng; flowchart **out of scope**).
4. Tài chính (khó nhất, để cuối).

MVP chỉ cần phục vụ tốt deployment HR tham chiếu, nhưng nền tảng **vốn đa ngôn ngữ
ngay từ thiết kế** (không hardcode một locale), và kiến trúc không được chặn đường
lên các domain/ngôn ngữ sau.

### 0.3 Triết lý sản phẩm — PHẢI thấm vào mọi quyết định

**"Parse đúng, HOẶC thất bại một cách trung thực."**

Với sản phẩm hỏi đáp số liệu, một con số sai âm thầm tệ hơn nhiều so với việc
hệ thống nói "tôi không chắc, đây là ảnh bảng gốc". Vì vậy:

- Mọi bảng đều lưu kèm **ảnh crop gốc** — không có ngoại lệ.
- Mọi kết quả parse đều có **confidence flag**.
- Khi không chắc → hiển thị ảnh gốc + nói rõ không chắc, **không bao giờ bịa số**.

Đây là tính năng bán được tiền, không phải afterthought. Nếu phải đánh đổi
giữa "trả lời được nhiều hơn" và "không bao giờ sai số", chọn vế sau.

---

## 1. Ràng buộc cứng (non-negotiable constraints)

| # | Ràng buộc | Hệ quả kỹ thuật |
|---|-----------|------------------|
| C1 | **Chủ quyền dữ liệu (data residency)**: nhiều khách (điển hình HR/GDPR) yêu cầu dữ liệu không rời hạ tầng | Nền tảng **phải chạy được hoàn toàn local**. Provider API là *tùy chọn* cắm thêm, người triển khai bật/tắt được; ở chế độ local-only không được có bất kỳ call nào ra ngoài trong đường dữ liệu. |
| C2 | **Đa ngôn ngữ**: tài liệu và câu hỏi có thể ở nhiều ngôn ngữ | Bộ ngôn ngữ chính cần hỗ trợ tốt: **Anh, Pháp, Đức, Tây Ban Nha, Ý, Bồ Đào Nha**, và CJK (Trung/Nhật/Hàn) + Ả Rập ở mức model cho phép. Embedding/LLM phải là loại multilingual mạnh, **cấu hình được** (xem C3). Hệ quả kỹ thuật quan trọng: **định dạng số theo locale khác nhau** — Pháp `7 462 639,50` (space nghìn, phẩy thập phân), Đức `7.462.639,50` (chấm nghìn, phẩy thập phân), Anh/Mỹ `7,462,639.50`. Việc chuẩn hóa số phải **locale-aware**, không hardcode một quy ước, và có test cho từng locale. |
| C3 | **Phần cứng & model do kỹ sư triển khai tự cấu hình** (giống Dify/RAGFlow) | Nền tảng **model-agnostic và hardware-agnostic**. Kỹ sư chọn: model nào cho từng vai trò (parse/embed/chat/rerank), local (Ollama/vLLM/llama.cpp) hay API, chạy trên GPU nào (NVIDIA/AMD/…), gán vai trò cho device ra sao. Nền tảng **không được hardcode** tên model, endpoint, hay device — tất cả qua config/UI admin. Cấu hình tham chiếu AMD của máy nội bộ nằm ở Phụ lục A như một ví dụ đã kiểm chứng, không phải yêu cầu. |
| C4 | **Người dùng cuối không phải engineer** | UI phải tự giải thích; trạng thái ingestion phải hiện rõ; lỗi phải human-readable. (Người *cài đặt* là kỹ sư; người *dùng* thì không.) |
| C5 | **Flowchart/diagram: out of scope** | Lưu ảnh + caption, đánh dấu `figure`, không bóc số liệu, không hứa hỗ trợ. |

### Mô hình cấu hình model & tài nguyên (không hardcode)

Nền tảng định nghĩa **bốn vai trò model** trừu tượng, mỗi vai trò được kỹ sư
triển khai ánh xạ tới một *endpoint* cụ thể qua config/UI admin:

| Vai trò | Dùng khi | Ví dụ lựa chọn (kỹ sư tự quyết) |
|---------|----------|--------------------------------|
| `parser` (VLM) | ingestion, bóc bảng/scan | Qwen2.5-VL, InternVL, Pixtral… hoặc API document-AI |
| `embedder` | index + query | bge-m3, multilingual-e5, hoặc API embedding |
| `chat` (LLM) | sinh câu trả lời, summary | model multilingual bất kỳ, local hoặc API |
| `reranker` | (tùy chọn) rerank | bge-reranker-v2-m3… hoặc bỏ trống |

Mỗi endpoint khai báo: `provider` (ollama | openai_compat | …), `base_url`,
`model_name`, và **tùy chọn** ràng buộc tài nguyên (ví dụ biến môi trường
`*_VISIBLE_DEVICES` để ghim GPU, hoặc để trống cho backend tự lo). Việc gán
vai trò nào lên GPU nào, hay dồn nhiều vai trò một GPU, hay chạy tất cả qua API
— **là quyết định của người triển khai, không phải của code**. Nền tảng chỉ
cung cấp khả năng cấu hình và kiểm tra sức khỏe endpoint.

> Cấu hình cụ thể đã kiểm chứng cho máy nội bộ (3× AMD RX 9070 XT) — gồm cả
> lưu ý ROCm 7 / Vulkan cho RDNA4 — nằm ở **Phụ lục A**. Dùng nó như điểm khởi
> đầu, không phải mặc định bắt buộc.

---

## 2. Nguyên tắc kiến trúc (4 nguyên tắc — vi phạm là reject PR)

1. **Storage layer là hợp đồng duy nhất.** Ingestion pipeline (ghi) và Query
   pipeline (đọc) KHÔNG gọi nhau. Chúng chỉ giao tiếp qua Postgres + Qdrant +
   object storage. Nhờ vậy: reprocess toàn bộ tài liệu (đổi VLM, sửa logic)
   không đụng phần chat; test hai nửa độc lập.
2. **Record tách `dimensions` / `metrics`.** Mỗi ô số liệu trong bảng trở thành
   một record với dimensions (các chiều: vùng, nước, sản phẩm, năm, tháng...)
   và metrics (giá trị số đã chuẩn hóa) tách bạch. Đây là nền cho độ chính xác
   và cho structured query sau này.
3. **Mọi element trỏ về nguồn gốc.** Element nào cũng có `doc_id, page, bbox,
   crop_image_path, confidence`. Truy vết ngược từ câu trả lời → record →
   bảng → ảnh crop → trang PDF phải luôn khả thi.
4. **Router và Verification là pluggable steps, không hardcode.** Query pipeline
   là một chuỗi step có interface rõ; MVP dùng no-op router (1 KB) và
   verification tắt/bật được, nhưng chỗ cắm phải tồn tại từ Phase 1.

### Design note — Phân tách KB & router (ý tưởng nền của sản phẩm)

Đây là nguyên lý gốc, cần nêu tường minh vì nó chi phối cả retrieval:

- **Mỗi KB là một kho tách biệt.** Người dùng chủ động đưa các nguồn *không liên
  quan nhau* vào các KB khác nhau. Sự cô lập này **tự nó cải thiện độ chính xác
  truy xuất**: index nhỏ, đồng nhất chủ đề → ít nhiễu chéo, embedding phân biệt
  tốt hơn, và câu hỏi chỉ chạm đúng vùng dữ liệu liên quan thay vì cạnh tranh
  với hàng nghìn vector không liên quan.
- **Mỗi KB có `description`** (trường đã có trong schema từ Phase 1) — đây là
  nhãn để router biết KB chứa gì.
- **Router** đọc câu hỏi + tập description → chọn (những) KB để truy vấn. Toàn
  bộ retrieval sau đó **filter theo `kb_id`** (payload filter ở Qdrant), nên
  việc chọn đúng KB trực tiếp thu hẹp không gian tìm kiếm → chính xác hơn.

**Vì sao router nằm ở Phase 5 chứ không sớm hơn:** nguyên tắc xuyên suốt là
*chất lượng retrieval trước, orchestration sau*. Router chọn sai là điểm chết
đã biết; xây nó khi retrieval một-KB chưa vững chỉ che mất lỗi thật. Nhưng
**nền móng cho nó có từ Phase 1**: KB được cô lập, `description` tồn tại, mọi
vector mang `kb_id`, và `Router` là một step pluggable (`SingleKBRouter` no-op
lúc đầu). Nhờ vậy khi tới Phase 5, thêm `LLMRouter` là *cắm vào*, không phải
sửa lại kiến trúc. Xem chi tiết chiến lược chống route-sai ở Phase 5.

---

## 3. Kiến trúc tổng thể

```
                          ┌─────────────────────────┐
                          │        Frontend          │
                          │  (Next.js, self-host)    │
                          └─────┬──────────┬─────────┘
                                │          │
                     upload/status      chat (SSE stream)
                                │          │
                          ┌─────▼──────────▼─────────┐
                          │     API Gateway           │
                          │      (FastAPI)            │
                          └─────┬──────────┬─────────┘
                          enqueue job    query pipeline
                                │          │
              ┌─────────────────▼──┐   ┌──▼───────────────────┐
              │ INGESTION PIPELINE │   │   QUERY PIPELINE      │
              │  (Celery worker)   │   │  (in-process, async)  │
              │                    │   │                       │
              │ 1. layout parse    │   │ 1. router (pluggable) │
              │ 2. route by type   │   │ 2. hybrid retrieve    │
              │ 3. table subpipe   │   │ 3. rerank             │
              │ 4. FR num normal.  │   │ 4. assemble context   │
              │ 5. confidence      │   │ 5. generate (stream)  │
              │ 6. embed + index   │   │ 6. verify (toggle)    │
              └─────────┬──────────┘   └──▲───────────────────┘
                        │ write only       │ read only
                 ┌──────▼──────────────────┴──────┐
                 │          STORAGE LAYER          │
                 │  Postgres  │  Qdrant  │  MinIO/ │
                 │  (metadata,│ (vectors)│  local  │
                 │   records) │          │  files  │
                 └────────────────────────────────┘
                        ▲
                 ┌──────┴───────────────────────────┐
                 │        MODEL LAYER (pluggable)    │
                 │ ModelProvider interface:          │
                 │  parse_table / embed / chat /     │
                 │  rerank                           │
                 │ impl: OllamaProvider (default),   │
                 │       OpenAICompatProvider (opt)  │
                 └───────────────────────────────────┘
```

### 3.1 Stack quyết định

| Lớp | Công nghệ | Lý do |
|-----|-----------|-------|
| Backend | Python 3.11+ / FastAPI | async, ecosystem ML |
| Job queue | Celery + Redis | ingestion bắt buộc async, retry, trạng thái job |
| Relational | PostgreSQL 16 | metadata, records (JSONB cho dimensions/metrics) |
| Vector | Qdrant | self-host nhẹ, hybrid dense+sparse, payload filter |
| Object storage | MinIO (hoặc local FS có interface) | PDF gốc, ảnh crop |
| Inference | Cấu hình được: local (Ollama / vLLM / llama.cpp) **hoặc** API (OpenAI-compat, document-AI) | model-agnostic, xem C3 & Phụ lục A |
| Frontend | Next.js + Tailwind | SSE streaming, render HTML table |
| Deploy | docker-compose | self-host một lệnh, đúng câu chuyện bán hàng |

### 3.2 Data model (Postgres)

```sql
knowledge_base(
  id uuid PK, name text, description text,   -- description dùng cho router sau này
  config jsonb,                               -- model overrides per-KB
  created_at timestamptz
)

document(
  id uuid PK, kb_id FK, filename text,
  status text CHECK (status IN ('queued','parsing','indexing','done','failed')),
  error text, page_count int, file_path text, created_at timestamptz
)

element(
  id uuid PK, doc_id FK, page int, bbox float8[4],
  type text CHECK (type IN ('text','table','figure')),
  crop_image_path text NOT NULL,             -- nguyên tắc #3: luôn có
  confidence float8, needs_review bool DEFAULT false,
  created_at timestamptz
)

table_element(
  element_id uuid PK FK,
  html text,                                  -- biểu diễn 1: để hiển thị
  summary text,                               -- biểu diễn 3: để routing ngữ nghĩa
  n_rows int, n_cols int,
  parse_strategy text                         -- 'simple_parser' | 'vlm'
)

record(                                       -- biểu diễn 2: để tra & suy luận số
  id uuid PK, table_element_id FK,
  dimensions jsonb NOT NULL,   -- {"region":"Afrique","country":"Algérie","model":"Citadine","year":2013,"quarter":"T1","month":"jan"}
  metrics jsonb NOT NULL,      -- {"revenue_eur":7462639,"volume":426}
  raw_values jsonb NOT NULL,   -- {"revenue_eur":"7 462 639 €","volume":"426"} — chuỗi gốc, bắt buộc giữ
  text_repr text NOT NULL      -- chuỗi được embed
)

chunk(
  id uuid PK, element_id FK, text text, token_count int
)

chat_session(id uuid PK, kb_id FK, created_at timestamptz)
chat_message(id uuid PK, session_id FK, role text, content text,
             citations jsonb, verification jsonb, created_at timestamptz)
```

Qdrant collections: `chunks`, `records`, `table_summaries` — mỗi point mang
payload `{kb_id, doc_id, element_id, (record_id)}` để filter và truy vết.

---

## 4. Các phase

Nguyên tắc chung mọi phase: mỗi phase kết thúc bằng một hệ thống **chạy được
end-to-end** ở mức của nó, có test, có DoD kiểm chứng được. Không gộp phase.

---

### PHASE 0 — De-risk spike: chứng minh `parser` model đọc được bảng mẫu trên phần cứng triển khai

**Đây là phase quan trọng nhất dù không sinh ra dòng code sản phẩm nào.**

#### Vấn đề cần giải quyết

Toàn bộ giá trị sản phẩm đứng trên một giả định chưa được kiểm chứng: model
`parser` đã chọn **(a)** chạy được với hiệu năng chấp nhận được trên phần cứng
triển khai, và **(b)** bóc đúng bảng pivot phức tạp thành HTML + records. Nếu
một trong hai sai, phải đổi lựa chọn *trước khi* xây. Spike này lặp lại mỗi khi
đổi model parser hoặc đổi phần cứng — nó là quy trình, không chỉ một lần.

*Với deployment tham chiếu (AMD RX 9070 XT / RDNA4), rủi ro phần cứng là có
thật:* RDNA4 mới, ROCm chỉ hỗ trợ từ 7.x, Ollama stock ship ROCm 6.x nên **nhận
GPU rồi treo ~30s và rớt về CPU âm thầm**. Chi tiết xử lý ở Phụ lục A.

#### Khó khăn kỹ thuật

- **Serving stack cho phần cứng đã chọn.** Với AMD/RDNA4: Vulkan backend hoặc
  build ROCm 7 (Phụ lục A). Với NVIDIA: thường trơn hơn. Đây là biến thiên theo
  môi trường — spike phải xác nhận, không giả định.
- VLM output không deterministic; cần prompt + few-shot ổn định để ra HTML
  hợp lệ và records đúng schema.
- Số theo locale trong ảnh (`7 462 639 €`, `7.462.639,50`) dễ bị VLM đọc vỡ —
  phải test trên các locale mục tiêu, không chỉ một.

#### Phương pháp

1. Dựng inference cho `parser` trên phần cứng thật; verify **chạy trên GPU**
   (không rớt CPU) và đo tokens/s để có baseline hiệu năng.
2. Viết script độc lập `spike/parse_table.py`: nhận ảnh bảng → prompt VLM sinh
   (a) HTML có rowspan/colspan, (b) JSON records theo schema
   `{dimensions, metrics, raw_values}`.
3. Chạy trên **bộ ≥10 ảnh bảng test** trải từ phẳng đơn giản → pivot lồng nhau
   (gồm ảnh Afrique/Algérie/Citadine đã có) và **trải vài locale số khác nhau**.
   Chấm tay từng con số.
4. Ghi `spike/REPORT.md`: model + serving stack đã chọn, tokens/s, tỉ lệ ô đúng,
   các kiểu lỗi — để Phase 1 dùng lại và để tái chạy khi đổi model/phần cứng.

#### Definition of Done

- [ ] Xác nhận `parser` chạy trên GPU (không CPU-fallback) trên phần cứng triển khai.
- [ ] Bảng pivot mẫu ra HTML đúng cấu trúc + records đúng ≥ 95% ô.
- [ ] Số ở các locale mục tiêu không bị vỡ (kiểm tay).
- [ ] REPORT.md ghi rõ serving stack đã chọn + lý do.

**Nếu DoD fail:** dừng, báo cáo, thử model parser khác (InternVL, Pixtral, hoặc
API document-AI) hoặc backend khác. KHÔNG tiến sang Phase 1 với giả định chưa
chứng minh.

---

### PHASE 1 — Skeleton: xương sống hai-pipeline với text-only

#### Vấn đề cần giải quyết

Dựng toàn bộ khung: storage layer làm hợp đồng, ingestion async, query pipeline
dạng chuỗi step pluggable, model layer trừu tượng. Chỉ xử lý **text** (chưa có
bảng) để chứng minh xương sống thông suốt mà không bị độ phức tạp của bảng che mờ.

#### Khó khăn kỹ thuật

- **Ranh giới pipeline dễ bị xói mòn**: cám dỗ lớn nhất là để query code
  "gọi nhanh" một hàm của ingestion. Phải cưỡng lại — hai package Python
  riêng (`ingestion/`, `query/`), chỉ import chung `storage/` và `models/`.
- Job lifecycle: PDF hỏng, worker chết giữa chừng, retry không được tạo
  element trùng (ingestion phải **idempotent theo doc_id** — reprocess xóa
  element cũ của doc trước khi ghi mới).
- Streaming: chat phải stream SSE từ đầu, retrofit sau rất đau.
- PDF text extraction: PDF có text layer thì trích trực tiếp (nhanh, chính xác);
  PDF scan thì cần OCR — Phase 1 dùng heuristic đơn giản (thử extract text,
  nếu quá ít text/trang → đánh dấu trang cần OCR, OCR bằng VLM sang Phase 2).

#### Phương pháp

1. Repo layout:

```
tablerag/
  api/            # FastAPI routes: kb, documents, chat, jobs
  ingestion/      # Celery tasks, layout, chunking
  query/          # pipeline steps: router, retrieve, rerank, assemble, generate, verify
  storage/        # repositories: Postgres (SQLAlchemy), Qdrant client, object store
  models/         # ModelProvider interface + OllamaProvider, OpenAICompatProvider
  core/           # config (pydantic-settings), logging, schemas (pydantic)
  frontend/       # Next.js app
  spike/          # giữ nguyên từ Phase 0
  tests/
  docker-compose.yml
```

2. `ModelProvider` interface (models/base.py):

```python
class ModelProvider(Protocol):
    async def parse_table(self, image: bytes, prompt_ctx: TableCtx) -> TableParse: ...
    async def embed(self, texts: list[str]) -> list[Vector]: ...          # dense + sparse
    async def chat(self, messages: list[Msg], stream: bool) -> AsyncIterator[str]: ...
    async def rerank(self, query: str, docs: list[str]) -> list[float]: ...
```

3. Query pipeline = chuỗi step, mỗi step một class có `async run(ctx) -> ctx`:
   `Router → Retrieve → Rerank → AssembleContext → Generate → Verify`.
   Phase 1: Router = `SingleKBRouter` (no-op), Rerank = pass-through,
   Verify = disabled. **Chỗ cắm tồn tại từ bây giờ** (nguyên tắc #4).
4. Ingestion Phase 1: upload → job → extract text (PyMuPDF) → chunk
   (theo đoạn, ~500 token, overlap 10%) → embed (bge-m3 dense) → Qdrant.
5. Frontend tối thiểu: tạo KB, upload + xem trạng thái job (polling), chat
   stream có citation trỏ về (doc, page).
6. Test: unit cho storage repositories + chunking; integration một PDF text
   tiếng Pháp end-to-end (docker-compose up → upload → hỏi → có câu trả lời
   kèm citation đúng trang).

#### Definition of Done

- [ ] `docker-compose up` dựng đủ stack; upload một PDF quy chế tiếng Pháp,
      status chuyển `queued→parsing→indexing→done`.
- [ ] Hỏi một câu chính sách tiếng Pháp → trả lời stream, citation đúng trang.
- [ ] Kill worker giữa job rồi retry → không có element trùng.
- [ ] `ingestion/` và `query/` không import lẫn nhau (kiểm bằng import-linter
      hoặc test cấu trúc).

**Out of scope Phase 1:** bảng, OCR scan, rerank, verification, multi-KB router, UI đẹp.

---

### PHASE 2 — Table sub-pipeline: ba biểu diễn (moat của sản phẩm)

#### Vấn đề cần giải quyết

Biến mỗi bảng trong PDF thành **ba biểu diễn**: `html` (hiển thị),
`records` (tra cứu & suy luận số chính xác), `summary` (routing ngữ nghĩa) —
kể cả với bảng pivot lồng nhau mà markdown/TSR heuristic bó tay. Đồng thời
tách vùng bảng ra khỏi trang và phân loại đơn giản/phức tạp để không đốt
VLM lên bảng 3 dòng.

#### Khó khăn kỹ thuật

1. **Layout detection**: tìm bbox các vùng `text/table/figure` trên trang.
   Phương án: PP-Structure (PaddleOCR) làm detector — nhẹ, chạy CPU được;
   hoặc dùng chính VLM nhìn cả trang trả về bbox. Chọn PP-Structure trước vì
   rẻ và tách bạch; VLM chỉ nhận vùng đã crop.
2. **Classifier độ phức tạp bảng**: quyết định `simple_parser` vs `vlm`.
   Heuristic đủ dùng: nếu detector/parser thấy ô gộp, header nhiều tầng,
   hoặc parser thường trả về lưới không đều → `vlm`. Bias về phía `vlm` khi
   nghi ngờ (đắt hơn nhưng đúng hơn).
3. **VLM structured output**: bắt VLM trả JSON đúng schema ổn định là khó nhất.
   Phương pháp: prompt few-shot với 2 ví dụ (1 bảng phẳng, 1 pivot), yêu cầu
   output hai khối tách biệt ```html``` và ```json```; parse + validate bằng
   pydantic; nếu JSON hỏng → retry 1 lần với thông báo lỗi cụ thể; vẫn hỏng
   → đánh `needs_review=true`, vẫn lưu HTML + ảnh crop (thất bại trung thực).
4. **Suy chiều (dimensions) từ header phân cấp**: với pivot, tên chiều
   không phải lúc nào cũng có sẵn (bảng mẫu không ghi chữ "region" ở đâu).
   Cho phép VLM tự đặt tên chiều (`level_1`, `country`,...) miễn nhất quán
   trong một bảng; tên chiều nằm trong `dimensions` JSONB nên schema không cần
   biết trước — đây là lý do chọn JSONB.
5. **Chuẩn hóa số locale-aware** — module riêng `core/numbers.py`, pure
   function, nhận `locale` (hoặc tự suy từ ngôn ngữ tài liệu), test dày cho
   **từng locale mục tiêu**:
   - FR `"7 462 639 €"` / `"1 234,56"` → `7462639` / `1234.56` + currency `EUR`
   - DE `"7.462.639,50"` → `7462639.50` (chấm nghìn, phẩy thập phân)
   - EN `"7,462,639.50"` → `7462639.50` (phẩy nghìn, chấm thập phân)
   - `"12,5 %"` / `"12.5%"` → `12.5` kèm unit `%` (chọn một quy ước, ghi rõ)
   - Xử lý cả narrow no-break space (U+202F/U+00A0) hay gặp ở FR.
   - Luôn giữ `raw_values` nguyên bản. Không bao giờ ghi đè chuỗi gốc.
   - **Không tự đoán locale bằng heuristic mong manh**: ưu tiên locale khai báo
     ở KB/tài liệu; chỉ suy đoán khi thiếu, và ghi log khi suy đoán.
6. **Bảng scan (ảnh)**: với trang scan, mọi thứ đi qua đường VLM (nó vốn
   đọc ảnh) — bảng scan không phải case riêng, chỉ là input ảnh chất lượng
   thấp hơn; thêm bước upscale/denoise nhẹ nếu cần.
7. **Bảng dài tràn trang**: MVP xử lý mức "bảng nhỏ nằm gọn một vùng"
   (đúng phân bố dữ liệu khách). Bảng tràn trang → đánh `needs_review`,
   ghi nhận làm việc tương lai. Không cố làm ngay.

#### Phương pháp

1. Mở rộng ingestion: sau extract, chạy layout detection → tạo `element`
   per vùng, crop và lưu ảnh mọi vùng (kể cả text — rẻ, và phục vụ nguyên tắc #3).
2. `figure` → lưu ảnh + caption gần nhất, không đi xa hơn (C5).
3. `table` → classifier → simple path (pdfplumber/camelot cho bảng phẳng có
   text layer) hoặc VLM path (Phase 0 spike code được nâng cấp thành module
   `ingestion/table_vlm.py`).
4. Từ parse result: ghi `table_element` + N `record`; sinh `text_repr`
   dạng `"Afrique | Algérie | Citadine | 2013 T1 janvier | revenue 7 462 639 EUR | volume 426"`;
   sinh `summary` bằng LLM chat (GPU1) từ HTML.
5. Embed: từng `record.text_repr` vào collection `records`; `summary` vào
   `table_summaries`.
6. Query pipeline: `Retrieve` giờ tìm trên cả 3 collection; `AssembleContext`
   khi trúng record thì **kéo cả HTML của bảng cha** vào context (không chỉ
   record lẻ) kèm ảnh crop path và confidence.
7. System prompt generate: nếu nguồn là bảng phân cấp → render lại bằng
   bảng markdown/HTML, không làm phẳng mất tính đối sánh hàng-cột;
   luôn cite bảng nguồn.
8. **Bộ eval bảng** (đây là bằng chứng của moat): `tests/eval/tables/` chứa
   ≥ 15 bảng thật (ảnh + ground truth JSON) từ đơn giản → pivot; script chấm
   **đúng/sai từng con số** và in báo cáo. Chạy được bằng một lệnh
   `make eval-tables`.

#### Definition of Done

- [ ] Upload PDF chứa bảng pivot mẫu → DB có records với dimensions/metrics
      đúng, HTML render lại đúng cấu trúc trên frontend.
- [ ] Hỏi "Chiffre d'affaires Citadine Algérie janvier 2013 ?" → trả lời
      **đúng con số** `7 462 639 €`, cite đúng bảng.
- [ ] `numbers.py` pass toàn bộ test số cho **các locale mục tiêu** (≥ 20 case
      mỗi locale FR/DE/EN, gồm edge case: số âm, %, nghìn bằng space/chấm/phẩy,
      narrow no-break space U+202F).
- [ ] `make eval-tables` chạy, báo cáo tỉ lệ ô đúng ≥ 95% trên bộ eval.
- [ ] Bảng bị parse hỏng → `needs_review=true`, vẫn có HTML/ảnh, không crash job.

**Out of scope Phase 2:** confidence check chéo (Phase 3), verification câu
trả lời (Phase 4), bảng tràn trang.

---

### PHASE 3 — Confidence & honest failure: lớp tự biết mình sai

#### Vấn đề cần giải quyết

Phase 2 parse được, nhưng chưa **biết khi nào mình parse sai**. Phase 3 xây
cơ chế tự chấm điểm ở tầng ingestion, và đường fallback hiển thị ảnh gốc ở
tầng query. Đây là hiện thực hóa triết lý 0.3.

#### Khó khăn kỹ thuật

- **Không có ground truth lúc runtime** — confidence phải suy từ tính nhất quán
  nội tại. Ba tín hiệu khả thi, độc lập nhau:
  1. *Structural consistency*: số ô suy ra từ HTML (đếm cell, tính cả
     rowspan/colspan) phải khớp số record × số metric. Lệch → nghi ngờ.
  2. *Double-read agreement*: đọc bảng lần 2 bằng VLM (temperature khác hoặc
     prompt biến thể), so records hai lần đọc. Bảng nhỏ nên đọc 2 lần rẻ —
     đây là lợi thế "brute-force bằng chất lượng" mà bảng nhỏ cho phép.
     Tỉ lệ ô khớp < ngưỡng (đề xuất 0.98) → `needs_review`.
  3. *Arithmetic check*: nếu bảng có dòng/cột tổng (phát hiện qua nhãn
     "Total/Somme/Ensemble" hoặc VLM đánh dấu), kiểm tổng các con ≈ dòng tổng
     (tolerance làm tròn). Sai → tín hiệu mạnh nhất, `needs_review` ngay.
- **Chi phí**: double-read nhân đôi thời gian ingestion. Chấp nhận được vì
  ingestion là offline/async; cho phép tắt qua config per-KB nếu khách cần nhanh.
- **Ngưỡng**: đừng đoán ngưỡng trong code review — expose thành config,
  tune bằng bộ eval Phase 2.

#### Phương pháp

1. `ingestion/confidence.py`: chạy 3 tín hiệu sau khi parse, tổng hợp thành
   `confidence: float` (trung bình có trọng số, arithmetic check nặng nhất)
   và `needs_review: bool`. Lưu chi tiết từng tín hiệu vào
   `element.meta.confidence_detail` để debug.
2. Query pipeline — `AssembleContext` và `Generate` nhận thức confidence:
   - Nguồn `needs_review` → context ghi rõ cho LLM: *"bảng này parse độ tin
     thấp, KHÔNG khẳng định số liệu từ nó"*; câu trả lời phải kèm ảnh crop
     và câu cảnh báo chuẩn.
   - Frontend render: câu trả lời có block "⚠ nguồn độ tin thấp — xem bảng gốc"
     kèm ảnh crop, click phóng to.
3. UI review tối thiểu cho admin: danh sách element `needs_review` của một
   document, hiện ảnh crop cạnh HTML đã parse; hai nút **Approve** (xóa cờ)
   / **Mark unusable** (loại record khỏi retrieval, giữ ảnh cho fallback).
   Không xây editor sửa bảng ở phase này — approve/reject là đủ.
4. Mở rộng eval: thêm vào bộ eval **các bảng cố tình khó/hỏng** (mờ, nghiêng,
   cấu trúc quái) và chấm cả hai chiều: hệ thống có *dám* flag không
   (recall của cờ) và có flag *oan* bảng tốt không (precision của cờ).

#### Definition of Done

- [ ] Bảng tốt trong bộ eval: ≤ 10% bị flag oan. Bảng hỏng cố tình: ≥ 90% bị flag.
- [ ] Hỏi số liệu từ bảng `needs_review` → câu trả lời KHÔNG khẳng định số,
      có ảnh crop + cảnh báo (test integration tự động kiểm chuỗi cảnh báo).
- [ ] Admin approve một bảng → cờ mất, câu trả lời trở lại bình thường.
- [ ] Double-read tắt/bật được per-KB qua config.

---

### PHASE 4 — Retrieval chất lượng cao & verification câu trả lời

#### Vấn đề cần giải quyết

Đến giờ retrieval là dense-only và câu trả lời chưa được kiểm số. Phase 4:
(a) hybrid retrieval + rerank để tìm đúng record/chunk trong kho lớn hơn,
(b) verification layer bắt LLM bịa số — mắt xích cuối của "không bao giờ sai số".

#### Khó khăn kỹ thuật

- **Hybrid search**: câu hỏi số liệu chứa token hiếm (mã sản phẩm, "T1 2013",
  tên riêng) mà dense embedding hay nhòe — sparse (BM25/learned sparse) bắt
  tốt hơn. bge-m3 sinh được cả dense + sparse trong một lần; Qdrant hỗ trợ
  named vectors + fusion (RRF). Khó ở chỗ tune trọng số fusion — đừng tune tay,
  dùng bộ eval câu hỏi.
- **Rerank latency**: bge-reranker-v2-m3 trên GPU2, chỉ rerank top-50 → top-8.
  Đo p95 latency, ngân sách < 500ms cho bước rerank.
- **Verification số liệu**: sau khi LLM sinh câu trả lời, trích mọi con số
  trong câu trả lời (regex số đa locale, tái dùng
  `core/numbers.py`), đối chiếu với tập `metrics` + `raw_values` của các record
  trong context. Số không khớp nguồn nào (sau chuẩn hóa + tolerance làm tròn)
  → hoặc regenerate 1 lần với chỉ dẫn "chỉ dùng số có trong nguồn", hoặc
  gắn nhãn "⚠ số này không đối chiếu được với nguồn" ngay cạnh con số.
  **Bẫy phải xử lý**: số do LLM *tính toán hợp lệ* (tổng, hiệu, %) sẽ không
  khớp nguồn — verification phải cho phép whitelist phép tính đơn giản:
  thử xem số lạ có bằng tổng/hiệu/tỉ lệ của ≤ 3 số nguồn không trước khi
  gắn cảnh báo. Không hoàn hảo cũng được — thà cảnh báo thừa còn hơn sai âm thầm.
- **Verification là toggle** (per-KB + per-request), mặc định bật cho KB
  chứa bảng. Đây là "lớp xác minh bật/tắt" trong yêu cầu gốc của sản phẩm.

#### Phương pháp

1. Nâng `embed()` trả cả dense + sparse; migrate Qdrant sang named vectors;
   viết migration script reprocess embedding (không cần re-parse — nhờ
   nguyên tắc #1, records/chunks còn nguyên trong Postgres).
2. `Retrieve` step: RRF fusion dense+sparse trên cả 3 collection, top-50.
3. `Rerank` step: bge-reranker trên GPU2 → top-8 vào context.
4. `Verify` step: như mô tả trên, output `verification` JSON lưu vào
   `chat_message.verification` (số nào khớp nguồn nào, số nào được suy ra,
   số nào cảnh báo) — frontend render badge cạnh từng con số.
5. **Bộ eval câu hỏi** (khác bộ eval bảng): ≥ 30 cặp (câu hỏi tiếng Pháp,
   đáp án + nguồn đúng) trên corpus HR thật, 3 nhóm: hỏi số từ bảng /
   hỏi chính sách từ text / **câu bẫy** hỏi vào bảng biết-là-khó để kiểm
   hệ thống có thành thật không. `make eval-qa` chấm: đúng đáp án, đúng nguồn,
   và với câu bẫy — có cảnh báo thay vì bịa.
6. Log mọi câu hỏi thật của người dùng nội bộ (dogfood) kèm feedback 👍/👎
   một chạm — nguồn nuôi bộ eval về sau.

#### Definition of Done

- [ ] `make eval-qa`: nhóm hỏi-số đạt độ chính xác con số ≥ 95%; nhóm câu bẫy
      100% có cảnh báo hoặc fallback (không câu nào bịa số mà không cảnh báo).
- [ ] Câu hỏi chứa mã/token hiếm mà dense-only trước đây trượt → hybrid tìm ra
      (thêm ít nhất 3 case như vậy vào eval để chứng minh).
- [ ] p95 end-to-end query < 8s (không tính stream token), rerank < 500ms.
- [ ] Tắt verification qua config → step bị bỏ qua sạch sẽ, không side effect.

---

### PHASE 5 — Multi-KB, router, và trải nghiệm người dùng cuối

#### Vấn đề cần giải quyết

Sản phẩm hóa: nhiều KB độc lập do người dùng tự tổ chức (đúng tầm nhìn gốc),
router chọn KB theo description, UI kéo-thả thân thiện non-engineer, và
đóng gói self-host bán được.

#### Khó khăn kỹ thuật

- **Router**: với ≤ ~15 KB, một LLM call (đưa câu hỏi + danh sách
  `kb.description`, trả JSON danh sách kb_ids, **cho phép chọn nhiều**) là đủ
  và dễ debug. Semantic routing (embed description) chỉ làm khi số KB lớn —
  ghi nhận là future work, đừng làm trước. Route sai là điểm chết đã biết →
  giảm rủi ro bằng: luôn cho phép chọn nhiều KB + UI cho người dùng pin KB
  thủ công (override router).
- **Description chất lượng thấp** (người dùng viết mô tả KB sơ sài) →
  router mù. Giải pháp sản phẩm chứ không phải kỹ thuật: khi tạo KB, gợi ý
  auto-generate description từ N tài liệu đầu tiên (LLM tóm), người dùng sửa.
- **UX ingestion cho non-engineer**: kéo-thả nhiều file, progress per-file,
  lỗi human-readable ("Trang 4 có bảng chưa đọc chắc — bấm xem"), khu review
  needs_review đưa ra khỏi "admin" thành flow tự nhiên.
- **Đóng gói**: docker-compose một lệnh, script kiểm tra GPU/driver in cảnh báo
  rõ (đặc thù ROCm/gfx1201 — C3), tài liệu cài đặt cho IT của khách.

#### Phương pháp

1. `Router` step: `LLMRouter` implement cùng interface với `SingleKBRouter`
   (chỗ cắm đã có từ Phase 1 — đây là lúc nguyên tắc #4 trả cổ tức).
   Log quyết định route vào chat_message để debug và làm eval routing sau này.
2. Retrieve/Rerank chạy trên union các KB được chọn, payload filter theo kb_ids.
3. Frontend hoàn thiện: màn hình KB (tạo, mô tả có nút auto-generate),
   kéo-thả upload, bảng trạng thái tài liệu, khu "cần xem lại" (từ Phase 3),
   chat có: chọn KB thủ công hoặc auto-route, render bảng HTML đẹp,
   badge verification, ảnh crop phóng to, nút 👍/👎.
4. Eval routing: thêm vào eval-qa trường `expected_kbs`, chấm router
   precision/recall riêng — tách "lỗi định tuyến" khỏi "lỗi sinh" để biết
   tối ưu chỗ nào (nguyên tắc đo lường xuyên suốt).
5. Hardening bán hàng: auth cơ bản (multi-user, role admin/user), audit log
   upload/query (GDPR accountability), backup script Postgres+Qdrant+MinIO,
   docs cài đặt.

#### Definition of Done

- [ ] 3 KB thật (vd: Quy chế nội bộ / Lương & phúc lợi / Đào tạo) — 10 câu hỏi
      trải đều: router chọn đúng (bộ) KB ≥ 90%, người dùng override được.
- [ ] Một đồng nghiệp HR không được hướng dẫn tự tạo KB, upload, hỏi, và hiểu
      được cảnh báo needs_review — test bằng quan sát thật, ghi lại điểm vướng.
- [ ] `docker-compose up` trên máy sạch (có GPU đã cài driver) dựng được toàn bộ,
      script preflight báo đúng tình trạng GPU.
- [ ] Eval routing được tách và báo cáo riêng khỏi eval sinh câu trả lời.

---

## 5. Chiến lược kiểm thử & đánh giá xuyên suốt

| Loại | Sống ở đâu | Chạy khi nào |
|------|-----------|--------------|
| Unit (numbers per-locale, chunking, confidence signals, verification math) | `tests/unit/` | mỗi commit |
| Integration (upload→query end-to-end, idempotency, streaming) | `tests/integration/` | mỗi PR |
| Eval bảng (đúng/sai từng ô) | `tests/eval/tables/` + `make eval-tables` | mỗi thay đổi pipeline bảng |
| Eval Q&A (đáp án + nguồn + câu bẫy) | `tests/eval/qa/` + `make eval-qa` | mỗi thay đổi retrieval/prompt |
| Eval routing | trong eval-qa, chấm riêng | từ Phase 5 |

Quy tắc vàng: **mọi thay đổi prompt hoặc model đều phải chạy lại eval liên quan
và dán kết quả vào PR.** Prompt là code.

Dữ liệu eval là tài sản: nuôi liên tục từ câu hỏi dogfood thật (log Phase 4).
Không có PII trong repo — bảng eval lấy từ tài liệu đã ẩn danh hoặc tự dựng
mô phỏng đúng cấu trúc thật.

## 6. Những thứ CỐ TÌNH không làm (để chống scope creep)

- GraphRAG, RAPTOR, query decomposition — chỉ cân nhắc khi eval chỉ ra nhu cầu.
- Semantic router / hàng trăm KB — future work có điều kiện kích hoạt rõ.
- Bảng tràn nhiều trang, flowchart, biểu đồ trích số — out of scope, fail trung thực.
- Editor sửa bảng trong UI review — approve/reject là đủ cho v1.
- Fine-tune model — chưa có dữ liệu, chưa có lý do.
- Cloud API trong đường dữ liệu mặc định — vi phạm C1.

## 7. Rủi ro còn mở & tín hiệu cảnh báo sớm

| Rủi ro | Tín hiệu | Kế hoạch B |
|--------|----------|------------|
| Parser model kém trên phần cứng đã chọn | Phase 0 DoD fail | đổi model/backend qua config; deployment AMD: xem Phụ lục A |
| (AMD deployment) Ollama update phá ROCm lib | inference đột nhiên chậm (CPU fallback) | pin version Ollama trong compose; healthcheck đo tokens/s, alert khi tụt (Phụ lục A.3) |
| Embedder yếu ở một ngôn ngữ mục tiêu | eval-qa nhóm text của ngôn ngữ đó thấp bất thường | đổi model embedding multilingual khác qua config — chỉ cần re-embed, không re-parse (nguyên tắc #1) |
| VLM output drift theo version model | eval-tables tụt sau khi đổi model | pin model tag; eval là cổng bắt buộc trước khi nâng model |
| Người dùng bỏ qua cảnh báo needs_review | quan sát dogfood | tăng độ nổi bật UI; chặn cứng khẳng định số từ nguồn flagged |

---

## Phụ lục A — Cấu hình tham chiếu (deployment nội bộ AMD)

> Đây **không phải yêu cầu của nền tảng**, mà là một cấu hình đã kiểm chứng cho
> máy nội bộ của chủ dự án. Nền tảng vẫn model-/hardware-agnostic (C3). Giữ lại
> vì nó đúng và là điểm khởi đầu tốt cho ai dùng phần cứng tương tự.

### A.1 Phần cứng
3× AMD Radeon RX 9070 XT (RDNA4 / gfx1201, 16GB VRAM mỗi card).

### A.2 Gán vai trò model → GPU

| GPU | Vai trò | Model gợi ý | Ghi chú |
|-----|---------|-------------|---------|
| GPU0 | `parser` (VLM) | Qwen2.5-VL-7B (Q4) | mạnh về document/table ở tầm 7B |
| GPU1 | `chat` (LLM) | model họ Mistral/Ministral ~8B (Q4) | tiếng Pháp tốt + câu chuyện "model châu Âu" khi bán ở thị trường Pháp; đổi tùy ngôn ngữ đích |
| GPU2 | `embedder` + `reranker` | bge-m3 + bge-reranker-v2-m3 | bge-m3 sinh cả dense + sparse, đa ngôn ngữ tốt |

Với 3 card, cả ba vai trò **thường trú song song** → ingestion và query chạy
đồng thời không giành GPU, không cần swap model theo pha. Gán device bằng
`ROCR_VISIBLE_DEVICES` (hoặc `HIP_VISIBLE_DEVICES`) cho từng instance.

*Nếu chỉ có 1 card 16GB:* không nhồi cả ba cùng lúc được → tách theo pha
(VLM chạy lúc ingestion, chat chạy lúc query, embedder bé thường trú), dùng
`keep_alive`/auto-unload của Ollama. Nền tảng hỗ trợ cả hai kịch bản qua config.

### A.3 Serving stack cho RDNA4 (điểm dễ vỡ nhất)

RX 9070 XT là gfx1201; ROCm chỉ hỗ trợ từ 7.x. **Ollama bản cài mặc định ship
ROCm 6.x → nhận GPU rồi treo ~30s lúc discovery và rớt về CPU âm thầm** (chạy
cực chậm mà không báo lỗi rõ). Ba đường xử lý, thử theo thứ tự:

1. **`OLLAMA_VULKAN=1`** — backend Vulkan, né hẳn ROCm, ít đau đầu driver nhất.
   Có thể chậm hơn ROCm một chút. Thử đầu tiên.
2. **Ollama + build ROCm 7 của cộng đồng** (ví dụ repo kiểu `ollama-rocm` cho
   gfx1201) — đã có báo cáo chạy 100% GPU cho model ~14B trên đúng card này.
   Nhược: mỗi lần Ollama auto-update ghi đè lib ROCm 6.x, phải chép đè lại
   → **pin version Ollama trong docker-compose** và có script khôi phục.
3. **llama.cpp trực tiếp** (Vulkan/ROCm) nếu cần kiểm soát sâu.

Kiểm chứng bắt buộc: `ollama ps` phải báo 100% GPU (không phải CPU/partial).
Preflight script khi deploy nên đo tokens/s và cảnh báo nếu nghi CPU-fallback.

### A.4 Ràng buộc local-only cho deployment này
Vì tài liệu HR Pháp chịu GDPR (C1), deployment này chạy **hoàn toàn local**:
`parser`, `embedder`, `chat`, `reranker` đều trỏ tới Ollama nội bộ, không bật
provider API nào. Đây là ví dụ điển hình của khách yêu cầu data residency.
