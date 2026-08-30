# PLAN.md — Kế hoạch triển khai chi tiết (cho AI/dev khác code)

> Tài liệu này là bản phác thảo THI CÔNG — đã chốt mọi schema, prompt, API, test. **Làm theo đúng thứ tự phase, không suy diễn lại thiết kế.**
> Khi cần hiểu "vì sao" → đọc `solution.md` (design v3). Luật bất biến → `claude.md`.

---

## 0. Cách dùng tài liệu này

1. Đọc §1 (luật bất biến) và §4 (quyết định mở) trước tiên.
2. Làm tuần tự Phase 0 → 9. Mỗi phase có **Definition of Done** — chưa đạt thì không sang phase sau.
3. Mọi test chạy offline: **`LLM_FAKE=1`** + FakeLLM + sqlite — không cần API key, không cần Supabase/Cloud Run để phát triển.
4. Code trong `backend/` viết bằng Python 3.12 (FastAPI, SQLAlchemy async, Pydantic v2, ruff). FE viết bằng Next.js 15 + TypeScript + Tailwind.

---

## 1. Luật bất biến (vi phạm = sửa lại, không thương lượng)

| # | Luật | Cách kiểm |
|---|---|---|
| L1 | **Engine headless:** logic nghiệp vụ 100% trong `backend/app/engine/`, `backend/app/llm/`, `backend/app/integrations/`. Mọi thứ gọi được qua API không cần FE | test_headless |
| L2 | **FE mỏng tuyệt đối:** `frontend/` chỉ render + input + REST + subscribe Realtime. Server-side Next chỉ auth/session | grep FE không có từ khoá engine |
| L3 | **Engine hằng số, profile tham số:** thêm loại họp = thêm YAML trong `backend/profiles/` + template, 0 dòng engine sửa | `git diff backend/app/engine/` rỗng |
| L4 | **Model là config:** mọi LLM call qua `ModelRouter` với `task_id`; model/provider nằm ở `backend/config/model_policy.yaml` | không hardcode model trong code |
| L5 | **Không đụng tay khi họp:** HITL duy nhất = xác nhận `FLAG` (lật mơ hồ) + gán project fallback, cả hai sau họp | test_khong_dung_tay |
| L6 | **Revision-aware:** state là MỘT tài liệu sống, PATCH mỗi nhịp; item bị lật giữ `superseded`, KHÔNG xoá | test_revision |

---

## 2. Bối cảnh tóm tắt (đủ để code, chi tiết ở solution.md)

- **Bài toán:** BA/PO chủ trì họp; họp = chuỗi **nhịp** (nêu chủ đề → tranh luận → khép); nhịp sau **lật/trả lời/hiệu chỉnh** nhịp trước. Cần biến transcript → **trạng thái sống revision-aware** (Đã chốt / Còn treo / Việc / Bị lật) → đóng gói về repo dự án.
- **Đầu vào:** transcript đã có (STT ngoài phạm vi, giả định có sẵn), đẩy qua ingest.
- **4 nguyên thủy:** `DECISION` (chốt), `OPEN` (treo), `ACTION` (việc), `REVISION` (lật — **là quan hệ**, không phải node).
- **Người dùng:** BA/PO; dashboard "trạng thái sống" ưu tiên: Còn treo → Đã chốt → Action → Bất đồng → Ảnh hưởng contract.

### Đã chốt (v3)
| Trục | Chọn |
|---|---|
| FE | Next.js 15 (App Router) trên Firebase Hosting; server-side Next chỉ auth/session |
| API + Engine | FastAPI + Python 3.12 trên Cloud Run (Firebase không chạy được engine Python) |
| Brain | **Model Router đa model** — task → model qua `config/model_policy.yaml`; Claude mặc định cho core |
| DB/Auth/Realtime/Storage | Supabase (Postgres + Auth + Realtime + Storage + Queue) |
| Ingest queue | Cloud Tasks (fallback: Supabase Queue) — idempotent theo `chunk_id` |
| Tích hợp | Tầng Connector/MCP: calendar, repo, (sau) docs/Jira |
| Profile | YAML khai báo + Jinja2 template |

---

## 3. Quyết định MỞ — KHÔNG tự chốt (nêu giả định, hỏi khi chạm)

1. **Ngưỡng cắt nhịp** (`silence_gap_sec`, `closing_cues`) — là tham số profile; giá trị khởi đầu ở §8.4; calibrate bằng dữ liệu thật, KHÔNG sửa code.
2. **Tín hiệu "LẬT hợp lệ"** — đã thiết kế ở §8.1 (cam kết + mâu thuẫn cùng subject_key; mơ hồ → FLAG). Nếu thấy case lật nhầm trong test thật → hỏi trước khi sửa rule.
3. **Escalation `beat_router`** — bật/tắt bằng config; nếu sai nhiều → tắt, không xoá.
4. **Các mục ⚠️ cần verify phiên bản** (Firebase webframeworks cho Next SSR, Supabase Realtime rate limit, Supabase Queue GA, Storage S3 API, SSO plan) — flag khi tới phase liên quan, KHÔNG chặn code core.
5. **Privacy:** policy gửi tối thiểu ra ngoài (TLS, no-retention, redact bản sau). Không tự nới.

---

## 4. Môi trường & toolchain

### 4.1. Backend — `backend/pyproject.toml` (deps)
```
python = ">=3.12"
fastapi, uvicorn[standard], pydantic>=2, pydantic-settings
sqlalchemy[asyncio]>=2, asyncpg, aiosqlite, alembic
anthropic>=0.40, httpx, pyyaml, jinja2, tenacity
mcp>=1.0, GitPython, google-api-python-client (calendar), google-auth
ruff (dev), pytest, pytest-asyncio, respx (mock httpx)
```

### 4.2. `backend/.env.example`
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/meeting_ba
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<...>
SUPABASE_ANON_KEY=<...>
ANTHROPIC_API_KEY=<...>
GOOGLE_APPLICATION_CREDENTIALS=<path-service-account.json>
GITHUB_TOKEN=<...>
MODEL_POLICY_PATH=config/model_policy.yaml
CONNECTORS_PATH=config/connectors.yaml
LLM_FAKE=0                  # 1 = FakeLLM (dev/test offline)
LLM_REAL=anthropic          # provider thật khi LLM_FAKE=0
```
Test chạy bằng **aiosqlite** (không cần Postgres): `DATABASE_URL=sqlite+aiosqlite:///:memory:`. SQLAlchemy `JSON` hoạt động trên sqlite (TEXT). Không dùng feature chỉ Postgres có trong code core (JSONB cast nếu cần — tránh).

