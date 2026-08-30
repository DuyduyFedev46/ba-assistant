# Solution Design — Platform hiểu-họp theo nhịp cho BA

> Tài liệu thiết kế giải pháp cho bài toán ở brief. Đọc kèm brief gốc.
> **v3** — FE: **Next.js** (trên Firebase Hosting); engine brain: **Model Router đa model** (task → model, khai báo config, có fallback + nâng cấp động).
> Lịch sử: v1 = VPC tự dựng; v2 = Firebase + Supabase + tầng MCP. Phần lõi (state-editing + hợp đồng engine/profile) **không đổi qua các phiên bản** — nó host/model-agnostic.

---

## 0. TL;DR

Xây một platform **API-first, headless** biến chuỗi transcript lộn xộn của buổi họp → **một trạng thái sống có cấu trúc, revision-aware** (đã chốt / còn treo / việc / bị lật), cập nhật **theo từng nhịp** (patch, không append), rồi đóng gói về đúng repo dự án. Engine là **hằng số dùng chung**; cái riêng của mỗi dự án nằm ở **profile (YAML)**; mọi LLM call đi qua **Model Router** (task nào → model nào, khai báo config); mọi tích hợp ngoài đi qua **tầng Connector/MCP**.

### Các trục đã chốt (v3)
| Trục | Chọn | Hệ quả chính |
|---|---|---|
| **FE** | **Next.js** (App Router) trên **Firebase Hosting** | SSR qua Firebase webframeworks (⚠️verify); server-side của Next **chỉ auth/session, KHÔNG logic engine** |
| **Host engine + API** | **Cloud Run** (FastAPI, Python) | Firebase proper không chạy engine Python stateful; Hosting rewrite `/api` → Cloud Run |
| **Engine brain** | **Model Router đa model** (§9) — Claude làm mặc định cho core | task → model khai báo config; nhiều provider (Anthropic/OpenAI/Gemini/self-host); fallback chain; nâng cấp động khi nhịp phức tạp |
| **DB + Auth + Storage + Realtime** | **Supabase** (Postgres + Auth + Storage + Realtime + Queue) | thay Postgres/Redis/MinIO/OIDC tự quản |
| **Stack engine** | **Python / FastAPI** | khớp hệ STT/LLM |
| **Scope bản này** | **Full platform** | FE + API + engine + ingest + routing + packaging |

---

## 1. Bài toán (rút gọn để định vị design)

4 lớp khó, theo thứ tự ưu tiên giải:
1. **Nhịp sau vặn lại nhịp trước** (lật / trả lời / hiệu chỉnh) — *bản chất của "hiểu cuộc họp"*, toàn bộ giá trị → **§5**.
2. **Họp = chuỗi nhiều nhịp không độc lập** — cắt nhịp không nút bấm → **§6**.
3. **Xung đột chú ý** — không đụng tay khi họp, tự chảy.
4. **Thiếu bức tranh "trạng thái sống"** — dashboard cho người chủ trì → **§8**.

KHÔNG phải bài toán transcription (STT là đầu vào có sẵn, ngoài phạm vi).

---

## 2. Kiến trúc tổng thể (v3)

### 2.1. Sơ đồ

```
┌─────────────────────────────── GOOGLE CLOUD PROJECT (Firebase) ───────────────────────────┐
│                                                                                           │
│  [Thiết bị = mic]   ghi + STT ngoài (Whisper/FunASR, NGOÀI phạm vi)                       │
│         │ POST chunk (idempotent)                                                         │
│         ▼                                                                                 │
│  [FIREBASE HOSTING — Next.js]  ──rewrite──►  [CLOUD RUN — API + ENGINE (FastAPI/Python)]  │
│   SSR (webframeworks, CF gen2)               · Segmenter · StateEditor · Mapper · Packager│
│   Server-side CHỈ: auth/session              · Ingest endpoint (idempotent)               │
│   Client: render + input                     · Model Router (§9)                          │
│        │ REST/JSON                           · Connector host (calendar/repo/MCP — §10)   │
│        │                                            │                                     │
│        └────── Realtime subscribe ──────────────────┼─── (Supabase Realtime: Postgres      │
│                                                     │     Changes trên snapshot state)    │
└─────────────────────────────────────────────────────┼─────────────────────────────────────┘
                                                      │ TLS (public internet)
                                                      ▼
                          ┌─────────────────────────────────────────────┐
                          │  SUPABASE (SaaS)                             │
                          │  · Postgres: state, op_log, project, profile │
                          │    + RLS theo project                        │
                          │  · Auth: JWT, RBAC qua claims                │
                          │  · Realtime: Postgres Changes → đẩy state FE │
                          │  · Storage (S3-compatible): audio/transcript │
                          │  · Queue (pgmq — ⚠️beta): ingest decouple     │
                          └─────────────────────────────────────────────┘
                                            │
                     ┌──────────────────────┼───────────────────────────┐
                     ▼                      ▼                           ▼
              Anthropic API           OpenAI/Gemini/…          Self-host LLM (vLLM)
              (Claude — mặc định)      (provider phụ)           (khe privacy, bản sau)
              ── tất cả qua MODEL ROUTER (§9), policy config, TLS ──
```

