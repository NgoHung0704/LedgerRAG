# Trang tài liệu kiến trúc LedgerRAG — thiết kế

Ngày: 2026-08-09 · Trạng thái: đã duyệt qua brainstorming, chờ plan

## 1. Mục tiêu và người đọc

Một trang web tĩnh giải thích kiến trúc repo này cho **dev mới** và **người
nhận bàn giao**. Trang phải đọc được bằng mắt lẫn bàn phím, và ràng buộc quan
trọng nhất: **không được nói sai về code**.

"Không nói sai" ở đây không phải lời hứa mà là một cơ chế: mọi khẳng định về
code đều mang theo một trích dẫn kiểm được, và một bộ guard chạy trong cổng
test sẵn có của repo sẽ đỏ khi trang lệch khỏi code. Đây là điểm khác biệt duy
nhất giữa trang này và một file README dài.

Trang cũng phải **ghi cả những chỗ còn nợ**: thứ chưa validate, thứ chưa làm,
chỗ tạm bợ. Repo này có nợ thật và đã ghi sẵn trong README (cổng ≥95% của
Phase 2 chưa đạt, recall ≥90% của Phase 3 không đạt được trên phần cứng đó,
DoD của Phase 1 và Phase 5 còn phải chạy trên stack thật). Một trang chỉ khoe
phần đẹp thì người nhận bàn giao không dùng được.

## 2. Bối cảnh khảo sát được từ repo

Những dữ kiện dưới đây là tiền đề của thiết kế; chúng đã được kiểm tại thời
điểm viết spec.

- **Backend**: Python ≥3.11 — FastAPI + Celery/Redis + SQLAlchemy/psycopg
  (Postgres) + Qdrant + MinIO + PyMuPDF. 73 module `.py` trong `tablerag/`.
- **Frontend sản phẩm**: Next.js 14 app router + Tailwind. 32 file `.ts/.tsx`
  trong `frontend/{app,components,lib}` (cộng `app/globals.css`).
- **API**: 61 endpoint trên 9 route module.
- **Hạ tầng**: `docker-compose.yml` — postgres, redis, qdrant, minio, api,
  worker, consumer, frontend, reranker (profile `reranker`, opt-in).
- **Model serving cố tình nằm ngoài compose** (ràng buộc C3): 4 vai trò
  `parser` / `embedder` / `chat` / `reranker` trỏ ra endpoint qua env
  `LEDGERRAG_MODELS__<ROLE>__*`.
- **Giai đoạn**: SPEC §4 định nghĩa Phase 0–5; README §"Phase status" ghi
  trạng thái đo được của từng phase.
- **Cổng đang có**: `make test-unit` → `pytest tests/unit` — **843 test, xanh,
  6.2s**. `make lint` → ruff — **đỏ, 6 lỗi có sẵn** (xem §9).
- **Không có CI**: không có `.github/`, không workflow nào được track.
- **GitHub Pages đang tắt**, Source = "Deploy from a branch", Branch = None.
- **Tiền lệ tốt**: `tests/unit/test_architecture.py` đã là guard tĩnh đọc AST
  để chặn `ingestion/` import `query/`. Guard mới đi theo đúng kiểu này.
- **Line ending**: working tree Windows có CRLF trong `.py`/`.tsx`, còn
  `SPEC.md`/`README.md` là LF; git lưu LF. Guard so sánh nguyên văn **bắt buộc**
  chuẩn hoá `\r\n` → `\n` trước khi so, nếu không sẽ xanh trên Windows và đỏ
  trên runner Linux.

## 3. Quyết định đã chốt với người dùng

| Câu hỏi | Chốt |
|---|---|
| Ngôn ngữ hiển thị | Song ngữ VI + EN |
| Trục lọc "ticket" | Phase 0–5 của SPEC §4 |
| Phạm vi guard phủ module | `tablerag/` + `frontend/` |
| Đường deploy | GitHub Actions build + deploy; guard nằm trong pytest |
| Stack trang | `docs-site/` riêng: Vite + React + TS, **không thư viện animation** |
| 6 lỗi ruff có sẵn | Sửa luôn, để CI gác được cả hai cổng |