### 4.3. Lệnh
```bash
cd backend
uv sync && uv run ruff check . && uv run pytest tests/ -v
```

---

## 5. Repo layout + trách nhiệm từng file

```
BA_Assitant/
├── claude.md                       # luật bất biến (AI khác tự đọc)
├── plan.md                         # file này
├── solution.md                     # design v3
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── alembic/                    # migrations (phase 3)
│   ├── config/
│   │   ├── model_policy.yaml       # §10
│   │   └── connectors.yaml         # §11
│   ├── profiles/
│   │   ├── family-package.yaml     # profile mẫu #1 (§6)
│   │   ├── ux.yaml                 # profile #2 (test đa-dự-án)
│   │   └── generic.yaml            # fallback routing
│   ├── templates/
│   │   └── brd_family.md.j2        # template doc cuối
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory: routers, lifespan, CORS
│   │   ├── config.py               # pydantic-settings đọc .env
│   │   ├── api/
│   │   │   ├── deps.py             # auth (verify Supabase JWT), get repos/services
│   │   │   ├── projects.py         # POST /projects, GET/PUT /projects/{id}/profile
│   │   │   ├── meetings.py         # POST /meetings, GET state, assign, package, oplog
│   │   │   └── ingest.py           # POST /meetings/{id}/ingest
│   │   ├── engine/
│   │   │   ├── state.py            # Pydantic: StateItem, MeetingState, compact()
│   │   │   ├── operations.py       # Pydantic: 5 Operation + apply(state, ops)
│   │   │   ├── state_editor.py     # build messages → router.run(state_edit) → parse tool calls → apply
│   │   │   ├── segmenter.py        # heuristic + LLM confirm (§8.4)
│   │   │   ├── profile_loader.py   # YAML → Profile model + build_tools() (§7)
│   │   │   ├── profile_mapper.py   # StateItem → schema riêng + render template
│   │   │   ├── packager.py         # build files → repo connector (§9.3)
│   │   │   └── prompts.py          # prompt templates (§9)
│   │   ├── llm/
│   │   │   ├── router.py           # ModelRouter: run(task_id, ...) (§10)
│   │   │   ├── tasks.py            # TaskId enum: SEGMENT_CONFIRM, BEAT_ROUTER, STATE_EDIT, PROFILE_MAP, FINAL_DOC, REDACT
│   │   │   └── providers/
│   │   │       ├── base.py         # LLMProvider protocol + ToolCall/ToolResult models
│   │   │       ├── fake.py         # FakeLLM: script theo (task, key) (§15)
│   │   │       ├── anthropic.py    # Claude — tool-use, structured output
│   │   │       └── openai.py gemini.py selfhosted.py   # stubs raise NotImplementedError
│   │   ├── integrations/
│   │   │   ├── protocol.py         # Connector protocol + ToolSchema (§11)
│   │   │   ├── registry.py         # load connectors.yaml → dict[id, Connector]
│   │   │   ├── mcp_client.py       # MCP adapter (httpx, SSE transport) — dùng mcp SDK
│   │   │   └── adapters/
│   │   │       ├── calendar_google.py   # resolve_event(event_id) → {title, tags, project_slug|null}
│   │   │       ├── calendar_outlook.py  # stub — NotImplementedError
│   │   │       └── repo_git.py          # commit_files(repo, branch, files, msg) → {sha, pr_url}
│   │   ├── db/
│   │   │   ├── engine.py           # async engine/session (env DATABASE_URL)
│   │   │   ├── models.py           # SQLAlchemy — §5.1 DDL
│   │   │   └── repos.py            # MeetingRepo, ProjectRepo, StateRepo, LLMCallRepo — §5.2
│   │   ├── realtime/
│   │   │   └── publisher.py        # StatePublisher protocol + NoopPublisher (Supabase Realtime = tự động qua UPDATE snapshot, không cần code push)
│   │   └── services/
│   │       └── meeting_service.py  # orchestrator: process_chunk → segment → edit → publish (§8)
│   └── tests/
│       ├── conftest.py             # FakeLLM fixture, sqlite session, app fixture
│       ├── test_operations.py      # apply: create/supersede/answer/amend/flag/none
│       ├── test_state_editor.py    # script ops → đúng lời gọi router → đúng state
│       ├── test_revision.py        # ★ acceptance §15
│       ├── test_multi_project.py   # ★ thêm profile mới, engine diff rỗng
│       ├── test_model_router.py    # §10: mapping/fallback/escalation/audit
│       ├── test_segmenter.py       # heuristics + confirm
│       ├── test_connector_swap.py  # calendar direct→mcp, engine không đổi
│       ├── test_api_headless.py    # ★ ingest→state→package qua API, không FE
│       └── test_packager.py        # file ra đúng template + convention
└── frontend/                       # Phase 8 — Next.js 15 (chi tiết §13)
```

---

## 6. Schema dữ liệu (CHÍNH XÁC — dùng để viết DDL + Pydantic)

### 6.1. Bảng (SQLAlchemy models — map 1:1)

