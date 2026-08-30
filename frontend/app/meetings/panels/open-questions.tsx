"use client";

// Panel brief — "Còn treo / cần quyết": OPEN đang active + item FLAG (đề xuất
// lật mơ hồ cần xác nhận, nổi vàng Notion). Quan trọng nhất với BA.

import type { StateItem } from "@/lib/api";
import { Fields } from "./fields";

function OpenCard({ item, flagged }: { item: StateItem; flagged: boolean }) {
  return (
    <li
      className={
        flagged
          ? "rounded-md border border-warn/40 bg-warn-soft p-3"
          : "rounded-md border border-line bg-paper p-3"
      }
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs font-medium text-ink-2">
          {flagged ? "🚩 Đề xuất lật — cần xác nhận" : item.subject_key}
        </span>
        <span className="text-[10px] text-ink-3">nhịp {item.updated_nhip}</span>
      </div>
      <Fields values={{ ...item.core, ...item.profile_fields }} />
    </li>
  );
}

export function OpenQuestionsPanel({ items }: { items: StateItem[] }) {
  const flagged = items.filter((i) => i.status === "flagged");
  const opens = items.filter((i) => i.type === "OPEN" && i.status === "active");
  if (flagged.length === 0 && opens.length === 0) {
    return (
      <section className="rounded-md border border-line bg-paper p-3">
        <h2 className="text-[13px] font-semibold text-ink">Còn treo / cần quyết</h2>
        <p className="mt-2 text-sm text-ink-3">Không có — đang rõ ràng. 👍</p>
      </section>
    );
  }
  return (
    <section className="rounded-md border border-line bg-paper p-3">
      <h2 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        Còn treo / cần quyết
        <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-normal text-warn">
          {opens.length + flagged.length}
        </span>
      </h2>
      <ul className="mt-3 space-y-2">
        {flagged.map((i) => (
          <OpenCard key={i.id} item={i} flagged />
        ))}
        {opens.map((i) => (
          <OpenCard key={i.id} item={i} flagged={false} />
        ))}
      </ul>
    </section>
  );
}
