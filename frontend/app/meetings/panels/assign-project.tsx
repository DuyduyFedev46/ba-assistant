"use client";

// HITL cho phép sau họp: gán meeting chưa có dự án vào project (fallback routing).
// Còn đang họp thì khoá — engine tự route qua calendar, không đụng tay khi họp (L5).

import { useState } from "react";

import type { Project } from "@/lib/api";

export function AssignProject({
  meetingId,
  status,
  profileKey,
  projects,
  busy,
  onAssign,
}: {
  meetingId: string;
  status: string;
  profileKey: string;
  projects: Project[];
  busy: boolean;
  onAssign: (slug: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState("");

  if (status === "live") {
    return (
      <span className="rounded bg-hover px-2 py-1 text-xs text-ink-2">{profileKey}</span>
    );
  }

  return (
    <div className="relative">
      <button
        disabled={busy}
        onClick={() => setOpen((v) => !v)}
        className="rounded-md border border-line-2 bg-paper px-3 py-1.5 text-sm text-ink hover:bg-hover disabled:opacity-50"
      >
        {profileKey}
        <span className="ml-1 text-ink-3">▾</span>
      </button>
      {open && (
        <div className="absolute right-0 z-10 mt-1 w-64 rounded-md border border-line bg-paper p-3 shadow-md">
          <p className="text-xs text-ink-2">
            Gán dự án (họp {meetingId.slice(0, 8)}) — remap state qua profile mới:
          </p>
          <select
            value={pick}
            onChange={(e) => setPick(e.target.value)}
            className="mt-2 w-full rounded-md border border-line-2 bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-accent"
          >
            <option value="">— chọn project —</option>
            {projects.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.name} ({p.slug})
              </option>
            ))}
          </select>
          <button
            disabled={!pick || busy}
            onClick={() => {
              onAssign(pick);
              setOpen(false);
            }}
            className="mt-2 w-full rounded-md bg-ink px-3 py-1.5 text-sm font-medium text-white hover:bg-ink/90 disabled:opacity-40"
          >
            Gán
          </button>
        </div>
      )}
    </div>
  );
}