```sql
projects (
  id UUID PK DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  profile_yaml TEXT NOT NULL,          -- nội dung profile (source of truth)
  repo_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
)

meetings (
  id UUID PK DEFAULT gen_random_uuid(),
  project_id UUID NULL REFERENCES projects(id),
  status TEXT NOT NULL DEFAULT 'live',  -- live | unassigned | ended | packaged
  calendar_event_id TEXT,
  calendar_source TEXT,                 -- google | outlook
  profile_key TEXT NOT NULL DEFAULT 'generic',  -- key profile đang dùng
  started_at TIMESTAMPTZ DEFAULT now(),
  ended_at TIMESTAMPTZ NULL
)

beats (                                   -- một nhịp = 1 dòng
  meeting_id UUID REFERENCES meetings(id),
  nhip_id INT NOT NULL,                   -- đánh số tăng dần per meeting (bắt đầu 1)
  status TEXT NOT NULL DEFAULT 'open',    -- open | closed
  transcript TEXT NOT NULL DEFAULT '',    -- nối các chunk
  started_at TIMESTAMPTZ, closed_at TIMESTAMPTZ,
  PRIMARY KEY (meeting_id, nhip_id)
)

ingest_chunks (
  meeting_id UUID REFERENCES meetings(id),
  chunk_id TEXT NOT NULL,                 -- idempotency key
  seq INT NOT NULL,                       -- thứ tự từ thiết bị
  speaker TEXT,
  text TEXT NOT NULL,
  ts_start REAL, ts_end REAL,
  created_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (meeting_id, chunk_id)      -- dedup cứng
)

state_items (
  id UUID PK,
  meeting_id UUID NOT NULL REFERENCES meetings(id),
  type TEXT NOT NULL,                     -- DECISION | OPEN | ACTION
  status TEXT NOT NULL DEFAULT 'active',  -- active | superseded | answered | flagged
  subject_key TEXT NOT NULL,
  core JSONB NOT NULL,                    -- {title, body, rationale}
  profile_fields JSONB NOT NULL DEFAULT '{}',
  provenance JSONB NOT NULL,              -- {nhip_id, span:[i,j], quote}
  supersedes UUID NULL,                   -- cạnh LẬT: item mới → item cũ
  superseded_by UUID NULL,
  answered_by UUID NULL,
  created_nhip INT NOT NULL,
  updated_nhip INT NOT NULL
)
CREATE INDEX ix_state_items_meeting ON state_items(meeting_id);
CREATE INDEX ix_state_items_subject  ON state_items(meeting_id, subject_key);

meeting_state_snapshot (                  -- 1 dòng per meeting, UPDATE mỗi nhịp → Realtime fire
  meeting_id UUID PK REFERENCES meetings(id),
  version INT NOT NULL DEFAULT 0,         -- tăng mỗi lần state đổi
  snapshot JSONB NOT NULL,                -- = output của compact() (§6.3)
  updated_at TIMESTAMPTZ DEFAULT now()
)

op_log (
  id BIGSERIAL PK,
  meeting_id UUID NOT NULL REFERENCES meetings(id),
  nhip_id INT NOT NULL,
  op_type TEXT NOT NULL,                  -- create | supersede | answer | amend | flag
  payload JSONB NOT NULL,
  applied_at TIMESTAMPTZ DEFAULT now()
)

llm_calls (
  id BIGSERIAL PK,
  meeting_id UUID NULL,
  task TEXT NOT NULL,                     -- segment_confirm | beat_router | state_edit | ...
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INT, output_tokens INT,
  latency_ms INT, cost_est NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
)
```

### 6.2. Pydantic models (app/engine/state.py)

```python
class StateItem(BaseModel):
    id: UUID
    type: Literal["DECISION", "OPEN", "ACTION"]
    status: Literal["active", "superseded", "answered", "flagged"] = "active"
    subject_key: str
    core: dict            # {"title": str, "body": str, "rationale": str}
    profile_fields: dict = {}
    provenance: dict      # {"nhip_id": int, "span": [int, int], "quote": str}
    supersedes: UUID | None = None
    superseded_by: UUID | None = None
    answered_by: UUID | None = None
    created_nhip: int
    updated_nhip: int

class MeetingState(BaseModel):
    meeting_id: UUID
    items: list[StateItem]
    version: int

    def compact(self, current_nhip: int) -> dict:
        # items active → đủ field; items phi-active → chỉ giữ nếu updated_nhip >= current_nhip - 5
        # output chính là payload gửi cho LLM (§9.2) và snapshot (§6.3)
```

### 6.3. Snapshot JSON (lưu bảng + trả về API `GET /state`)

```json
{
  "meeting_id": "…",
  "version": 7,
  "nhip_id": 7,
  "items": [
    {"id":"…","type":"DECISION","status":"active","subject_key":"payment-flow",
     "core":{"title":"Dùng phương án B cho luồng thanh toán","body":"","rationale":"A không kịp deadline"},
     "profile_fields":{"replaces_decision":"…D1","impacts":"contract"},
     "provenance":{"nhip_id":3,"span":[0,3],"quote":"thôi đổi sang phương án B đi…"},
     "supersedes":"…D1","superseded_by":null,"answered_by":null,
     "created_nhip":3,"updated_nhip":3}
  ],
  "summary": {
    "open_count": 0,
    "decision_count": 2,
    "action_unassigned": ["…id"]   // ACTION thiếu owner → cờ đỏ FE
  }
}
```

---

## 7. Hợp đồng Engine ↔ Profile (chốt chính xác)

### 7.1. `backend/profiles/family-package.yaml` (nội dung file thật)

```yaml
project: family-package
display_name: "Family Package — requirement/design"

vocabulary:
  aliases:      { "gói GĐ": "family package", "tier": "gói dịch vụ" }
  participants: ["BA-Ha", "BE-Nam", "FE-Linh", "Ecom-Tuan"]

routing:
  connector:        calendar-google
  calendar_tags:    ["FamilyPkg", "#fp"]
  repo:             "git@git.company:be/family-pkg.git"
  file_convention:  "meetings/{date}-{slug}.md"

item_schemas:
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
  template: "templates/brd_family.md.j2"

segmenter:
  silence_gap_sec: 8
  closing_cues: ["ok chốt", "chốt vậy", "quyết định vậy", "vậy quyết", "chuyển sang", "sang phần", "tiếp theo"]
  max_beat_words: 400
  max_beat_sec: 180
```

### 7.2. `ux.yaml` (profile #2 — dùng cho test đa-dự-án): field khác hẳn
```yaml
project: ux-redesign
display_name: "UX Redesign"
vocabulary: { aliases: {}, participants: ["BA-Ha", "UX-Mai"] }
routing: { connector: calendar-google, calendar_tags: ["UX"], repo: "git@git.company:fe/ux.git", file_convention: "meetings/{date}-{slug}.md" }
item_schemas:
  DECISION:
    fields:
      - { name: affects_flow, type: text }
      - { name: edge_cases,   type: text }
  ACTION:
    fields: [ { name: owner, type: person }, { name: due, type: date } ]
final_doc: { enabled: false }
segmenter: { silence_gap_sec: 6, closing_cues: ["ok", "chốt", "xong", "next"] }
```

### 7.3. `generic.yaml`: `item_schemas: {}` (không field riêng), `final_doc: {enabled: false}`, `routing: {connector: calendar-google, calendar_tags: []}`.

### 7.4. `profile_loader.build_tools(profile) → list[ToolSchema]` — 5 TOOLS cố định (tên không đổi; chỉ schema `profile_fields` đổi)

| Tool | Params (bắt buộc trước) | Dùng khi |
|---|---|---|
| `create_item` | `item_type`, `subject_key`, `core{title,body,rationale}`, `profile_fields`(schema theo item_type), `evidence{quote,span}` | phát biểu cam kết |
| `supersede_item` | `old_item_id`, `new_item{subject_key,core,profile_fields(DECISION),evidence}`, `reason` | lật quyết định |
| `answer_open` | `open_item_id`, `answer_text`? hoặc `answer_decision{subject_key,core,profile_fields(DECISION),evidence}`?, `evidence` | trả lời TREO |
| `amend_item` | `item_id`, `field_changes` (dict field→value mới), `reason`, `evidence` | hiệu chỉnh item có sẵn |
| `flag_item` | `target_item_id`?, `new_item`?, `reason` | lật mơ hồ — cần xác nhận |