## 4. Kiến trúc trang

```
docs-site/
  content/            <- toàn bộ chữ người đọc thấy
  src/                <- code: chỉ biết hình dạng dữ liệu, không biết chữ
  tests/              <- Vitest: hành vi UI
  tools/relink.py     <- sửa số dòng đã trôi
  vite.config.ts      <- base: '/LedgerRAG/'
tests/unit/test_docs_content.py   <- guard chống lệch (pytest, cổng sẵn có)
.github/workflows/ci.yml          <- CI đầu tiên của repo
```

`tools/relink.py` nằm trong `docs-site/` chứ không phải `scripts/` ở gốc:
`scripts/` gốc đang là script vận hành cho box triển khai (`backup.sh`,
`preflight.sh`), trộn một công cụ tài liệu vào đó sẽ gây hiểu nhầm.

**`.gitignore`**: thêm `docs-site/node_modules/`. **Không** thêm
`docs-site/package-lock.json` — `npm ci` trong CI *bắt buộc* có lockfile được
commit. Luật `frontend/package-lock.json` đang có chỉ áp cho app sản phẩm, nên
lockfile của `docs-site` không bị nó chặn. `docs-site/dist/` đã bị luật `dist/`
sẵn có bắt.

**Vì sao thư mục riêng, không nhét vào `frontend/`**: app sản phẩm chạy động
(SSR, gọi API), không cấu hình cho static export; ép nó export sẽ đụng cấu
hình sản phẩm và trộn hai vòng đời khác nhau vào một build.

**Vì sao không thư viện animation**: Motion/Framer ghi `opacity` vào inline
style, vô hiệu hoàn toàn class `.dimmed` trên cùng phần tử — tính năng lọc
trông như hỏng mà test vẫn xanh. Không cài thư viện thì bẫy này không tồn tại.
Chuyển cảnh làm bằng CSS transition; `prefers-reduced-motion` xử lý trong CSS.

**Base path**: Pages project site phục vụ ở `https://<user>.github.io/LedgerRAG/`.
`base: '/LedgerRAG/'` trong Vite và hash routing (Pages không có SPA fallback,
hash tránh hẳn nhu cầu file `404.html`).

## 5. Mô hình nội dung

Mọi chuỗi người đọc thấy — kể cả nhãn nút và `aria-label` — nằm trong
`docs-site/content/`. Lý do không phải thẩm mỹ: nó cho phép guard viết bằng
Python canh nội dung mà không phải parse code UI.

```
content/
  ui.json               nhãn nút, tiêu đề, aria-label, trạng thái rỗng
  nodes.json            Lớp 1: service, datastore, thành phần ngoài
  edges.json            Lớp 1: cạnh + hợp đồng
  ownership.json        bảng ai sở hữu / ai ghi
  phases.json           Phase 0–5 + nợ còn mở của từng phase
  components.json       Lớp 2: lưới component
  components/<id>.json  Lớp 3: chi tiết từng component
  machines.json         sơ đồ dây chuyền
```

### 5.1 Chuỗi song ngữ là một kiểu dữ liệu

Mỗi chuỗi hiển thị là `{"vi": "…", "en": "…"}`. **Không** tách thành hai file
theo ngôn ngữ: hai file sẽ lệch âm thầm khi ai đó thêm key vào một bên. Để
cạnh nhau thì guard chỉ cần một luật — cả `vi` lẫn `en` phải có và khác rỗng.

### 5.2 Hai kiểu trích dẫn

```jsonc
{ "kind": "excerpt", "file": "tablerag/query/steps/router.py",
  "from": 41, "to": 58, "code": "class LLMRouter:\n    …" }

{ "kind": "anchor", "file": "SPEC.md", "from": 93, "to": 109,
  "anchor": "ingestion/ và query/ không bao giờ import nhau" }
```

`excerpt` = code hiện nguyên văn trên trang. `anchor` = khẳng định không kèm
code; chuỗi `anchor` phải nằm trong khoảng dòng đó. Anchor trỏ được vào cả
`SPEC.md`/`README.md` — phần "vì sao" của dự án nằm ở đó và vẫn phải bị canh.