### 2.2. Luật ranh giới (KHÔNG vi phạm)

- **LUẬT TỐI THƯỢNG:** mọi logic engine (cắt nhịp, biên tập state, đọc profile, khử mâu thuẫn, packaging, chọn model) nằm **hoàn toàn** trong engine (Cloud Run). FE **tuyệt đối không** chứa logic engine.
  - **Với Next.js cụ thể:** server components / API routes / server actions của Next **chỉ được làm auth-session (Supabase SSR) và proxy mỏng** — KHÔNG được nhét cắt nhịp, biên tập state, đọc profile vào Next server. Engine là Cloud Run, Next chỉ gọi REST + subscribe Realtime.
  - *Bằng chứng cưỡng chế:* **test-headless** (§14) — tắt FE, mọi nghiệp vụ vẫn chạy đủ qua API/pytest.
- **Ingest = điểm decouple:** thiết bị ghi và engine không biết nhau.
- **4 hộp thay độc lập:** đổi STT, đổi model (router config), đổi FE, đổi storage, đổi connector — không lan sang hộp khác.

---

## 3. Giới hạn Firebase + Supabase vs solution (đã phân tích ở v2, tóm lại)

- **Firebase không chạy engine Python** → engine + API = **Cloud Run**; Firebase Hosting chỉ FE.
- **Next.js trên Firebase:** Firebase Hosting có hỗ trợ framework (webframeworks) deploy Next.js SSR lên **Cloud Functions gen2 / Cloud Run**. ⚠️ *Verify phiên bản firebase-tools hiện tại.* Nếu muốn tối giản nhất: Next `output: 'export'` (static) — chọn sau khi đo nhu cầu SSR thật (chủ yếu là auth session).
- **Mất VPC riêng:** Supabase là SaaS ngoài VPC; traffic TLS công cộng. Bù đắp: RLS, at-rest AES-256, retention, no-retention phía LLM, redaction (bản sau). **Cần xác nhận stakeholder bảo mật.**
- **Realtime:** Supabase Realtime (Postgres Changes) thay SSE/Redis. ⚠️Verify rate limits — nhu cầu chỉ vài push/phút/meeting.
- **Queue:** Cloud Tasks (hoặc Supabase Queue ⚠️beta). Idempotent theo `chunk_id`.
- **Auth:** Supabase Auth + RLS (không dùng Firebase Auth để tránh 2 hệ auth).
- **Storage:** Supabase Storage (S3-compatible) + retention policy cho audio.

---

## 4. Mô hình lõi — Hợp đồng Engine ↔ Profile (KHÔNG ĐỔI)

> Trái tim. FE đẹp mà engine append thì = 0. Giải chắc phần này **trước tiên**.

### 4.1. Engine chỉ làm việc với nguyên thủy trừu tượng
- `DECISION` (CHỐT), `OPEN` (TREO), `ACTION` (VIỆC), `REVISION` (LẬT) — **một quan hệ**, không phải node thứ 4: item mới thay/đảo item cũ.

### 4.2. Profile = config khai báo (YAML), KHÔNG phải plugin code

```yaml
# profiles/family-package.yaml
project: family-package
display_name: "Family Package — requirement/design"

vocabulary:
  aliases:      { "gói GĐ": "family package", "tier": "gói dịch vụ" }
  participants: ["BA-Ha", "BE-Nam", "FE-Linh", "Ecom-Tuan"]

routing:
  connector:        calendar-google            # ← tầng Integration (§10)
  calendar_tags:    ["FamilyPkg", "#fp"]
  repo:             "git@git.company:be/family-pkg.git"
  file_convention:  "meetings/{date}-{slug}.md"

item_schemas:                                  # BƠM field riêng vào từng nguyên thủy
  DECISION:
    fields:
      - { name: replaces_decision, type: ref }
      - { name: impacts,           type: enum, values: [contract, tier, rule] }
  ACTION:
    fields:
      - { name: owner, type: person }
      - { name: due,   type: date }

final_doc:
  enabled:  true
  template: "templates/brd_family.md.j2"       # Jinja2

segmenter:                                      # ngưỡng cắt nhịp (calibrate được)
  silence_gap_sec: 8
  closing_cues:    ["ok chốt", "vậy quyết", "chuyển sang", "next"]
```