**Mapping type profile field → JSON Schema:**
`ref`→`{"type":"string","description":"item id"}`, `enum`→`{"type":"string","enum":[…]}`,
`person`→`{"type":"string"}`, `date`→`{"type":"string","description":"YYYY-MM-DD"}`, `text`→`{"type":"string"}`.

`profile_fields` schema của tool `create_item` = object với properties từ `item_schemas[item_type].fields` (rỗng nếu type không có khai báo). `supersede_item.new_item.profile_fields` và `answer_open.answer_decision.profile_fields` **luôn dùng schema DECISION**.

**Parser:** state_editor gộp TẤT CẢ tool calls trong một response → list operations, **giữ thứ tự tool call**.

---

## 8. Pipeline xử lý (chính xác)

### 8.1. Luồng `POST /meetings/{id}/ingest`
```
1. verify JWT (Supabase) + meeting thuộc scope người gọi
2. INSERT ingest_chunks ON CONFLICT (meeting_id, chunk_id) DO NOTHING
   → nếu conflict: return {"accepted": false, "deduped": true} (200)
3. append text vào beats dòng hiện tại (open); nếu chưa có → tạo nhip_id = max+1
4. signals = segmenter.heuristics(chunk)          # §8.4
   - boundary_certain (cue + silence): đóng nhịp NGAY
   - boundary_weak (silence | buffer full | speaker change): gọi router.run(SEGMENT_CONFIRM)
   - không có tín hiệu: return
5. nếu đóng nhịp: UPDATE beats SET status='closed' → process_beat(meeting_id, nhip_id)
   (v1: chạy await trực tiếp; nếu beat > 20s thì chuyển background task — ghi TODO)
```

### 8.2. `process_beat(meeting_id, nhip_id)` — trái tim
```
1. LOCK: per-meeting asyncio.Lock (dict trong memory) + SELECT meetings FOR UPDATE
2. state = StateRepo.get_compact_state(meeting_id, nhip_id)     # items active + gần đây
3. hints = None
   nếu policy có beat_router: hints = await router.run(BEAT_ROUTER, transcript)
4. tools = profile_loader.build_tools(profile) + connector tools (calendar §11)
5. ops = await router.run(STATE_EDIT, state=state, beat=transcript, profile=profile, tools=tools, hints=hints)
6. apply:
   new_items = operations.apply(state, ops)                     # thuần Python, §8.3
   TX: INSERT/UPDATE state_items + INSERT op_log rows + UPDATE meeting_state_snapshot (version+1)
7. Supabase Realtime tự fire khi snapshot UPDATE (không cần code push; publisher = Noop cho dev)
```

### 8.3. `operations.apply(state, ops)` — quy tắc (unit-test ở đây)
- `create` → item mới status=active, `provenance.nhip_id = nhip_id hiện tại`.
- `supersede(old_id, new_item)` → **validate**: (a) old tồn tại, type=DECISION, status=active, (b) `subject_key` khớp hoặc old_id được model chỉ định rõ ràng từ danh sách state đã đưa; nếu invalid → log warning, bỏ op (không crash pipeline). Valid → new_item.status=active, new_item.supersedes=old_id; old.status=superseded, old.superseded_by=new_item.id.
- `answer(open_id, …)` → open.status=answered, open.answered_by=(decision mới).id nếu có answer_decision, ngược lại lưu answer_text vào open.core.body (nếu trống) + `core.answer_text`. Nếu có answer_decision → tạo DECISION mới active.
- `amend(item_id, field_changes)` → merge vào core/profile_fields (chỉ field tồn tại; field lạ → bỏ + warning); updated_nhip = hiện tại.
- `flag` → nếu target_item_id: item đó status=flagged; nếu có new_item: tạo item mới status=flagged. Flag KHÔNG đổi state các item khác.
- `none`/rỗng → không gì (version KHÔNG tăng, snapshot KHÔNG update → FE không nhận push).

### 8.4. Segmenter heuristics (không LLM)
```python
def heuristics(chunk, beat) -> Literal["certain", "weak", None]:
    gap = chunk.ts_start - last_ts_in_beat if beat has content else 0
    text = beat.transcript + chunk.text
    if gap >= profile.segmenter.silence_gap_sec and any(cue in text.lower() for cue in closing_cues):
        return "certain"
    if gap >= silence_gap_sec or words(text) >= max_beat_words or (now - beat.started_at) >= max_beat_sec:
        return "weak"
    if chunk.speaker != last_speaker and any(cue in text for cue in closing_cues):
        return "weak"
    return None
```
`SEGMENT_CONFIRM` prompt (§9.4) trả `{"closed": bool, "has_content": bool}`; closed=True → đóng nhịp (kể cả has_content=False → process_beat xử lý rỗng).

### 8.5. Định tuyến dự án (§7 solution)
- `POST /meetings` với `calendar_event_id` → gọi connector calendar `resolve_event` → match `calendar_tags` (regex trên title+description) → project_id. Không khớp → status=unassigned, profile=generic.
- `POST /meetings/{id}/assign {project_id}` → set project + profile_key, re-map state (chạy lại `profile_map` cho các item hiện có — v1: chỉ đổi profile_key, không map lại lịch sử; ghi TODO).

---

## 9. Prompts (CHÍNH XÁC — dùng nguyên văn, thay placeholder)

### 9.1. SYSTEM — STATE_EDIT (task `state_edit`)
```
You maintain the live decision state of a business-analysis meeting held in Vietnamese (quotes may be Vietnamese).
State items are: DECISION (a decision that was committed), OPEN (an open question not yet answered), ACTION (a task for someone, optionally with owner/due).
A later beat can REVISE earlier items. Revision is expressed ONLY through operations (supersede/answer/amend) — you never edit history text.

RULES:
1. Create items only for COMMITTED statements (cues: "chốt", "ok vậy", "quyết định", "thống nhất", "vậy làm"). Do NOT create items for options being considered or speculation.
2. supersede_item ONLY when BOTH: (a) the new option is committed, AND (b) it directly contradicts an active DECISION with the same subject_key. If only discussing options, create an OPEN or do nothing — never supersede.
3. answer_open ONLY when the beat gives a committed answer. If the answer is a decision, pass answer_decision; otherwise pass answer_text.
4. amend_item to update fields of an existing item when the beat clarifies or changes its content WITHOUT contradicting it.
5. When unsure whether a contradiction is a real flip or just discussion, use flag_item (do NOT supersede). The host will confirm after the meeting.
6. subject_key: a short stable English slug identifying the topic (e.g. "payment-flow", "rate-limit"). Reuse the existing item's subject_key when revising it.
7. Every operation MUST include evidence.quote (verbatim snippet from the beat, original language) and evidence.span (start,end indexes of that quote in the beat transcript).
8. If the beat contains nothing actionable, call NO tool (empty response).
9. Use the participant names in the profile for ACTION.owner when identifiable.
```