**Mọi khẳng định về code phải mang một trong hai.** Phần "vì sao" rút từ lý do
đã có sẵn trong comment/docstring/SPEC, không được bịa thêm.

### 5.3 Hàm ở Lớp 3

`{name, signature, file, line}`. Guard đòi dòng `line` **chứa đúng khai báo**
— không phải "nằm trong khoảng".

### 5.4 Quan hệ phase ↔ component có ba loại

`creates` · `modifies` · `traverses`.

- Lọc theo phase làm sáng **cả ba**. Nếu chỉ sáng `creates`+`modifies`, request
  của phase hiện ra như đứt giữa chừng — thành phần nó *gọi* mà không *sửa* bị
  làm mờ.
- Sở hữu chỉ tính `creates`+`modifies`. Nếu chỉ tính `creates`, sẽ có phase
  không sở hữu gì và biến mất khỏi sơ đồ.

Mỗi khai báo quan hệ mang một `cite` — mapping phase↔file không suy được từ
git (commit không gắn phase), nên nó phải neo vào SPEC §4 hoặc README.

### 5.5 Nợ

`debt` là mục con của phase và của component, mỗi mục có `cite`. Không có mục
nợ nào được bịa: chúng rút từ README §"Phase status", SPEC §7 (rủi ro còn mở)
và SPEC §6 (những thứ cố tình không làm).

## 6. Ba lớp

### Lớp 1 — bản đồ hệ thống

Bốn cột: **bên ngoài** (trình duyệt, reverse-proxy/SSO, MCP client, thư mục
`consume/`) → **service của repo** (frontend, api, worker, consumer, mcp) →
**kho dữ liệu** (Postgres, Redis, Qdrant, MinIO) → **endpoint model**
(`parser`, `embedder`, `chat`, `reranker`).

61 endpoint không vẽ thành 61 mũi tên. Một **cạnh** là một họ hợp đồng; bấm
vào mở panel liệt kê từng operation với method, path, auth, hình dạng
request/response, mã lỗi. Sơ đồ đọc được, hợp đồng vẫn đủ.

**Bảng ai sở hữu / ai ghi** phủ 15 bảng Postgres, 3 collection Qdrant
(`chunks`, `records`, `table_summaries`) và tiền tố object store. Cột: kho ·
ai sở hữu · ai ghi · ai đọc · trích dẫn. Đây là chỗ dev mới hiểu sai nhất, và
là chỗ giải thích nguyên tắc #1 của SPEC (hai pipeline chỉ gặp nhau ở tầng lưu
trữ).

**Vẽ nhiều cạnh cùng một cặp node**: chia làn, nhãn đặt ở **giữa đoạn rẽ** chứ
không phải tâm hộp nguồn (hai cạnh đi hai hướng khác nhau sẽ nhận cùng một
điểm). Khoảng cách cột tính từ số làn thật sự đi qua khe đó.

### Lớp 2 — lưới component

21 component gom **hết** 105 module (73 `.py` + 32 `.ts/.tsx`). Danh sách đầy
đủ ở §7. Lọc theo Phase 0–5.

### Lớp 3 — chi tiết một component

Sơ đồ luồng gọi hàm · danh sách hàm (chữ ký + `file:line`) · **đoạn code thật**
· link tới đúng dòng trên GitHub · thẻ "vì sao" rút từ comment/docstring · thẻ
nợ.

### Sơ đồ "cỗ máy"

Hai dây chuyền:

- **ingest**: PDF vào → convert → extract → layout → vùng → bảng → confidence
  → chunk → embed → index. Lối ra: `done` / `failed` / hàng đợi review.
- **query**: câu hỏi vào → Router → Retrieve → Rerank → Assemble → Generate →
  Verify. Lối ra: trả lời có trích dẫn / từ chối / cờ cảnh báo.

Lọc theo phase: phần thuộc phase sáng lên, phần còn lại chìm xuống.

