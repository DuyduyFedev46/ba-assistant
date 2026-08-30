# BA_Assitant — Platform hiểu-họp theo nhịp cho BA

## ĐỌC TRƯỚC KHI CODE
1. **`IMPLEMENTATION_PLAN.md`** — plan chi tiết để triển khai (schema, prompt, API, phases, acceptance tests). Làm theo thứ tự phase, đánh dấu Definition of Done từng phase.
2. **`solution.md`** — thiết kế tổng thể v3 (đọc khi cần hiểu "vì sao").

## LUẬT BẤT BIẾN (vi phạm = sai kiến trúc, phải sửa lại)
1. **Engine headless:** mọi logic nghiệp vụ (cắt nhịp, biên tập state, đọc profile, khử mâu thuẫn, packaging, chọn model) nằm 100% trong `backend/app/engine/` + `backend/app/llm/` + `backend/app/integrations/`. Mọi thứ gọi được qua API mà không cần FE.
2. **FE mỏng tuyệt đối:** `frontend/` (Next.js) chỉ render + nhận input + gọi REST + subscribe Realtime. Server-side của Next chỉ auth/session. **0 dòng logic engine** trong FE.
3. **Engine hằng số, profile tham số:** thêm loại họp mới = thêm file YAML trong `backend/profiles/` + template. **Không sửa code engine.** Test: `git diff backend/app/engine/` phải rỗng.
4. **Model là config:** mọi LLM call đi qua `ModelRouter` với `task_id`; model/provider nằm trong `backend/config/model_policy.yaml`. Không hardcode model trong code.
5. **Không đụng tay khi họp:** không yêu cầu BA upload thủ công, bấm nút kết thúc nhịp, tự phân loại. Các điểm human-in-the-loop duy nhất: xác nhận `FLAG` lật mơ hồ, gán project fallback (sau họp).
6. **Revision-aware:** state là MỘT tài liệu sống, biên tập bằng PATCH mỗi nhịp (CREATE/SUPERSEDE/ANSWER/AMEND/FLAG). Item bị lật giữ lại `superseded`, KHÔNG xoá trắng. Không append, không rebuild từ 0.

## QUYẾT ĐỊNH MỞ — KHÔNG tự chốt, nêu giả định và hỏi
Xem mục "Quyết định mở" trong `IMPLEMENTATION_PLAN.md` (ngưỡng cắt nhịp, tín hiệu LẬT, privacy items cần verify).

## WORKFLOW
- Làm tuần tự theo phases của `IMPLEMENTATION_PLAN.md`. Mỗi phase xong: chạy `pytest backend/tests` + checklist DoD của phase đó.
- Test offline: dùng `FakeLLM` + sqlite (không cần API key). Đặt `LLM_FAKE=1` để chạy app không cần Claude API.
- Code style: Python 3.12, ruff, type hints; Next.js TypeScript. Match comment density/idiom của repo.