### 9.2. USER — STATE_EDIT (template, điền placeholder)
```
CURRENT_STATE (after beat {prev_nhip}):
{state_json}          # output compact() — chỉ items active + superseded/answered 5 nhịp gần nhất

NEW_BEAT ({nhip_id}) — transcript:
{speaker}: {text}
...

PROFILE CONTEXT:
- project: {display_name}
- participants: {participants}
- vocabulary aliases: {aliases}
- DECISION fields: {item_schemas.DECISION.fields}
- ACTION fields: {item_schemas.ACTION.fields}

Return operations for THIS beat only, via the provided tools. Call tools in chronological order.
```

### 9.3. USER — BEAT_ROUTER (task `beat_router`, escalation)
```
Beat transcript:
...
Classify this beat: does it contain a committed flip of an earlier decision, an answer to an open question, or unresolved disagreement?
Return JSON: {"complexity": "simple" | "complex", "has_revision_cue": bool, "has_answer_cue": bool, "has_disagreement": bool}
```

### 9.4. USER — SEGMENT_CONFIRM (task `segment_confirm`)
```
Beat so far (unclosed):
...
Given this transcript plus the fact a boundary signal fired (silence/speaker change/buffer full),
decide: has the discussion reached a natural closing point for a beat?
Return JSON: {"closed": bool, "reason": "silence" | "topic_shift" | "closing_cue" | "buffer_full" | null}
```

### 9.5. USER — FINAL_DOC (task `final_doc`) — không bắt buộc ở v1; template Jinja2 render là chính:
`profile_mapper` render template với context: `{state, summary, project, date}`. Template mẫu `templates/brd_family.md.j2`:
```jinja2
# {{ project.display_name }} — Meeting {{ date }}
## Decisions
{% for it in state.items if it.type == 'DECISION' and it.status == 'active' %}
- **{{ it.core.title }}** — rationale: {{ it.core.rationale }} {% if it.profile_fields.impacts %}(impacts: {{ it.profile_fields.impacts }}){% endif %}
{% endfor %}
## Open questions
{% for it in state.items if it.type == 'OPEN' and it.status == 'active' %}
- {{ it.core.title }}
{% endfor %}
## Actions
{% for it in state.items if it.type == 'ACTION' and it.status == 'active' %}
- [ ] {{ it.core.title }} — owner: {{ it.profile_fields.get('owner', 'CHƯA GÁN') }} — due: {{ it.profile_fields.get('due', '—') }}
{% endfor %}
```

---

## 10. Model Router (chốt chính xác)

### 10.1. `backend/config/model_policy.yaml` (nội dung file thật — dùng model IDs này)
```yaml
defaults: { provider: anthropic, model: claude-sonnet-5 }

tasks:
  segment_confirm:
    model: claude-haiku-4-5-20251001
    budget: { max_latency_ms: 3000 }
  beat_router:
    model: claude-haiku-4-5-20251001
  state_edit:
    model: claude-opus-5
    escalate:
      - if: has_revision_cue
        model: claude-opus-5
      - if: has_disagreement
        model: claude-opus-5
    fallback: [ { provider: anthropic, model: claude-sonnet-5 } ]
  profile_map: { model: claude-sonnet-5 }
  final_doc:   { model: claude-sonnet-5 }
  redact:      { model: claude-haiku-4-5-20251001 }

providers:
  anthropic:  { kind: cloud, secret: ANTHROPIC_API_KEY }
  openai:     { kind: cloud, secret: OPENAI_API_KEY, disabled: true }
  gemini:     { kind: cloud, secret: GEMINI_API_KEY, disabled: true }
  selfhosted: { kind: selfhost, base_url: "http://localhost:8000/v1", disabled: true }
```

### 10.2. Interface
```python
# app/llm/providers/base.py
class LLMProvider(Protocol):
    provider_id: str
    async def complete(self, *, model: str, system: str, user: str,
                       tools: list[dict]) -> list[ToolCall]   # tool calls theo thứ tự
    # ToolCall = {name: str, args: dict}
    # provider phải trả thêm usage {in, out, latency_ms} — trả qua object riêng:
    #   async def complete(...) -> LLMResult{tool_calls, usage}

# app/llm/router.py
class ModelRouter:
    def __init__(self, policy, providers: dict[str, LLMProvider], audit: LLMCallRepo): ...
    async def run(self, task: TaskId, *, system: str, user: str,
                  tools: list[dict], hints: dict | None = None,
                  meeting_id: UUID | None = None) -> list[ToolCall]
```
Logic `run()`: (1) tra task trong policy (không có → defaults); (2) áp `escalate` rules theo `hints`; (3) gọi provider chính, `tenacity` retry 1 lần cho lỗi 429/5xx; lỗi vĩnh viễn → `fallback` chain; (4) ghi `llm_calls` (task, provider, model, tokens, latency_ms, cost_est=0 v1); (5) provider không có trong dict hoặc disabled → raise rõ ràng.

### 10.3. `providers/anthropic.py`
- Dùng SDK `anthropic` (AsyncAnthropic). `tools=[...]`, `tool_choice={"type":"any"}` cho STATE_EDIT (bắt buộc gọi tool khi có nội dung — chấp nhận lỗi rỗng), để tự do cho SEGMENT_CONFIRM/BEAT_ROUTER (text output → parse JSON).
- Map kết quả tool_use → `ToolCall`. Ghi usage từ `message.usage`.
- **Không log payload** (messages chứa transcript nhạy cảm) — chỉ log metadata.

