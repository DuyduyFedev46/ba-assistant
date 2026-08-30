"use client";

// Panel brief — "Việc cần làm": ACTION active, hiện việc • ai • hạn; chưa gán
// người phụ trách → cờ đỏ (BA cần gán, sau họp).

import type { StateItem } from "@/lib/api";
import { Fields } from "./fields";

export function ActionsPanel({ items }: { items: StateItem[] }) {
  const actions = items.filter((i) => i.type === "ACTION" && i.status === "active");

  return (
    <section className="rounded-md border border-line bg-paper p-3">
      <h2 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        Việc cần làm
        <span className="rounded-full bg-hover px-2 py-0.5 text-xs font-normal text-ink-2">
          {actions.length}
        </span>
      </h2>
      <ul className="mt-3 space-y-2">
        {actions.length === 0 && <li className="text-sm text-ink-3">Không có việc nào đang mở.</li>}
        {actions.map((i) => {
          const owner =
            (i.profile_fields.owner as string | undefined) ??
            (i.core.owner as string | undefined);
          const due =
            (i.profile_fields.due as string | undefined) ??
            (i.core.due as string | undefined);
          return (
            <li key={i.id} className="rounded-md border border-line bg-paper p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs font-medium text-ink">{i.subject_key}</span>
                {owner ? (
                  <span className="rounded bg-hover px-1.5 py-0.5 text-xs text-ink-2">
                    👤 {owner}
                  </span>
                ) : (
                  <span className="rounded bg-danger-soft px-1.5 py-0.5 text-xs font-medium text-danger">
                    🚩 chưa gán người
                  </span>
                )}
                {due && (
                  <span className="rounded bg-warn-soft px-1.5 py-0.5 text-xs text-warn">
                    hạn {due}
                  </span>
                )}
              </div>
              <Fields values={{ ...i.core, ...i.profile_fields }} />
            </li>
          );
        })}
      </ul>
    </section>
  );
}
