"use client";

// Panel brief — "Đã chốt": DECISION active (chấm xanh lá Notion), kèm
// "Thay cho: <chủ đề cũ>" nếu là kết quả một cú LẬT; lịch sử lật (item
// superseded giữ lại, không xoá — luật revision-aware).

import type { StateItem } from "@/lib/api";
import { Fields } from "./fields";

export function DecisionsPanel({ items }: { items: StateItem[] }) {
  const byId = new Map(items.map((i) => [i.id, i]));
  const active = items.filter((i) => i.type === "DECISION" && i.status === "active");
  const superseded = items.filter((i) => i.type === "DECISION" && i.status === "superseded");

  return (
    <section className="rounded-md border border-line bg-paper p-3">
      <h2 className="flex items-center gap-2 text-[13px] font-semibold text-ink">
        Đã chốt
        <span className="rounded-full bg-ok-soft px-2 py-0.5 text-xs font-normal text-ok">
          {active.length}
        </span>
      </h2>
      <ul className="mt-3 space-y-2">
        {active.length === 0 && <li className="text-sm text-ink-3">Chưa chốt gì.</li>}
        {active.map((i) => {
          const replaced = i.supersedes ? byId.get(i.supersedes) : null;
          return (
            <li key={i.id} className="rounded-md border border-line bg-paper p-3">
              <div className="flex items-start justify-between gap-2">
                <span className="flex items-center gap-1.5 text-xs font-medium text-ink">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-ok" />
                  {i.subject_key}
                </span>
                <span className="text-[10px] text-ink-3">nhịp {i.updated_nhip}</span>
              </div>
              {replaced && (
                <p className="mt-1 pl-3 text-xs text-ok">
                  Thay cho: <span className="font-medium">{replaced.subject_key}</span>
                </p>
              )}
              <Fields values={{ ...i.core, ...i.profile_fields }} />
            </li>
          );
        })}
      </ul>

      {superseded.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-xs text-ink-3 hover:text-ink-2">
            Lịch sử lật ({superseded.length} phương án đã thay)
          </summary>
          <ul className="mt-2 space-y-2">
            {superseded.map((i) => {
              const next = i.superseded_by ? byId.get(i.superseded_by) : null;
              return (
                <li key={i.id} className="rounded-md border border-line bg-hover p-3">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-xs font-medium text-ink-2 line-through">
                      {i.subject_key}
                    </span>
                    <span className="text-[10px] text-ink-3">nhịp {i.updated_nhip}</span>
                  </div>
                  {next && (
                    <p className="mt-1 text-xs text-ink-2">
                      Bị thay bởi: <span className="font-medium">{next.subject_key}</span>
                    </p>
                  )}
                  <Fields values={{ ...i.core, ...i.profile_fields }} />
                </li>
              );
            })}
          </ul>
        </details>
      )}
    </section>
  );
}