### 10.4. `providers/fake.py` — FakeLLM (test/dev offline)
```python
class FakeLLM(LLMProvider):
    provider_id = "fake"
    def __init__(self): self.script: dict[str, list[list[ToolCall]]] = {}  # task -> [lượt -> tool calls]
    def enqueue(self, task: str, calls: list[ToolCall]): ...               # FIFO theo task
    async def complete(...): pop và trả; hết script → trả []
    # hỗ trợ: script theo key "state_edit:<subject_key contains>", và mode "echo_schema":
    #   với flag echo_schema=True, tự sinh tool call create_item với profile_fields đúng schema
```
`LLM_FAKE=1` → router dùng FakeLLM cho mọi task. Test `test_multi_project` dùng `echo_schema` để chứng minh schema động theo profile.

---

## 11. Tầng Connector/MCP (chốt chính xác)

### 11.1. Protocol
```python
# app/integrations/protocol.py
class ToolSchema(TypedDict):        # tương thích Anthropic tool format
    name: str; description: str
    input_schema: dict

class Connector(Protocol):
    connector_id: str
    def tools(self) -> list[ToolSchema]: ...
    async def call(self, name: str, args: dict) -> dict   # timeout 15s, audit, raise ConnectorError
```

### 11.2. `backend/config/connectors.yaml` (nội dung file thật)
```yaml
connectors:
  - id: calendar-google
    transport: direct
    config: { calendar_ids: ["primary"] }
  - id: repo-github
    transport: direct
    config: { clone_dir: "/tmp/ba_repos" }
  - id: docs-notion            # chưa bật — minh hoạ MCP
    transport: mcp
    enabled: false
    config: { url: "https://mcp.example.com/notion", transport: sse }
```

### 11.3. `calendar_google.py` (direct)
- Dùng google-api-python-client + service account (`GOOGLE_APPLICATION_CREDENTIALS`).
- `resolve_event(event_id) → {title, description, tags: [str]}`: đọc event, tags = title+description.
- `match_project(tags, profiles) → project_slug | None`: với mỗi profile, nếu bất kỳ `routing.calendar_tags` xuất hiện (substring, case-insensitive) trong tags → khớp. Nhiều khớp → theo thứ tự profile load; không khớp → None.
- Tool export cho LLM (để model tự gọi khi cần): `calendar.resolve_event(event_id)`.

### 11.4. `repo_git.py` (direct)
```python
async def commit_files(self, repo_url: str, branch: str, files: dict[str, str],
                       message: str, token: str | None) -> {"sha": str, "pr_url": str | None}
```
- GitPython: clone nông (depth 1) vào `clone_dir`, tạo nhánh `meetings/{date}-{meeting_id[:8]}`, ghi files, commit, push; nếu có token → tạo PR qua `gh` CLI (subprocess) hoặc GitHub REST (httpx). Test dùng `FakeRepoConnector` (ghi dict, không git thật).

### 11.5. `mcp_client.py` (MCP adapter)
- Dùng Python SDK `mcp`: `streamablehttp_client` (ưu tiên) / `sse_client`. `tools()` = list tools từ server (đổi sang ToolSchema); `call()` gọi tool MCP.
- V1 chỉ cần **chạy được với mock MCP server trong test** (`test_connector_swap`: một MCP server giả trong-process trả `resolve_event` y hệt direct) — không cần MCP thật tới phase 6.
- Timeout + retry idempotent + audit (ghi vào op_log dạng `connector_call`).

### 11.6. Registry
`registry.load(connectors_yaml) → dict[id, Connector]`; connector `enabled: false` → skip. Engine nhận registry qua DI; `meeting_service` dùng `connectors["calendar-google"]` cho routing, `connectors["repo-github"]` cho packaging. **Không hardcode id trong engine** — id đọc từ profile.routing.connector / config mặc định.

---

## 12. API contracts (CHÍNH XÁC)

Auth: mọi endpoint yêu cầu `Authorization: Bearer <supabase_jwt>`; verify bằng supabase client (service role) hoặc JWKS cache. RBAC v1: user phải thuộc project (claim/`project_members` bảng — tạo bảng `project_members(project_id, user_id)`; người tạo project = owner).

| Method & Path | Request | Response |
|---|---|---|
| `POST /projects` | `{slug, name, profile_yaml, repo_url?}` | `201 {id, slug, name}` |
| `GET /projects/{id}/profile` | — | `200 {profile_yaml}` |
| `PUT /projects/{id}/profile` | `{profile_yaml}` (validate bằng profile_loader) | `200 {ok: true}` |
| `POST /meetings` | `{calendar_event_id?, calendar_source?, project_id?}` | `201 {id, project_id, status, profile_key}` — có calendar_event_id thì auto-route (§8.5) |
| `POST /meetings/{id}/ingest` | `{chunk_id, seq, text, speaker?, ts_start?, ts_end?}` | `200 {accepted, deduped}`; 404 nếu meeting không tồn tại; 403 nếu không thuộc project |
| `GET /meetings/{id}/state` | — | `200` snapshot §6.3 |
| `GET /meetings/{id}/oplog?after=<id>` | — | `200 {ops: [{id, nhip_id, op_type, payload, applied_at}]}` |
| `POST /meetings/{id}/assign` | `{project_id}` | `200 {id, project_id, profile_key}` |
| `POST /meetings/{id}/package` | — | `200 {repo, branch, files: [paths], commit_sha, pr_url?}`; 409 nếu meeting chưa `ended` hoặc chưa có project |
| `POST /meetings/{id}/end` | — | `200` — đóng nhịp cuối + status=ended (gọi khi buổi họp kết thúc) |

Lỗi chuẩn: `{"detail": "..."}` (FastAPI). Ingest phải **luôn 200** cho chunk trùng (idempotent).

Realtime (FE): subscribe supabase-js `postgres_changes` bảng `meeting_state_snapshot` filter `meeting_id=eq.<id>` → nhận UPDATE → re-fetch `GET /state`. Dev không có Supabase: FE poll `GET /state` 15s (flag env `NEXT_PUBLIC_POLL_MODE=1`).

---

## 13. FE Next.js (Phase 8 — chi tiết)