## 7. Danh sách component (mapping đầy đủ)

Mapping này phủ 100% module trong phạm vi guard. `app/globals.css` không nằm
trong phạm vi (`.py`/`.ts`/`.tsx`), nhưng vẫn được liệt kê ở `fe-shell`.

| id | module |
|---|---|
| `gateway` | `tablerag/__init__.py`, `api/__init__.py`, `api/main.py`, `api/caching.py`, `core/auth.py`, `api/routes/__init__.py` |
| `http-contracts` | `api/routes/{assistants,chat,diagnostics,documents,elements,health,kb,me,models}.py` |
| `ingest-intake` | `ingestion/__init__.py`, `consumer.py`, `worker.py`, `tasks.py`, `convert.py` |
| `ingest-page-analysis` | `extract.py`, `layout.py`, `region_detect.py`, `boilerplate.py`, `ocr.py`, `imaging.py` |
| `ingest-tables` | `table_pipeline.py`, `html_tables.py`, `core/table_text.py`, `models/table_parsing.py` |
| `ingest-figures` | `chart_check.py`, `palette.py` |
| `ingest-confidence` | `confidence.py` |
| `index-write` | `chunking.py`, `indexing.py`, `scripts/reindex_all.py` |
| `query-pipeline` | `query/__init__.py`, `pipeline.py`, `steps/__init__.py` |
| `query-route-retrieve` | `steps/router.py`, `steps/retrieve.py`, `steps/rerank.py`, `core/sparse.py` |
| `query-answer` | `steps/condense.py`, `steps/assemble.py`, `steps/generate.py`, `steps/smalltalk.py` |
| `query-verify` | `steps/verify.py`, `query/verification.py`, `core/numbers.py` |
| `models-providers` | `models/{__init__,base,ollama,openai_compat,registry,edit_assist}.py` |
| `storage-layer` | `storage/{__init__,db,orm,repositories,qdrant,object_store}.py` |
| `core-config` | `core/{__init__,config,logging,queue,schemas,text_export}.py` |
| `mcp-and-ops` | `mcp/{__init__,client,server}.py`, `scripts/{__init__,debug_context}.py` |
| `fe-shell` | `app/layout.tsx`, `AppShell`, `Sidebar`, `ui`, `ThemeToggle`, `confirm`, `CopyButton`, `lib/api.ts`, `lib/clipboard.ts` |
| `fe-kb-documents` | `app/page.tsx`, `app/kb/[id]/page.tsx`, `DocumentsPanel`, `KbSettings`, `KbDescription`, `KbCardMenu`, `ReviewPanel` |
| `fe-inspector-editor` | `app/doc/[docId]/page.tsx`, `ElementEditor`, `RecordsTable`, `BoilerplatePanel`, `EditAssistant`, `SourceModal` |
| `fe-chat-assistants` | `app/ask/page.tsx`, `app/assistants/page.tsx`, `app/assistants/[id]/page.tsx`, `ChatPanel`, `ChatScopeSelector`, `AssistantForm`, `AssistantCardMenu` |
| `fe-ops-surfaces` | `app/models/page.tsx`, `app/audit/page.tsx`, `app/diagnostics/page.tsx` |

Tổng: 6+9+5+6+4+2+1+3+3+4+4+3+6+6+6+5 = **73** module Python; 9+7+6+7+3 =
**32** file frontend.

## 8. Guard chống lệch

Đặt ở `tests/unit/test_docs_content.py`. Python thuần + pytest, không thêm
dependency (`json` stdlib, phân tích code bằng `ast`). Chạy trong
`make test-unit`.

