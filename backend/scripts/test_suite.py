# ruff: noqa: E501 — transcript là dữ liệu, giữ nguyên một dòng cho dễ đối chiếu
"""Bộ 10 cuộc họp mô phỏng — đo năng lực revision-aware của engine.

Mỗi case dán NGUYÊN transcript vào một lần (đúng cách BA sẽ dùng), backend tự tách
lượt nói và cắt nhịp. Chạy:  python scripts/test_suite.py [API_URL] [--only N]

Không assert cứng (LLM không deterministic) — xuất JSON để chấm tay theo cột
"cần bắt" của từng case.
"""

from __future__ import annotations

import json
import sys
import time

import httpx

API = next((a for a in sys.argv[1:] if a.startswith("http")), "http://localhost:8000")
ONLY = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)

CASES: list[dict] = [
    {
        "id": 1,
        "ten": "Họp chốt API Contract",
        "can_bat": [
            "LẬT status: String → Integer (giữ Integer sau khi bàn Boolean)",
            "LẬT updatedAt: bắt buộc → optional",
            "ACTION mờ: FE tự map Integer sang text, không ai nhận",
        ],
        "transcript": (
            "A: Bắt đầu nhé. BE đề xuất endpoint POST /batch-update nhận vào mảng object. "
            "B: Em định dùng List<Map<String, Object>> cho linh hoạt, nhưng mà field status nên là String hay Enum? "
            "C: Dùng String đi, FE gửi lên đơn giản. "
            "B: Để em check... À mà dùng String thì backend phải parse thủ công, lâu. Chốt là Integer đi, 1 là Active, 0 là Inactive. "
            "A: OK, chốt Integer. "
            "C: Khoan, nếu dùng Integer thì FE phải map sang text hiển thị, mệt. Hay là dùng Boolean? true/false cho nhanh. "
            "B: Boolean thì dễ, nhưng mở rộng sau này nếu có trạng thái Pending thì sao? Em vẫn giữ Integer. "
            "A: Vậy chốt Integer. Nhưng FE muốn thì tự map nhé. Tiếp theo field updatedAt có bắt buộc không? "
            "B: Có, em thêm luôn validation. "
            "C: Nhưng mà UI cũ không gửi updatedAt. Nếu bắt buộc là lỗi. Hay để optional, nếu không có thì BE tự lấy thời gian hiện tại. "
            "B: Được, optional. Vậy chốt là Integer status, optional updatedAt."
        ),
    },
    {
        "id": 2,
        "ten": "Backlog Refinement",
        "can_bat": [
            "LẬT priority: B là P0 → A là P0, B xuống P1",
            "LẬT điểm: A 5đ → 8đ → tách A.1 (5đ) + A.2 (5đ)",
            "TREO: A.2 chưa ai nhận, chưa vào sprint",
        ],
        "transcript": (
            "P: Sprint sau tập trung vào Story A tính năng tìm kiếm và Story B báo cáo. Story A priority P0. "
            "A: Nhưng tuần trước chốt Story B là P0 mà? "
            "P: Ừ nhưng mà marketing muốn ra tìm kiếm trước, đẩy B xuống P1. "
            "D1: Vậy Story A điểm mấy? "
            "A: Theo tôi là 5 điểm. "
            "P: 5 điểm là nhẹ, tăng lên 8 đi vì còn tích hợp Elasticsearch. "
            "D2: 8 thì sprint này không kịp. Hay tách Story A thành A.1 và A.2. A.1 làm luồng cơ bản, A.2 nâng cao. "
            "P: Ừ, tách ra. A.1 là 5 điểm, A.2 là 5 điểm. Vậy sprint này lấy A.1 và Story B 5 điểm nữa. "
            "A: Nhưng Story B chỉ còn 5 điểm vì đã bỏ bớt UI phức tạp. "
            "P: Ok chốt sprint này: A.1 5 điểm cộng B 5 điểm bằng 10 điểm."
        ),
    },
    {
        "id": 3,
        "ten": "Họp với Sếp (C-level prep)",
        "can_bat": [
            "RỦI RO: sếp bảo ghi 20% dù dữ liệu thật là 15%",
            "LẬT: có biểu đồ chi phí → bỏ → chỉ còn doanh thu",
            "TREO: sếp 'để đó tôi xem lại sau', slide 2-3 chưa chốt",
        ],
        "transcript": (
            "Boss: Slide tuần sau phải cho HĐQT thấy được tiềm năng tăng trưởng. A, em có số liệu user mới không? "
            "A: Dạ có, tháng trước tăng 15 phần trăm. "
            "Boss: 15 phần trăm là ít, ghi là 20 phần trăm đi. Họ không kiểm tra đâu. "
            "M: Nhưng bên em tracking là 15 phần trăm thật. Nếu ghi sai mà audit thì sao. "
            "Boss: Ừ thì sửa thành tăng trưởng ấn tượng không cần số cụ thể. Về phần chi phí, M làm cái biểu đồ giảm chi phí vận hành được không? "
            "M: Dạ được, nhưng phải cắt giảm mảng QC. Vậy em đề xuất giảm 10 phần trăm chi phí QC để bù vào marketing. "
            "Boss: Không được, QC phải giữ. Thôi bỏ biểu đồ chi phí đi, chỉ cần biểu đồ doanh thu. "
            "A: Vậy em sẽ gộp slide 2 và 3 vào làm một. "
            "Boss: Không gộp, slide 2 là doanh thu, slide 3 là kế hoạch action. Ừ mà thôi, để đó tôi xem lại sau. Giờ chốt là có 4 slide: Giới thiệu, Doanh thu, Action plan, Kết luận."
        ),
    },
    {
        "id": 4,
        "ten": "Bug Triage / Incident",
        "can_bat": [
            "LẬT kép: hotfix → rollback → hotfix (về lại lựa chọn đầu)",
            "ACTION: Q test phần thẻ tín dụng, không có hạn",
            "TREO: regression các phần khác chưa ai nhận test",
        ],
        "transcript": (
            "Q: Bug 123: user không thanh toán được. Lỗi này P0, phải fix ngay. "
            "A: Fix mất bao lâu? "
            "D: Fix mất 3 giờ, nhưng em có thể patch nóng hotfix trong 30 phút nếu chỉ sửa 1 dòng. "
            "A: Vậy chốt hotfix trong 30 phút. "
            "Q: Nhưng mà patch nóng thì chưa test hết regression. Em đề xuất rollback version về bản stable cũ. "
            "D: Rollback thì mất tính năng new checkout vừa ra, khách hàng cũng kêu. Hay là hotfix nhanh rồi test sau. "
            "Q: Nếu test sau mà lỗi lại thì nguy hiểm. Tôi vote rollback. "
            "A: Thôi thì rollback đi, đảm bảo user thanh toán được trước đã. Mất tính năng mới thì chấp nhận. "
            "D: Khoan, em vừa check log. Lỗi chỉ ảnh hưởng đến user dùng thẻ tín dụng, không ảnh hưởng đến ví điện tử. Vậy ta chỉ cần thông báo lỗi thẻ tín dụng, không cần rollback. Hotfix là đủ. "
            "A: Vậy chốt hotfix thẻ tín dụng, không rollback. Q, em test kỹ phần đó giúp."
        ),
    },
    {
        "id": 5,
        "ten": "Cross-team Sync",
        "can_bat": [
            "LẬT: API → CSV tạm → API có hạn thứ 5",
            "ACTION: E gửi CSV hàng ngày, chưa rõ ai import/check",
            "TREO: thứ 5 trượt thì CSV thêm 1 tuần, chưa ai đôn đốc",
        ],
        "transcript": (
            "A: Chốt tuần trước là Ecom sẽ cung cấp API sync dữ liệu sản phẩm cho Core trong tuần này. "
            "E: Team em đang bận sprint feature flash-sale, API chưa làm kịp. Tuần sau mới xong. "
            "T: Tuần sau thì Core chết, em cần data để chạy campaign quảng cáo. "
            "A: Hay là E gửi file csv hàng ngày, Core tự import tạm? "
            "T: CSV thì không realtime, nhưng tạm chấp nhận. Nhưng E phải gửi đúng format. "
            "E: Được, em gửi CSV từ hôm nay. Nhưng mà tuần sau em có API thì thôi CSV nhé. "
            "A: Vậy chốt: từ nay đến tuần sau dùng CSV, tuần sau dùng API. "
            "T: Khoan, nếu tuần sau API ra mà chậm thì sao? Em xin hạn cụ thể là thứ 3 tuần sau phải có API. "
            "E: Thứ 3 hơi gấp, thứ 5 đi. "
            "A: Vậy thứ 5. Nếu thứ 5 chưa có, vẫn dùng CSV thêm 1 tuần."
        ),
    },
    {
        "id": 6,
        "ten": "Đàm phán Vendor",
        "can_bat": [
            "LẬT giá/scope: 100k(5) → 70k(3) → 85k(4) → 90k(4+migration)",
            "MƠ HỒ: 'clean data trước' — không rõ scope, ai làm, bao lâu",
            "ACTION: A clean data, không có hạn",
        ],
        "transcript": (
            "V: Giá gói cơ bản là 100k USD một năm, bao gồm 5 tính năng chính. "
            "CFO: 100k là quá cao. Giảm còn 70k thì bàn tiếp. "
            "V: 70k thì chỉ còn 3 tính năng, bỏ tính năng báo cáo và AI suggest. "
            "A: Khoan, AI suggest là lý do chính mua CRM. Bỏ nó đi thì vô nghĩa. "
            "CFO: Anh V, vậy 85k cho 4 tính năng giữ AI suggest, bỏ báo cáo. Báo cáo thì team tự làm. "
            "V: 85k cho 4 tính năng được, nhưng mà không hỗ trợ training và migration. "
            "A: Training thì bên em tự học, nhưng migration data cần vendor hỗ trợ vì format phức tạp. "
            "CFO: Vậy thêm 5k cho migration, tổng 90k. "
            "V: Đồng ý 90k cho 4 tính năng cộng migration. Tuy nhiên thời gian migration là 2 tuần, không đảm bảo nếu data dirty. "
            "A: Em sẽ clean data trước, ok. Vậy chốt hợp đồng 90k."
        ),
    },
    {
        "id": 7,
        "ten": "Review UX/UI với khách hàng",
        "can_bat": [
            "LẬT: thanh toán cuối → lên đầu → bỏ hẳn → 2 cột",
            "MƠ HỒ: chưa đánh giá tác động kỹ thuật của 2 cột",
            "ACTION: D update mockup, không hạn",
        ],
        "transcript": (
            "C: Cái màn hình checkout này rối quá. Tôi muốn chuyển bước chọn thanh toán lên trên cùng. "
            "A: Thưa chị, theo nghiên cứu UX, bước cuối mới là chọn thanh toán vì user đã nhập xong thông tin. "
            "C: Tôi không quan tâm, tôi thấy không đẹp. Chuyển lên đầu. "
            "D: Chuyển lên đầu thì phần nhập thông tin phải xuống dưới, nhưng logic của BE là gửi thanh toán cuối, nên khó. "
            "C: Vậy bỏ thanh toán luôn, để user gọi hotline thanh toán. "
            "A: Hotline thì không tự động, loãng quy trình. Hay chị cho em đưa ra phương án: chia màn hình thành 2 cột, trái nhập info, phải chọn thanh toán. Vẫn cùng lúc, đẹp. "
            "C: Được, 2 cột. Làm đi."
        ),
    },
    {
        "id": 8,
        "ten": "Go/No-Go Decision",
        "can_bat": [
            "LẬT: Go tuần sau → No-Go, dời",
            "ACTION thiếu chủ: fix 2 lỗi P2 chưa gán cho dev nào",
            "TREO: marketing sẵn sàng chưa, chưa ai xác nhận",
        ],
        "transcript": (
            "Q: UAT đã pass 95 phần trăm. Còn 2 lỗi P2 nhỏ về giao diện, không ảnh hưởng core. "
            "PD: Vậy tuần sau release chính thức Go nhé. "
            "A: Vậy em chuẩn bị release note. "
            "Q: Khoan, 2 lỗi P2 đó liên quan đến màn hình login. Nếu release, user mới đăng ký thấy lỗi hiển thị sai, mất hình ảnh. "
            "PD: Ừ, vậy báo lỗi là gì? Fix mất 1 ngày, ta dời release sang thứ 2 tuần sau. No-Go cho kịch bản hôm nay. "
            "A: Thứ 2 tuần sau thì team marketing chưa kịp chuẩn bị thông báo. Hay là cứ release đúng lịch, nhưng ẩn chức năng login mới, dùng login cũ tạm. "
            "PD: Login cũ không hỗ trợ SSO. Mà SSO là điểm bán hàng. Thôi, No-Go, dời đến khi fix xong và marketing sẵn sàng. Hẹn 1 tuần nữa review lại."
        ),
    },
    {
        "id": 9,
        "ten": "Phân bổ nguồn lực",
        "can_bat": [
            "LẬT chuỗi: task A cho X → Y → tách A.1/A.2 → bỏ A khỏi sprint",
            "ACTION: A viết spec chi tiết",
            "HỆ QUẢ: sprint chấp nhận chậm tiến độ",
        ],
        "transcript": (
            "SM: Dev X rảnh 100 phần trăm, giao task A cho X. "
            "TL: X đang support dự án cũ, tuần sau mới rảnh. Đưa task A cho Y. "
            "A: Y đang làm task B rồi. Hay chia task A thành A.1 và A.2. Y làm A.1, X làm A.2 khi về. "
            "SM: Vậy tuần này Y làm A.1 và B? Quá tải. "
            "TL: Để em handle: Y làm B, còn A.1 giao cho intern Z, A.2 để X tuần sau. "
            "A: Intern chưa biết tech stack này. Hay A.1 để em BA viết spec chi tiết hơn để sau này X làm nhanh. Còn sprint này tạm đưa A ra khỏi scope. "
            "SM: Vậy sprint này chỉ có B, không có A. Chấp nhận chậm tiến độ."
        ),
    },
    {
        "id": 10,
        "ten": "Post-Mortem",
        "can_bat": [
            "LẬT: test hàng quý → hàng tuần → hàng tháng",
            "LẬT: runbook 2 tuần → 3 tuần",
            "TREO: ai review runbook chưa rõ",
            "ACTION: D viết runbook 3 tuần, D test lần đầu tháng sau",
        ],
        "transcript": (
            "D: Vụ mất điện là do Ops không có backup generator. "
            "O: Back-up có đấy, nhưng dev deploy sai config nên khi khởi động lại không tự start service. "
            "A: Thôi, không đổ lỗi. Vậy tới đây làm gì để không lặp lại? "
            "D: Phải có runbook sổ tay quy trình restart service sau khi mất điện. "
            "O: Runbook thì đã có, nhưng dev không đọc. "
            "D: Vì runbook viết sai. Tôi đề xuất viết lại runbook và test thử hàng quý. "
            "A: Ai viết lại? "
            "D: Ops viết. "
            "O: Ops không biết chi tiết service của dev. Dev viết. "
            "A: Vậy D viết phần service, O review phần infrastructure. Vậy chốt: viết lại runbook trong 2 tuần. "
            "D: Nhưng mà sprint này em bận, 2 tuần không kịp. 3 tuần. "
            "A: 3 tuần. Và test hàng quý, ai test thì chưa chốt. "
            "O: Test thì Ops làm, nhưng cần dev hỗ trợ. Khoan, tôi nghĩ chạy auto-test hàng tuần tốt hơn. "
            "A: Hàng tuần thì nhiều, hàng tháng đi. Vậy chốt: viết runbook 3 tuần, test hàng tháng bắt đầu từ tháng sau. Ai nhận việc test? "
            "D: Em nhận test lần đầu, vì em hiểu service."
        ),
    },
]