```
frontend/
├── app/
│   ├── layout.tsx, page.tsx              # redirect → /meetings hoặc /login
│   ├── login/page.tsx                    # Supabase Auth (email OTP)
│   ├── meetings/page.tsx                 # danh sách họp (server component OK — chỉ đọc)
│   └── meetings/[id]/page.tsx            # ★ dashboard — client component
│       ├── panels/open-questions.tsx     # TREO + FLAG (nổi bật nhất)
│       ├── panels/decisions.tsx          # CHỐT + "thay cho…" + rationale
│       ├── panels/actions.tsx            # VIỆC; owner rỗng → đỏ
│       ├── panels/conflicts.tsx          # bất đồng (từ core.body disagreement)
│       └── assign-project.tsx            # chip gán project khi unassigned
├── lib/supabase.ts                       # @supabase/ssr (server: session) + browser client
├── lib/api.ts                            # fetch wrapper mỏng: getState, assign, end
├── middleware.ts                         # bảo vệ route (session)
├── firebase.json                         # hosting + rewrite /api → Cloud Run URL
├── Dockerfile                            # không cần nếu Firebase webframeworks; dự phòng static export
└── next.config.ts
```
- **Chỉ `lib/api.ts` + panels được gọi REST/Realtime.** Server components tối đa: đọc session, redirect. Không import gì từ `backend/`.
- Tailwind cho style; gọi skill `design-taste-frontend` khi vào phase này.
- Bảng kiểm "FE mỏng" (DoD phase 8): `grep -rE "segment|state_edit|supersede|profile_fields" frontend/app` → chỉ ra chuỗi trong dữ liệu render (OK), không có logic xử lý (không import/function tính state).

---

## 14. PHASES — thứ tự bắt buộc + Definition of Done

### Phase 0 — Scaffold backend (0.5 ngày)
- pyproject, .env.example, config.py, `pytest` + conftest trống, ruff config, alembic init.
- **DoD:** `uv run pytest` xanh với 1 smoke test (`test_config.py` đọc .env.example mẫu).

### Phase 1 — Engine core (2–3 ngày) ★ quan trọng nhất
- `state.py`, `operations.py` (apply + validate), `profile_loader.py` (parse YAML + build_tools), `state_editor.py` (không phụ thuộc DB: nhận state + beat + tools + router → trả ops), `prompts.py`.
- 3 profiles + template Jinja2.
- Tests: `test_operations`, `test_state_editor`, `test_revision` (FakeLLM script đúng ops), `test_multi_project` (echo_schema).
- **DoD:** test_revision xanh (kịch bản §15) — **đây là thước đo toàn dự án**; test_multi_project xanh và `git diff app/engine/` không có gì để diff (engine vốn không đổi — test chạy 2 profile cùng code).

### Phase 2 — Model Router (1 ngày)
- `llm/` đầy đủ + policy + FakeLLM + Anthropic provider + `llm_calls` audit (in-memory trước, DB sau phase 3).
- Tests: `test_model_router` — (a) task→model đúng policy; (b) provider lỗi → fallback; (c) hints escalation; (d) audit ghi đủ field.
- **DoD:** 4 tests xanh; smoke thật tuỳ chọn: `LLM_FAKE=0 ANTHROPIC_API_KEY=...` gọi 1 request.

### Phase 3 — DB + Repos (1–2 ngày)
- `db/models.py` theo §6.1, alembic migration đầu, `db/repos.py` (MeetingRepo, ProjectRepo, StateRepo, LLMCallRepo) — async, testable với sqlite.
- **DoD:** migration áp lên Postgres sạch thành công; test repo CRUD + `apply_operations` transaction (rollback khi lỗi giữa chừng).

### Phase 4 — API + pipeline service (2 ngày)
- `services/meeting_service.py` (process_chunk, process_beat, per-meeting lock), API routers theo §12, auth deps (Supabase JWT; test mode: bypass bằng env `AUTH_DISABLED=1`).
- Tests: `test_api_headless` — dựng app + FakeLLM + sqlite: tạo project → meeting → ingest 4 chunk → state ra đúng §15 → `POST /end` → `POST /package` (FakeRepoConnector) → file đúng.
- **DoD:** test_api_headless xanh, không có FE nào tham gia.

### Phase 5 — Segmenter (1 ngày)
- `segmenter.py` theo §8.4 + SEGMENT_CONFIRM qua router; beats logic trong service.
- Tests: `test_segmenter` — (a) cue+silence → đóng không cần LLM; (b) silence thuần → gọi confirm, closed=True → đóng; (c) closed=False → không đóng; (d) buffer full → weak.
- **DoD:** 4 tests xanh; `test_api_headless` vẫn xanh (chunks giờ đi qua segmenter — cập nhật fixture thêm ts).

### Phase 6 — Connectors + routing (1–2 ngày)
- protocol, registry, calendar_google (direct, có fake cho test), repo_git (direct + fake), mcp_client + mock MCP server trong test.
- Routing trong `POST /meetings` (§8.5) + `assign`.
- Tests: `test_connector_swap` — cùng kịch bản chạy với `calendar-google` transport=direct và transport=mcp (mock server trả y hệt) → kết quả route giống nhau; `git diff app/engine/` rỗng.
- **DoD:** test_connector_swap xanh.

### Phase 7 — Packager (0.5–1 ngày)
- `profile_mapper.py` + `packager.py` theo §9.5 + convention `meetings/{date}-{slug}.md` (slug từ project.slug; `{date}` = YYYY-MM-DD).
- Luôn kèm file `meeting-state.json` (snapshot §6.3) cùng commit.
- **DoD:** `test_packager` xanh (nội dung file khớp template render với state cho trước); test_api_headless vẫn xanh.

### Phase 8 — FE Next.js (3–4 ngày)
- Theo §13. Auth trước, dashboard sau. **Gọi skill `design-taste-frontend` trước khi code UI.**
- Deploy config: firebase.json rewrite `/api` → Cloud Run; nếu Firebase webframeworks ⚠️lỗi → fallback `output: 'export'` + static hosting.
- **DoD:** login + dashboard hiển thị state từ API thật; Realtime (hoặc poll dev); grep FE không có logic engine; `npm run build` sạch.

### Phase 9 — E2E + calibration (1–2 ngày)
- Script e2e: Supabase thật + Claude thật (`LLM_FAKE=0`), transcript mẫu §15 qua ingest từng chunk → so sánh state với expectation. Nếu sai: chỉnh PROMPT/config, **không sửa rule apply**.
- **DoD:** bảng acceptance §15 điền đủ PASS; các mục ⚠️ §3.4 verify xong (ghi kết quả vào solution.md).

---

## 15. ACCEPTANCE — kịch bản chính xác + assertion

### 15.1. `test_revision` (FakeLLM script — deterministic, KHÔNG dùng Claude thật)

Transcript mẫu (4 nhịp, tiếng Việt, chunk theo nhịp):

