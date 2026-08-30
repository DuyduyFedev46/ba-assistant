"""E2E Phase 9 — transcript §15 qua HTTP thật (plan.md §15.1/15.5).

Chạy với backend bất kỳ: fake (LLM_FAKE=1 LLM_FAKE_ECHO=1) hoặc Claude thật (LLM_FAKE=0).
    python scripts/e2e_live.py [API_URL]

Luồng: tạo project → mở meeting → ingest 4 nhịp → state → end → package.
Không assert cứng với LLM thật (không deterministic) — in state để đối chiếu §15.5.
"""

from __future__ import annotations

import sys

import httpx

API = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

# Transcript §15.1 — 4 nhịp, text BẤT BIẾN; ts chỉnh gap ≥ 8s ở chunk đóng để segmenter
# đóng "certain" (gap + cue). Nhịp 2 không có cue đóng → fake không đóng (cần LLM confirm,
# chỉ Claude thật xử lý); in rõ ở kết quả.
BEATS: list[list[tuple[float, float, str]]] = [
    [  # nhịp 1: chốt phương án A (đóng: gap 12-3=9s + cue "vậy chốt")
        (0.0, 3.0, "BE-Nam: phần thanh toán thì em thấy phương án A ổn."),
        (12.0, 14.0, "BA-Ha: ok vậy chốt phương án A cho luồng thanh toán nhé."),
    ],
    [  # nhịp 2: rate limit — mở (không chốt; không cue đóng → cần LLM confirm)
        (22.0, 24.0, "BA-Ha: còn rate limit thì mình tính thế nào nhỉ?"),
        (25.0, 27.0, "Ecom-Tuan: chưa rõ, phụ thuộc hạ tầng."),
        (28.0, 30.0, "BA-Ha: vậy để mở, mai hỏi thêm bên platform."),
    ],
    [  # nhịp 3: LẬT sang phương án B (đóng: gap 40-30=10s + cue "vậy chốt")
        (30.0, 32.0, "BE-Nam: thôi đổi sang phương án B đi, A không kịp deadline tuần sau."),
        (40.0, 42.0, "BA-Ha: ok, vậy chốt B, bỏ A."),
    ],
    [  # nhịp 4: trả lời treo (chunk 1 có cue "chốt 100"? không trong list — gap + LLM confirm)
        (50.0, 52.0, "BA-Ha: rate limit chốt 100 req/s nhé."),
        (60.0, 62.0, "Ecom-Tuan: ok."),
    ],
]


def main() -> None:
    with httpx.Client(base_url=API, timeout=60) as c:
        # 1. project
        yaml_text = open("profiles/family-package.yaml", encoding="utf-8").read()
        r = c.post(
            "/projects",
            json={"slug": "family-package", "name": "Family Package", "profile_yaml": yaml_text},
        )
        if r.status_code == 409:
            print("· project đã tồn tại — dùng tiếp")
        else:
            r.raise_for_status()

        # 2. meeting
        # Gán project thẳng bằng slug — không phụ thuộc Google Calendar.
        # Muốn test routing qua calendar thì đổi thành {"event_id": "evt-family"}
        # (cần GOOGLE_APPLICATION_CREDENTIALS, hoặc LLM_FAKE=1 để dùng fake calendar).
        r = c.post("/meetings", json={"project_slug": "family-package"})
        r.raise_for_status()
        meeting = r.json()
        print(
            f"· meeting {meeting['id'][:8]} status={meeting['status']} "
            f"profile={meeting['profile_key']}"
        )

        # 3. ingest theo nhịp
        seq = 0
        for beat_i, chunks in enumerate(BEATS, start=1):
            for ts0, ts1, text in chunks:
                seq += 1
                r = c.post(
                    f"/meetings/{meeting['id']}/ingest",
                    json={
                        "chunk_id": f"n{beat_i}c{seq}",
                        "seq": seq,
                        "speaker": text.split(":")[0],
                        "text": text,
                        "ts_start": ts0,
                        "ts_end": ts1,
                    },
                )
                r.raise_for_status()
                res = r.json()
                if res.get("state_changed"):
                    print(f"  nhịp {beat_i} đóng → version {res['version']}")

        # 4. state — đối chiếu §15.5
        state = c.get(f"/meetings/{meeting['id']}/state").json()
        print(f"\nSTATE version={state['version']} summary={state['summary']}")
        for it in state["items"]:
            title = it["core"].get("title", "?")
            pf = it["profile_fields"]
            extra = f" supersedes={it['supersedes'][:8]}" if it["supersedes"] else ""
            extra += f" answered_by={it['answered_by'][:8]}" if it["answered_by"] else ""
            print(f"  [{it['type']:<8}] {it['status']:<10} {title}{extra} {pf if pf else ''}")

        # 5. end + package
        r = c.post(f"/meetings/{meeting['id']}/end")
        r.raise_for_status()
        r = c.post(f"/meetings/{meeting['id']}/package")
        r.raise_for_status()
        pkg = r.json()
        print(f"\nPACKAGE: files={list(pkg['files'])} commit={pkg['commit']} repo={pkg['repo']}")

        # 6. op_log
        ops = c.get(f"/meetings/{meeting['id']}/oplog").json()["items"]
        print(f"OPLOG: {[e['op_type'] for e in ops]}")

        # 7. khuyến nghị đối chiếu (Claude thật có thể lệch — đối chiếu tay)
        statuses = {i["type"]: i["status"] for i in state["items"]}
        if statuses.get("DECISION") == "active" and statuses.get("OPEN") in (None, "answered"):
            print("\n§15.5 Revision: PASS (chỉ DECISION active, treo đã đóng hoặc không có)")
        else:
            print("\n§15.5 Revision: KIỂM TRA TAY — state trên, đối chiếu bảng §15.5")
        if not statuses:
            print("⚠️  state rỗng — LLM không tạo item (fake không bật LLM_FAKE_ECHO=1?)")


if __name__ == "__main__":
    main()