def run_case(c: httpx.Client, case: dict) -> dict:
    t0 = time.time()
    r = c.post("/meetings", json={})  # generic profile, không phụ thuộc calendar
    r.raise_for_status()
    mid = r.json()["id"]

    words = len(case["transcript"].split())
    r = c.post(
        f"/meetings/{mid}/ingest",
        json={
            "chunk_id": f"case{case['id']}-paste",
            "seq": 1,
            "speaker": None,
            "text": case["transcript"],
            "ts_start": 0.0,
            "ts_end": float(words * 0.4),  # ~2.5 từ/giây
        },
    )
    r.raise_for_status()
    c.post(f"/meetings/{mid}/end").raise_for_status()

    state = c.get(f"/meetings/{mid}/state").json()
    tr = c.get(f"/meetings/{mid}/transcript").json()
    ops = c.get(f"/meetings/{mid}/oplog").json()["items"]
    return {
        "id": case["id"],
        "ten": case["ten"],
        "can_bat": case["can_bat"],
        "meeting_id": mid,
        "tu": words,
        "luot": len(tr["chunks"]),
        "nhip": len(tr["beats"]),
        "giay": round(time.time() - t0, 1),
        "version": state["version"],
        "summary": state["summary"],
        "ops": [o["op_type"] for o in ops],
        "items": [
            {
                "type": it["type"],
                "status": it["status"],
                "subject_key": it["subject_key"],
                "title": it["core"].get("title"),
                "body": it["core"].get("body"),
                "fields": it["profile_fields"],
                "supersedes": it["supersedes"],
                "answered_by": it["answered_by"],
                "nhip": it["updated_nhip"],
            }
            for it in state["items"]
        ],
    }


def main() -> None:
    out = []
    with httpx.Client(base_url=API, timeout=600) as c:
        for case in CASES:
            if ONLY and case["id"] != ONLY:
                continue
            print(f"▶ Case {case['id']}: {case['ten']} …", flush=True)
            try:
                res = run_case(c, case)
            except Exception as exc:
                print(f"  ✗ LỖI: {exc}")
                out.append({"id": case["id"], "ten": case["ten"], "loi": str(exc)})
                continue
            print(
                f"  {res['tu']} từ → {res['luot']} lượt → {res['nhip']} nhịp"
                f" | v{res['version']} | ops={res['ops']} | {res['giay']}s"
            )
            out.append(res)
    path = "/tmp/test_suite_result.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n→ {path}")


if __name__ == "__main__":
    main()