```
NHIP 1:  "BE-Nam: phần thanh toán thì em thấy phương án A ổn." /
         "BA-Ha: ok vậy chốt phương án A cho luồng thanh toán nhé."
NHIP 2:  "BA-Ha: còn rate limit thì mình tính thế nào nhỉ?" /
         "Ecom-Tuan: chưa rõ, phụ thuộc hạ tầng." /
         "BA-Ha: vậy để mở, mai hỏi thêm bên platform."
NHIP 3:  "BE-Nam: thôi đổi sang phương án B đi, A không kịp deadline tuần sau." /
         "BA-Ha: ok, vậy chốt B, bỏ A."
NHIP 4:  "BA-Ha: rate limit chốt 100 req/s nhé." / "Ecom-Tuan: ok."
```

**Script FakeLLM (ops đúng kỳ vọng của engine — test này kiểm chứng apply, không kiểm chứng model):**
1. `create_item(DECISION, subject_key="payment-flow", title="Dùng phương án A cho luồng thanh toán", evidence quote="ok vậy chốt phương án A cho luồng thanh toán nhé.")` → id D1
2. `create_item(OPEN, subject_key="rate-limit", title="Rate limit tính thế nào?")` → id O1
3. `supersede_item(old=D1, new DECISION subject_key="payment-flow", title="Dùng phương án B cho luồng thanh toán", rationale="A không kịp deadline", profile_fields={replaces_decision:D1, impacts:"contract"})` → D2
4. `answer_open(open=O1, answer_decision=DECISION subject_key="rate-limit", title="Rate limit = 100 req/s")` → D3

**Assertions (cuối):**
- `state.items` có D1.status == `"superseded"` và D1.superseded_by == D2.id
- D2.status == `"active"`, D2.supersedes == D1.id
- O1.status == `"answered"`, O1.answered_by == D3.id
- **Không** tồn tại 2 DECISION active cùng subject_key "payment-flow" (chống mâu thuẫn song song)
- `summary.open_count == 0` (O1 rời panel treo)
- `op_log` có đúng 4 dòng theo thứ tự create/create/supersede/answer
- `snapshot.version == 4`

### 15.2. `test_multi_project` (profile-driven)
- Chạy đúng pipeline trên với profile `ux.yaml` (FakeLLM echo_schema) → DECISION có `profile_fields` với khoá `affects_flow`/`edge_cases` (không có `impacts`).
- Assert: cùng code `state_editor/profile_loader` sinh schema khác nhau theo profile; không có branch theo project trong `app/engine/`.

### 15.3. `test_headless` (API end-to-end, không FE)
- TestClient: POST /projects (family-package) → POST /meetings (không calendar → unassigned) → ingest 4 nhịp (mỗi nhịp 1 chunk, ts cách nhau để segmenter đóng) → GET /state đúng §15.1 → POST /assign → POST /end → POST /package → FakeRepoConnector nhận đúng file `meetings/{date}-family-package.md` + `meeting-state.json`.

### 15.4. `test_khong_dung_tay`
- Toàn luồng 15.3 **không có endpoint thao tác nào được gọi ngoài** ingest/end (assign chỉ vì fallback routing). Assert: không tồn tại API "close beat"/"classify" trong openapi schema.

### 15.5. Bảng tổng kết acceptance (điền khi hoàn thành)
| Test | Trạng thái | Ghi chú |
|---|---|---|
| Revision (§15.1) | ✅ PASS | `test_revision.py` (4 ops create/create/supersede/answer, version 4, superseded giữ lại) + `scripts/e2e_live.py` chạy transcript qua HTTP |
| Đa-dự-án (§15.2) | ✅ PASS | `test_multi_project.py` — thêm profile UX không đụng engine |
| Headless (§15.3) | ✅ PASS | `test_api_headless.py` — ingest→state→assign→end→package qua HTTP, FE tắt |
| Không-đụng-tay (§15.4) | ✅ PASS | `test_khong_dung_tay` — openapi không có endpoint close/classify/segment |
| Model router (§10) | ✅ PASS | `test_model_router.py` — task→model theo policy, fallback, fake swap |
| Connector swap (§11) | ✅ PASS | `test_connector_swap.py` — calendar routing, repo commit, LLM_FAKE swap |
| FE mỏng (grep) | ✅ PASS | grep logic engine trên `frontend/app` rỗng — chỉ render + fetch |
| E2E Claude thật (§15.5) | ⏳ chờ key | `scripts/e2e_live.py` — chạy với `LLM_FAKE=0` + ANTHROPIC_API_KEY |

---

## 16. Definition of Done TỔNG (trước khi giao bản build đầu)

1. `pytest backend/tests` xanh 100% với `LLM_FAKE=1` (không cần mạng ngoài trừ test smoke thật).
2. Bảng §15.5 đủ PASS.
3. `LLM_FAKE=0` chạy 1 buổi họp giả (transcript thật) ra state đúng chốt cuối (tự đánh giá chất lượng, ghi kết quả).
4. Deploy được: Cloud Run (engine) + Firebase Hosting (FE) + Supabase (DB) — hướng dẫn deploy 10 bước trong README (tạo sau khi deploy xong lần đầu).
5. `solution.md` cập nhật kết quả các mục ⚠️ đã verify.
6. Không có TODO nào chạm 4 luật L1–L4.

---

## 17. Pitfalls — những chỗ dễ làm sai (đọc trước khi code phase liên quan)

1. **Apply phải validate** (old_item_id tồn tại, subject khớp) — model LLM có thể ảo giác id; apply sai → state rác. Quy tắc: op invalid → **bỏ op + warning**, không crash beat.
2. **Order tool calls giữ nguyên** — gộp ops theo thứ tự model gọi; đảo thứ tự làm lật sai.
3. **Snapshot chỉ UPDATE khi có thay đổi thật** — nếu không, FE bị push vô nghĩa (vi phạm "không nhấp nháy").
4. **Dedup ingest bằng PK (meeting_id, chunk_id)** — không dedup bằng seq (seq có thể trùng khi retry).
5. **Không nhét profile field vào `core`** — core trừu tượng cố định; field riêng phải vào `profile_fields` (nếu không mapper/template vỡ).
6. **Lock per-meeting khi process_beat** — 2 chunk vào song song cùng đóng nhịp sẽ race version snapshot.
7. **Never log transcript/prompt** — privacy; log chỉ metadata (task, model, tokens, meeting_id).
8. **sqlite vs postgres**: test dùng sqlite nên tránh `JSONB`/`gen_random_uuid()` trực tiếp trong query — dùng SQLAlchemy `JSON` + `Uuid` để portable.
9. **Tool schema động**: build bằng `json.dumps`/pydantic từ `item_schemas`, không viết tay schema cho từng profile.
10. **Escalation tắt được**: `beat_router` null trong policy = bỏ qua; không hardcode gọi.