| # | Luật | Bắt được |
|---|---|---|
| G1 | `excerpt.code` khớp **nguyên văn** `[from..to]` sau chuẩn hoá CRLF→LF | code đổi, khoảng dòng sai, lệch khoảng trắng |
| G2 | `anchor` là chuỗi con **nằm trong** khoảng dòng; dài ≥12 ký tự; **duy nhất trong file** | chèn đoạn văn phía trên → khoảng trôi sang nội dung khác |
| G3 | Mọi module trong phạm vi có mặt ở ≥1 component | thêm file mà quên viết docs |
| G4 | Endpoint khớp **hai chiều** với `@router.*` đọc bằng AST | đổi/xoá endpoint; thêm endpoint không ai viết |
| G5 | Mọi `file` khai trong content tồn tại thật | đổi tên / di chuyển file |
| G6 | Mọi id tham chiếu chéo giải được **hai chiều** | node không cạnh nào chạm; phase không ai sở hữu; detail file mồ côi |
| G7 | Mọi `__tablename__` và collection Qdrant có một dòng trong bảng sở hữu | thêm bảng mà không nói ai ghi |
| G8 | Mọi chuỗi hiển thị đủ `vi`+`en` khác rỗng; chuỗi `en` không chứa ký tự có dấu tiếng Việt | dịch sót |
| G9 | `aria-label`/`title`/`alt`/`placeholder` trong `docs-site/src` không nhận literal; không text node trần trong JSX | chuỗi lọt vào code, thoát tầm test nội dung |

Ba chi tiết dễ làm sai:

**G3 nạp đúng hai nguồn, không glob cả `content/`**: chỉ `components.json` và
`components/*.json`. Nếu glob toàn thư mục, một module chỉ cần được
`phases.json` nhắc tên là qua cửa mà chẳng ai viết về nó.

**G6 là hai luật riêng, không phải một.** Chiều xuôi: mọi id được nhắc phải
tồn tại. Chiều ngược: mọi thực thể khai ra phải được nhắc — cụ thể mỗi phase
phải có ≥1 component quan hệ `creates` hoặc `modifies`. `traverses` không tính
vào chiều ngược (nó phục vụ lọc, không phục vụ sở hữu).

**G1/G2 kèm `make docs-relink`**: chỉ đánh lại số dòng khi tìm thấy đúng chuỗi
đó, không đổi, ở chỗ khác trong file. Nếu khai báo hoặc nội dung code thật sự
đổi, lệnh từ chối sửa và CI vẫn đỏ — vì lúc đó đoạn văn giải thích nó có thể
đã sai, và đấy đúng là lúc cần một con người.

**Không guard nào chốt cứng số lượng.** Không có `assert len(x) == 21`; đếm
theo chính nội dung. Thêm nội dung không phải lỗi.

### 8.1 Định nghĩa chính xác, để không diễn giải hai kiểu

- **G2 "duy nhất trong file"**: chuỗi `anchor` xuất hiện **đúng một lần** trong
  toàn file. Nếu không duy nhất, người viết phải kéo dài anchor cho đến khi
  duy nhất. Luật này vừa chặn anchor quá chung chung (kiểu `def `), vừa là
  điều kiện để `relink` biết chắc nó đang nối lại đúng chỗ.
- **G4 "path"**: đường dẫn đầy đủ = `prefix` của `APIRouter(...)` + path trong
  decorator, đọc bằng `ast` từ `tablerag/api/routes/*.py`. So khớp cặp
  `(METHOD, full_path)`.
- **G8 "ký tự có dấu tiếng Việt"**: tập ký tự riêng của tiếng Việt — `ăâđêôơư`
  và mọi nguyên âm mang dấu thanh, cả hoa lẫn thường. Các trường **trích dẫn
  nguyên văn nguồn** (`anchor`, `signature`, `file`, `code`) **được miễn**:
  chúng là bản sao của source, không phải bản dịch. Chỉ trường hiển thị bị
  kiểm.
- **G9 "text node trần"**: text node chứa **chữ cái** thì cấm. Ký tự trang trí
  thuần (`·`, `/`, `→`, dấu câu, khoảng trắng) được phép — chúng không phải
  nội dung cần dịch.

## 9. Sửa 6 lỗi ruff có sẵn

Để CI gác được cả hai cổng ngay từ commit đầu:

