"use client";

// Panel dò "bất đồng chưa giải": ô tìm kiếm regex lọc nhanh mọi item active
// theo subject/core/profile_fields. CHỈ LÀ VIEW LỌC — engine không có khái niệm
// "bất đồng" riêng; mâu thuẫn thật nằm ở item FLAG (panel treo) và lịch sử lật
// (panel chốt). Không thêm logic engine vào FE (luật L2).

import { useMemo, useState } from "react";

import type { StateItem } from "@/lib/api";

function matchesRegex(item: StateItem, re: RegExp): boolean {
  if (re.test(item.subject_key)) return true;
  for (const group of [item.core, item.profile_fields]) {
    for (const v of Object.values(group)) {
      if (typeof v === "string" && re.test(v)) return true;
    }
  }
  return false;
}

export function ConflictsPanel({ items }: { items: StateItem[] }) {
  const [q, setQ] = useState("");
  const active = items.filter((i) => i.status === "active");

  const shown = useMemo(() => {
    if (!q.trim()) return [];
    let re: RegExp;
    try {
      re = new RegExp(q.trim(), "i");
    } catch {
      return null; // regex lỗi — hiện thông báo, không crash
    }
    return active.filter((i) => matchesRegex(i, re));
  }, [active, q]);

  return (
    <section className="rounded-md border border-line bg-paper p-3">
      <h2 className="text-[13px] font-semibold text-ink">Dò bất đồng</h2>
      <p className="mt-1 text-xs text-ink-3">
        Tìm nhanh theo regex trên mọi mục đang active (xem — không sửa).
      </p>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="vd: giá|deadline|hợp đồng"
        className="mt-3 w-full rounded-md border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-accent"
      />
      {q.trim() && (
        <ul className="mt-3 space-y-2">
          {shown === null && <li className="text-sm text-danger">Regex không hợp lệ.</li>}
          {shown?.length === 0 && <li className="text-sm text-ink-3">Không khớp mục nào.</li>}
          {shown?.map((i) => (
            <li key={i.id} className="rounded-md border border-line bg-hover p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-2">
                  {i.type} · {i.subject_key}
                </span>
                <span className="text-[10px] text-ink-3">nhịp {i.updated_nhip}</span>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