### 4.3. Cơ chế nối sạch (seam)
```
profile.item_schemas ──► profile_loader ──► DỰNG ĐỘNG JSON tool-schema
                                                    │
                         state + đoạn nhịp mới ─────┤
                                                    ▼
                                   MODEL ROUTER (§9) ──► provider ──► Claude/…
                                                    │
                                                    ▼
                                        danh sách OPERATIONS (§5.2)
```
- Engine đọc `item_schemas` → **dựng động** tool-schema. **Engine code không đổi; chỉ schema thay.**
- ProfileMapper dùng cùng khai báo để map `StateItem` → file output theo `final_doc.template` + `file_convention`.

> Engine chỉ biết "có một `DECISION`, nó vừa bị lật"; **không cần biết** nó về payload hay màu nút. "Về cái gì" ⟶ profile.

---

## 5. State-editing revision-aware (PHẦN KHÓ NHẤT — KHÔNG ĐỔI)

### 5.1. State là MỘT tài liệu sống, không phải list nối đuôi

```
StateItem (bảng state_items trong Supabase):
  id:            UUID ổn định            # không phải dòng text trôi nổi
  type:          DECISION | OPEN | ACTION
  status:        active | superseded | answered | flagged
  subject_key:   string                  # khoá chủ đề, nối các nhịp cùng nói 1 thứ
  core:          { title, body, rationale }         # field trừu tượng chung
  profile_fields:{ ... }                 # field riêng do PROFILE khai báo (§4.2)
  provenance:    { nhip_id, transcript_span, quote }# evidence — truy vết được
  supersedes:    item_id | null          # cạnh LẬT
  superseded_by: item_id | null
  answered_by:   item_id | null          # OPEN được trả lời bởi item nào
  history:       [ { nhip_id, op, before, after } ]
  created_nhip, updated_nhip
```

- **`REVISION`/LẬT là một cạnh** (`supersedes`/`superseded_by`). Item cũ → `status=superseded`, **giữ lại** (không xoá trắng).
- **`OPEN` được trả lời** → `status=answered` + `answered_by`, HOẶC chuyển thành `DECISION` mới. Rời panel "còn treo".
- State hiện tại = `fold(op_log)`; lưu **cả snapshot** (`meeting_state`) để đọc nhanh — và snapshot này chính là thứ Realtime đẩy xuống FE.

### 5.2. Biên tập theo nhịp = PATCH, KHÔNG rebuild

```
INPUT:  MeetingState hiện tại (compact) + transcript nhịp mới + profile
   │
   ▼  Model Router → provider → structured output (tool-schema dựng động từ profile)
   │
OUTPUT: danh sách OPERATIONS (patch) — KHÔNG phải state nguyên khối:
   ├─ CREATE(type, subject_key, fields, provenance)
   ├─ SUPERSEDE(old_id, new_item)          # LẬT hợp lệ
   ├─ ANSWER(open_id, answer | new_decision)
   ├─ AMEND(item_id, field_changes)        # hiệu chỉnh định nghĩa đã nêu
   └─ FLAG(item_id | new, reason)          # đề xuất mơ hồ, cần xác nhận
   │
   ▼
apply(patch) → MeetingState mới (transactional trong Postgres);
               ghi từng op vào op_log;
               UPDATE snapshot → Realtime tự đẩy xuống FE.
```

- **Không dựng lại từ 0 mỗi nhịp** → rẻ, nhanh, giữ trí nhớ xuyên nhịp.
- Prompt engine **generic**; phần "về cái gì" đến từ **field profile bơm vào schema**.

### 5.3. Ví dụ minh hoạ (kịch bản acceptance §14)

```
Nhịp @05:  "OK vậy chốt đi phương án A cho luồng thanh toán."
  → CREATE(DECISION, subject_key="payment-flow",
           core={title:"Dùng phương án A cho thanh toán"})   ⇒ item D1 (active)

Nhịp @12:  "Còn việc rate limit thì tính sao? — chưa rõ, để mở."
  → CREATE(OPEN, subject_key="rate-limit",
           core={title:"Rate limit tính sao?"})               ⇒ item O1 (active)

Nhịp @40:  "Thôi, đổi sang phương án B, A không kịp deadline."
  → SUPERSEDE(old_id=D1, new_item=DECISION{subject_key:"payment-flow",
             core={title:"Dùng phương án B", rationale:"A không kịp deadline"},
             profile_fields:{replaces_decision:D1, impacts:"contract"}})
                                            ⇒ D2 (active), D1 → superseded

Nhịp @55:  "Rate limit thì chốt 100 req/s nhé." (trả lời O1)
  → ANSWER(open_id=O1, new_decision=DECISION{subject_key:"rate-limit",
           core={title:"Rate limit = 100 req/s"}})
                                            ⇒ O1 → answered (answered_by=D3), D3 (active)
```