- `tablerag/ingestion/tasks.py:32` — bỏ `TableCtx` không dùng
- `tablerag/query/steps/rerank.py:17` — bỏ `get_settings` không dùng
- `tests/unit/test_layout_detection.py:4` — bỏ `pytest` không dùng
- `tests/unit/test_layout_detection.py:127` — E402, chuyển import lên đầu file
- `tests/unit/test_rerank.py:7` — bỏ `pytest` không dùng
- `tests/unit/test_review_queue.py:4` — bỏ `uuid` không dùng

Sau khi sửa: chạy lại `pytest tests/unit` và xác nhận vẫn 843 xanh.

## 10. Tương tác và trợ năng

**Route giữ toàn bộ trạng thái panel.** `#/vi/c/ingest-tables/fn/parse_table`
— mở panel là đẩy một segment. **Một** listener Escape duy nhất, thuộc về
router, bóc **một** tầng.

`stopPropagation` **không** chặn giữa các listener gắn trên cùng target, nên
nếu mỗi panel tự nghe `document` thì một lần bấm sẽ đóng cả chồng và đẩy nhiều
entry vào history. Router giữ route thì không có chuyện đó. Cũng **không dùng
ngăn xếp theo thứ tự mount**: panel đang chạy animation thoát vẫn nằm trong
ngăn xếp và sẽ nuốt phím tiếp theo.

**Không có animation thoát**: panel unmount tức thì, chỉ fade khi vào — không
có panel đang thoát nào còn sống để nuốt phím.

**Escape và nút Back trình duyệt làm cùng một việc**: router ghi `depth` vào
`history.state`; còn depth thì `back()`, hết thì `replace()` về route cha —
không nhồi history.

**Làm mờ đặt trên phần tử cha**, để hai opacity nhân nhau thay vì tranh nhau.

**Không `aria-hidden` cho sơ đồ.** Mỗi node/cạnh bấm được là
`<g role="button" tabindex="0" aria-label>` thật — focus được **và** đọc được.
`aria-hidden` + `tabIndex` là bẫy: control focus được nhưng screen reader
không đọc còn tệ hơn không focus được.

Kèm một mục "bản văn bản" mở ra được, **sinh từ chính JSON vẽ sơ đồ**, liệt kê
node, cạnh **kèm nhãn cạnh**, **nhãn cổng rẽ nhánh** và lối ra. Danh sách hàm
không thay thế được sơ đồ: nó không chứa nhãn cổng rẽ và nhãn cạnh, tức là mất
sạch phần logic.

**SVG không tự xuống dòng.** Tự tính ngắt dòng thành `<tspan>`; chiều cao hộp
lớn theo số dòng; kích thước hộp lấy theo **bản dài hơn trong hai ngôn ngữ**,
để đổi ngôn ngữ không tràn.

## 11. Test hành vi UI (Vitest)

Guard nội dung không thấy được hành vi. Bổ sung, mỗi test nhắm một hành vi đã
từng hỏng trong khi test của nó vẫn xanh:

1. Lọc phase làm **opacity tính toán được** của phần tử con giảm thật — không
   phải "class có được gắn không".
2. Escape bóc **đúng một** tầng; mỗi lần mở panel đẩy **tối đa một** entry
   history.
3. Đổi ngôn ngữ xong DOM không còn dấu vết ngôn ngữ kia.
4. Nhãn SVG dài sinh ≥2 `<tspan>` và chiều cao hộp tăng theo.
5. Hai cạnh cùng cặp node nhận hai đường và hai vị trí nhãn khác nhau.
6. Bản văn bản thay thế chứa **đủ** nhãn cạnh và nhãn cổng rẽ.

Mọi assert đếm theo chính nội dung, không chốt cứng số lượng.

## 12. CI và deploy

`.github/workflows/ci.yml` — CI đầu tiên của repo, ba job nối tiếp:

1. `python-gates` — `pip install -e .[dev]`; `ruff check tablerag tests spike`;
   `pytest tests/unit -q` (đã bao gồm G1–G9).
2. `docs-site` — cần job 1: `npm ci`; `tsc --noEmit`; `vitest run`;
   `vite build`; `actions/upload-pages-artifact` từ `docs-site/dist`.
3. `deploy` — cần job 2, chỉ trên `main`: `actions/deploy-pages`, environment
   `github-pages`, permissions `pages: write` + `id-token: write`.