**Kết quả state cuối:** DECISION=B `active` (A `superseded`, không song song); OPEN rate-limit đã `answered`, rời panel treo. ✅ đúng chốt cuối.

### 5.4. Quyết định mở #3 — thế nào là "LẬT" hợp lệ

| Tình huống | Tín hiệu | Hành động |
|---|---|---|
| **Lật rõ** | (a) **cam kết** trên phương án mới ("ok chốt B", "thôi đổi sang…") **VÀ** (b) mâu thuẫn trực tiếp một `DECISION` `active` **cùng `subject_key`** | `SUPERSEDE` |
| **Chỉ đang cân nhắc** | nêu lựa chọn, chưa cam kết | `CREATE(OPEN)` hoặc để nguyên — **KHÔNG** supersede |
| **Mơ hồ (ở giữa)** | không rõ đã cam kết chưa | `FLAG` "đề xuất lật — cần xác nhận", nổi trong panel *cần quyết*, **không tự áp** |

`FLAG` là **human-in-the-loop nhẹ, sau nhịp** — BA chỉ liếc, không bắt buộc thao tác giữa mạch → không phá luật "không đụng tay khi họp".

---

## 6. Cắt nhịp (Segmenter) — quyết định mở #2 & #5

Không có nút bấm → engine tự nhận ranh giới nhịp. **Hai tầng, rẻ trước, LLM sau:**
1. **Heuristic pre-filter** (gần như free): khoảng lặng > `segmenter.silence_gap_sec`, đổi người dẫn, cue-phrase đóng (`segmenter.closing_cues`), buffer vượt ngưỡng.
2. **LLM confirm** (chỉ khi tầng 1 nghi ngờ): qua Model Router task `segment_confirm` — "nhịp đã khép chưa + có nội dung chốt/treo/việc không".

- Ranh giới **confirm** ⟶ trigger pass state-edit (§5.2) trên đoạn vừa khép.
- **Push xuống FE (#5):** snapshot đổi **chỉ khi** (a) nhịp khép **VÀ** (b) patch khác rỗng (state thực sự đổi). Realtime chỉ phát khi UPDATE → **không nhấp nháy cướp chú ý**.
- "Khép" định nghĩa rõ = ranh giới confirm tầng 2. Ngưỡng là **tham số per profile**, calibrate bằng dữ liệu họp thật.

---

## 7. Định tuyến "đúng dự án" — quyết định mở #4

- **Đường chính:** buổi họp ↔ project qua **calendar event** (Google Calendar + Outlook). Pipeline gọi **connector calendar** (§10) đọc tag/tên event → match `routing.calendar_tags` → biết repo đích. **Khỏi engine đoán, khỏi user bấm.**
- **Fallback (không có event khớp):**
  1. meeting → `unassigned`;
  2. engine vẫn dựng state bằng `profiles/generic.yaml` — không mất dữ liệu;
  3. FE hiện chip "chưa gán dự án" → BA gán **1 chạm sau họp** (HITL có chủ đích, được phép);
  4. khi gán, engine **re-map** state qua profile đúng rồi packaging.

---

## 8. Đầu ra "trạng thái sống" (FE render — Next.js)

**Bảng điều khiển cho người chủ trì**, KHÔNG phải bản tóm tắt. FE render thuần từ `GET /meetings/{id}/state` + subscribe Realtime. Thứ tự ưu tiên:
1. **Còn treo / cần quyết** — nổi bật NHẤT (gồm cả `FLAG` "đề xuất lật cần xác nhận").
2. **Đã chốt** — kèm `rationale` + "thay cho phương án nào" (nếu là kết quả `supersede`).
3. **Action** — việc • ai • hạn; **chưa gán người → cờ đỏ**.
4. **Bất đồng chưa giải** — ai muốn gì, vướng đâu.
5. **Ảnh hưởng contract/scope** — field profile bơm vào, chảy thẳng BRD.

**Ranh giới Next.js (quan trọng):**
- Client components: render state (nhận từ Realtime) + input + gọi REST — toàn bộ tương tác engine.
- Server components / route handlers / server actions: **CHỈ** auth-session (`@supabase/ssr`) và proxy mỏng nếu cần. **0 dòng logic engine** — cắt nhịp, biên tập state, đọc profile là của Cloud Run.
- Trải nghiệm mục tiêu: hết một nhịp, BA **liếc sang → bảng đã tự nhảy tới trạng thái mới nhất**.

---

## 9. Model Router (MỚI v3 — dùng nhiều model, task nào model nào)

### 9.1. Nguyên tắc
- Engine **không gọi trực tiếp** bất kỳ provider nào. Mọi LLM call đi qua **Model Router** với một `task_id` khai báo.
- **Task nào → model nào** là **policy config (YAML)**, không phải code. Đổi model / thêm provider / đổi tỉ lệ rẻ-đắt = sửa config, **0 dòng engine sửa**.
- Mỗi provider có **adapter** riêng thoả chung một interface — thêm OpenAI/Gemini/self-host = thêm 1 adapter class, router tự nạp.

### 9.2. Policy khai báo
```yaml
# config/model_policy.yaml
defaults:  { provider: anthropic, model: claude-sonnet-5 }

tasks:                                    # task nào dùng model nào
  segment_confirm:                        # phân loại ranh giới nhịp — nhẹ, gọi nhiều
    model: claude-haiku-4-5
    budget: { max_latency_ms: 3000, max_cost_per_1k: $0.01 }

  beat_router:                            # (tuỳ chọn) phân loại độ phức tạp nhịp — rẻ
    model: claude-haiku-4-5

  state_edit:                             # ★ CORE revision-aware — model mạnh nhất
    model: claude-opus-5
    escalate:                             # nâng cấp động dựa trên nhịp
      - if: beat_has_revision_cue         #   có dấu hiệu lật → chắc chắn opus
        model: claude-opus-5
    fallback:                             #   opus lỗi → sonnet
      - { provider: anthropic, model: claude-sonnet-5 }

  profile_map: { model: claude-sonnet-5 }
  final_doc:   { model: claude-sonnet-5 }

  redact:                                 # khử entity nhạy cảm (bản sau)
    model: claude-haiku-4-5

providers:                                # danh sách provider sẵn sàng
  anthropic:  { kind: cloud,  secrets: ANTHROPIC_API_KEY }
  openai:     { kind: cloud,  secrets: OPENAI_API_KEY, disabled: true }   # bật khi cần
  gemini:     { kind: cloud,  secrets: GEMINI_API_KEY, disabled: true }
  selfhosted: { kind: selfhost, url: "http://vllm.internal:8000", disabled: true }  # khe privacy
```

### 9.3. "Detect task nào dùng model nào" — hai mức
1. **Định tuyến tĩnh (mặc định):** mỗi call site của engine mang `task_id` (`segment_confirm`, `state_edit`, `profile_map`, `final_doc`…) → router tra policy lấy model. Đủ cho 95% trường hợp.
2. **Nâng cấp động (escalation):** trước `state_edit`, một pass **rẻ** (`beat_router`, haiku) quét nhịp: có dấu hiệu lật/trả lời câu treo/bất đồng không → **nhịp phức tạp nâng lên opus, nhịp đơn giản dùng sonnet** → tiết kiệm chi phí mà không hy sinh chất lượng chỗ khó.
   - `escalate` rules là khai báo (`if:` trên tín hiệu nhịp), engine chỉ đọc kết quả — thêm rule không sửa engine.
   - Có thể tắt (`beat_router: null`) nếu muốn đơn giản tuyệt đối.

### 9.4. Interface (Python)
```python
# app/llm/router.py
class LLMProvider(Protocol):
    async def complete(self, *, messages, tools, model, **opts) -> StructuredOutput

class ModelRouter:
    async def run(self, task: TaskId, *, messages, tools,
                  beat_hints: dict | None = None) -> StructuredOutput
    # 1. tra policy (task → model), áp escalation rules nếu có
    # 2. thử provider/model chính → lỗi/timeout/limit → fallback chain
    # 3. ghi audit (task, model dùng, latency, cost) vào bảng llm_calls
```
- Engine call site chỉ viết: `await router.run("state_edit", messages=…, tools=…, beat_hints=hints)`. Không biết provider/model nào được chọn.
- Structured output vẫn là **tool-schema dựng động từ profile** (§4.3) — router chỉ là tầng vận chuyển.

### 9.5. Ràng buộc & privacy
- **Mọi call qua router đều audit** (`llm_calls`: task, model, tokens, latency, cost) → đo được model nào ăn tiền ở đâu, chỉnh policy bằng dữ liệu.
- Provider cloud = dữ liệu đi ra ngoài → cùng policy privacy §3: gửi tối thiểu, TLS, no-retention nơi khả dụng, **redact trước khi gửi provider lạ** (task `redact`, bản sau).
- Khe `selfhosted` (vLLM/Ollama) dành sẵn: khi công ty siết privacy → trỏ `state_edit` sang self-host, **engine không đổi**.
- Provider mới = 1 adapter class + 1 entry config. Test: `test_model_router.py`.

---

## 10. Tầng Integration / MCP (v2, giữ nguyên)

### 10.1. Nguyên tắc
- Engine **không gọi trực tiếp** Google Calendar API, Git, Notion, Jira… Engine chỉ nói chuyện với **Connector protocol**. Thêm/bớt tích hợp không đụng engine.
- **Hai adapter cùng thoả một protocol:**
  1. **Direct adapter** — SDK native (Google Calendar, MS Graph, GitHub): đường chính, nhanh, ít phụ thuộc.
  2. **MCP adapter** — host **MCP client** (Python `mcp` SDK, HTTP/SSE remote hoặc local): mỗi MCP server là một nguồn tools; **gọi thêm MCP sau = thêm config, 0 dòng engine sửa**.

### 10.2. Protocol (Python, trừu tượng)
```python
# app/integrations/protocol.py
class Connector(Protocol):
    connector_id: str
    async def list_tools(self) -> list[ToolSchema]          # tương thích Anthropic tool-use format
    async def call(self, name: str, args: dict) -> ToolResult  # timeout, retry idempotent, audit
```
- Tool từ connector **nạp thẳng** vào danh sách tools của pass state-edit (qua Model Router) — khi routing cần đọc calendar, model tự gọi `calendar.resolve_event`.

### 10.3. Registry — nạp connector từ khai báo
```yaml
# config/connectors.yaml
connectors:
  - id: calendar-google
    transport: direct
    config:  { calendar_ids: [...] }
  - id: repo-github
    transport: mcp               # gọi MCP server git, không code direct
    config:  { url: "https://mcp.example.com/git", transport: sse, headers: {...} }
  - id: docs-notion              # thêm sau, engine không đổi
    transport: mcp
    config:  { url: "https://mcp.example.com/notion" }
```

### 10.4. Dùng connector ở đâu
| Điểm trong luồng | Connector | Tool điển hình |
|---|---|---|
| Định tuyến dự án (§7) | `calendar-google` / `calendar-outlook` | `resolve_event(event_id) → project` |
| Đóng gói | `repo-github` (direct hoặc MCP) | `create_branch`, `commit_files`, `create_pr` |
| (Sau này) sinh BRD/task | `docs-notion`, `task-jira`, … | tạo page/ticket từ state đã đóng gói |
| (Sau này, đối xứng) | **platform tự phơi thành MCP server** cho Claude Code đọc state họp — ngoài scope bản này | |

### 10.5. Ràng buộc
- Connector chỉ **đọc/ghi ngoài platform** — KHÔNG chứa logic engine.
- Mọi call connector ghi **audit log**.
- MCP call ra ngoài = **dữ liệu nhạy cảm đi ra** — gửi tối thiểu (vd `event_id`, không gửi transcript), TLS bắt buộc.

---

## 11. Stack & thành phần cụ thể (v3)

| Hộp | Công nghệ | Ghi chú |
|---|---|---|
| FE | **Next.js** (App Router, TS) | SSR qua Firebase webframeworks ⚠️verify; server-side chỉ auth/session |
| FE hosting | **Firebase Hosting** | rewrite `/api` → Cloud Run |
| API + Engine | **Cloud Run** (FastAPI, Python 3.12) | `min-instances` giờ họp |
| Engine brain | **Model Router** (§9) + providers | Anthropic (mặc định), OpenAI/Gemini/self-host (khe); policy YAML |
| Ingest | FastAPI endpoint + **Cloud Tasks** (hoặc Supabase Queue ⚠️beta) | idempotent theo `chunk_id` |
| Realtime push | **Supabase Realtime** (Postgres Changes) | snapshot đổi → FE subscribe nhận |
| DB | **Supabase Postgres** + RLS + Supavisor | state, op_log, project, profile, meeting, llm_calls |
| Auth | **Supabase Auth** (JWT + claims) + `@supabase/ssr` ở Next | RBAC theo project qua RLS |
| Storage | **Supabase Storage** (S3-compatible) | audio/transcript, at-rest, retention |
| Profile | YAML (versioned) + Jinja2 template | khai báo |
| Packager | GitPython / `gh` — qua **connector repo** (§10) | commit/PR theo `file_convention` |
| Integrations | `app/integrations/` — protocol + registry + adapters (direct/MCP) | thêm MCP = thêm config |
| Secrets | Google Secret Manager | API keys, supabase keys, MCP tokens |
| Deploy | Cloud Run deploy (CI), Firebase CLI, Supabase migrations | TLS out, tắt log payload |

---

## 12. API surface (bằng chứng headless)

Mọi nghiệp vụ qua API — FE tắt vẫn chạy đủ:

| Method | Path | Việc |
|---|---|---|
| POST | `/projects` | tạo project + gắn profile |
| GET/PUT | `/projects/{id}/profile` | xem/sửa profile (khai báo) |
| POST | `/meetings` | mở meeting (auto-route calendar hoặc `unassigned`) |
| POST | `/meetings/{id}/ingest` | nhận transcript chunk (streaming, idempotent) |
| GET | `/meetings/{id}/state` | trạng thái sống hiện tại (JSON) |
| — | Realtime channel `meeting:{id}` | Supabase Realtime đẩy khi state đổi |
| GET | `/meetings/{id}/oplog` | lịch sử operations (audit) |
| POST | `/meetings/{id}/assign` | gán project (fallback routing) |
| POST | `/meetings/{id}/package` | đóng gói → repo đích (qua connector) |

---

## 13. Cấu trúc mã nguồn (khi thực thi)

```
backend/
  app/main.py                    FastAPI app + routers
  app/api/
    projects.py  meetings.py  ingest.py
  app/engine/                    # ★ KHÔNG ĐỔI khi thêm loại họp / thêm model / thêm MCP
    segmenter.py                 cắt nhịp (heuristic + LLM confirm qua router)
    state_editor.py              PASS state-edit: state+nhịp → operations → apply
    operations.py                CREATE/SUPERSEDE/ANSWER/AMEND/FLAG + apply/fold
    profile_loader.py            YAML → dựng động tool-schema
    profile_mapper.py            StateItem → schema riêng + render template
    packager.py                  → repo đích (qua connector repo)
  app/llm/                       # ★ MODEL ROUTER (mới v3)
    router.py                    ModelRouter: task → model, escalation, fallback, audit
    tasks.py                     TaskId enum + beat_hints
    providers/
      base.py                    LLMProvider protocol
      anthropic.py               Claude (mặc định)
      openai.py  gemini.py  selfhosted.py
  app/integrations/              # ★ TẦNG MCP/CONNECTOR
    protocol.py  registry.py
    adapters/
      direct_calendar_google.py  direct_calendar_outlook.py  direct_repo_git.py
      mcp_client.py              host MCP servers (mcp SDK, HTTP/SSE)
  app/models/                    SQLAlchemy: StateItem, MeetingState, OpLog, Project, Profile, LLMCall
  app/db/                        Supabase client + RLS-aware queries + migrations
  config/
    model_policy.yaml            task → model (§9.2)
    connectors.yaml              khai báo connectors (§10.3)
  profiles/
    family-package.yaml          profile mẫu #1
    ux.yaml                      profile #2 (chứng minh test-đa-dự-án)
    generic.yaml                 fallback routing
  templates/
    brd_family.md.j2
  tests/
    test_revision.py             kịch bản §5.3 (quan trọng nhất)
    test_multi_project.py        thêm profile, 0 sửa engine
    test_model_router.py         task→model đúng policy; swap provider; fallback; escalation (mới v3)
    test_connector_swap.py       đổi calendar direct→MCP, engine không đổi
    test_headless.py             ingest→state→package qua API, FE off
frontend/                        Next.js (App Router, TS)
  app/(auth)/...                 login (Supabase SSR) — CHỈ auth
  app/meetings/[id]/...          dashboard trạng thái sống (client components, Realtime)
  lib/supabase.ts  lib/api.ts    REST client mỏng — KHÔNG logic engine
supabase/                        migrations + RLS policies
firebase.json                    hosting config + rewrite /api → Cloud Run
```

### Thứ tự build (giải chắc lõi trước — đúng ghi chú brief mục 11)
1. **Core model + StateEditor + operations** — unit-test bằng transcript giả (chưa cần FE/STT).
2. **Profile loader/mapper + 1 profile thật** → pass test-đa-dự-án.
3. **Model Router** (provider anthropic trước; test swap) + nối vào engine.
4. **API + Ingest + Supabase (DB/Auth/Realtime).**
5. **Segmenter** (heuristic → LLM).
6. **Tầng Connector/MCP** + calendar routing + packager.
7. **FE Next.js** lên Firebase Hosting.

---

## 14. Verification — map thẳng acceptance brief §10 + các tầng mới

| Test | Cách kiểm | Pass = |
|---|---|---|
| **Revision** (quan trọng nhất) | feed transcript §5.3 (lật A→B + 1 câu treo trả lời cuối) | `GET state`: chỉ DECISION=B `active`, A `superseded` (không song song); OPEN `answered`, rời panel treo. Ra mâu thuẫn/2 mục song song = **SAI** |
| **Đa-dự-án** | thêm `profiles/ux.yaml` + template, chạy lại | ra schema UX; `git diff app/engine/` = **rỗng** |
| **Model router (mới)** | ① policy đổi `state_edit` sang provider khác (mock) → pipeline chạy; ② provider chính lỗi → fallback; ③ nhịp có revision-cue → escalation; ④ audit `llm_calls` có task/model/latency | ①②③④ đúng; `git diff app/engine/` = **rỗng** |
| **Headless** | pytest gọi API, FE off | luồng ingest→state→package chạy đủ |
| **Không-đụng-tay** | chunk vào ingest → state sống + file đóng gói | 0 thao tác thủ công (trừ HITL có chủ đích: xác nhận `FLAG`, gán project fallback) |
| **Realtime** | state đổi sau 1 nhịp | FE nhận push qua Supabase Realtime ≤ vài giây, **không** push khi patch rỗng |
| **Connector swap** | đổi `calendar-google` từ `direct` sang `transport: mcp` | pipeline chạy như cũ; `git diff app/engine/` = **rỗng** |
| **FE mỏng** | grep `frontend/`: không có từ khoá logic engine (segment/state_edit/profile_map…) | chỉ thấy REST call + render + auth |

Chạy: `supabase start` (local dev) hoặc Supabase cloud → `pytest backend/tests` → deploy Cloud Run + `firebase deploy` → kịch bản e2e transcript mẫu.

---

## 15. Rủi ro & giả định (nêu rõ, không chốt ngầm)

- **Privacy — SaaS ngoài VPC (căng nhất):** Firebase+Supabase **đảo ngược** lựa chọn "VPC riêng" trước đó. Mitigations: RLS, at-rest AES-256, TLS, retention policy, no-retention phía LLM, **redact trước khi gửi provider/connector lạ**, khe `selfhosted` LLM sẵn trong Model Router. **Xác nhận stakeholder bảo mật trước khi ship.**
- **Đa provider = thêm điểm dữ liệu đi ra** — policy chỉ cho phép provider trong danh sách cho phép; mọi call audit.
- ⚠️ **Mục nhạy phiên bản cần verify:** Firebase webframeworks cho Next.js SSR, Supabase Realtime rate limits, Supabase Queue GA, Storage S3 API, SSO plan, Cloud Tasks quota. (Session này không có web access — verify trước khi code.)
- **Ngưỡng cắt nhịp / LẬT** sẽ sai vòng đầu — calibrate bằng config/eval, không sửa code.
- **Model routing** phụ thuộc chất lượng phân loại `beat_router` (escalation) — nếu sai nhiều thì tắt escalation, dùng định tuyến tĩnh; đo bằng audit `llm_calls`.
- **STT** là đầu vào có sẵn (ngoài phạm vi); ingest decouple.
- **Calendar routing** phụ thuộc kỷ luật đặt tag/tên event của người dùng — fallback `unassigned` gánh.

---

## 16. Prior art — mượn gì, tự làm gì

| Dự án | Mượn (tham chiếu logic) | Tự làm (giá trị cốt lõi) |
|---|---|---|
| VPBuddy | schema phân loại phát biểu (REQ/GOAL/...) | — nó **append**, không biên tập lại khi nhịp sau lật |
| Talktrace | khái niệm state + evidence + event | — "revision" của nó ở **tầng transcript**, không phải **tầng quyết định** |
| JKinco Listen | scene detection (~cắt nhịp) | — nó sinh minutes offline, không có state sống revision-aware |

**Tự làm (còn trống, là giá trị dự án này):** ① **revision ở tầng quyết định** (§5), ② **cấu hình đa dự án** (§4), ③ khớp workflow BA thật + nối thẳng repo, ④ **tầng connector/MCP** (§10), ⑤ **Model Router đa model** (§9). Các dự án trên đều **local-first desktop**; dự án này **web/server-side** → chỉ tham chiếu *logic*, không fork.