Guard đỏ thì không có gì được deploy: trang không thể lên mạng ở trạng thái
nói sai về code.

**Việc chỉ người dùng làm được**: Settings → Pages → Source đổi từ *Deploy from
a branch* sang **GitHub Actions**. Chừng nào chưa đổi, job 3 fail. Pages trên
repo private cần gói Enterprise.

**Windows**: cài `node_modules` bằng PowerShell, không qua Git Bash — qua Git
Bash, npm nhận diện sai platform nên bỏ qua optional dependency native (rollup)
và sinh shim thiếu file `.cmd`.

## 13. Nghiệm thu

**Trước khi báo xong:**

1. Chạy đủ cổng, **từng lệnh trần, in exit code riêng**. `cmd | tail -2` trả
   exit code của `tail`, nên `&&` phía sau vẫn chạy dù lệnh trước đã fail —
   đã từng khiến một commit hỏng lọt qua.
2. **Với mỗi test bảo vệ một hành vi: phá hành vi, xem test đỏ, khôi phục.**
   Báo cáo cuối liệt kê test nào đã thật sự thấy đỏ. Không tin một test chưa
   từng thấy nó đỏ.
3. **Mở trang bằng mắt**: Playwright headless chụp từng lớp, và ảnh được đọc
   lại để soi chữ tràn, đường chồng, tương phản kém. Chụp ở desktop rộng ·
   375px · `prefers-reduced-motion: reduce` · **cả hai ngôn ngữ**. Nếu
   Playwright không tải được browser trên máy này, **nói thẳng là không mở được
   trang**, không ngụ ý đã kiểm.
4. Xác nhận không sót chữ ngôn ngữ kia sau khi đổi ngôn ngữ.

## 14. Cố tình không làm

- **Không** search toàn văn — trang đủ nhỏ để duyệt bằng lọc.
- **Không** tự sinh nội dung từ AST. Sơ đồ và lời giải thích do người viết,
  guard chỉ canh chúng không lệch. Nội dung tự sinh sẽ đúng nhưng vô nghĩa.
- **Không** phủ `tests/`, `spike/`, `scripts/*.sh` trong G3 — đã chốt phạm vi
  `tablerag/` + `frontend/`. `scripts/reindex_all.py` và `debug_context.py` vẫn
  có mặt vì chúng nằm trong `tablerag/`.
- **Không** đụng `frontend/` sản phẩm ngoài việc đọc nó.

## 15. Thứ tự thực hiện

Guard viết **trước** nội dung. Không phải để đẹp quy trình: G3 đòi phủ 100%
module, nên nó sẽ đỏ suốt giai đoạn viết nội dung và chỉ xanh khi component
cuối cùng được viết xong — đúng là cái nó sinh ra để làm. Viết guard sau thì
guard đầu tiên chạy đã xanh, và một guard chưa từng thấy đỏ là guard chưa được
kiểm chứng.

1. Sửa 6 lỗi ruff (§9); dựng `.github/workflows/ci.yml`.
2. Schema content + G1–G9 + `docs-site/tools/relink.py`, với một hạt giống nội
   dung nhỏ. Kỳ vọng: G3/G4/G7 **đỏ** — ghi lại thông báo lỗi của chúng.
3. Khung trang: routing, Escape một tầng, đổi ngôn ngữ, `.dimmed` trên cha,
   SVG ngắt dòng thành `<tspan>`.
4. Lớp 1: nodes, edges + hợp đồng, bảng sở hữu → G4, G7 xanh.
5. Lớp 2 + Lớp 3: 21 component → G3 xanh.
6. Hai sơ đồ "cỗ máy" + lọc phase.
7. Test hành vi Vitest (§11).
8. Nghiệm thu (§13): phá từng test xem đỏ, chạy đủ cổng, chụp ảnh và soi.

Giai đoạn 2 kết thúc với CI **đỏ có chủ đích**; chỉ giai đoạn 5 mới đưa nó về
xanh. Không commit trạng thái đỏ lên `main`.
