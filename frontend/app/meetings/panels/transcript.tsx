"use client";

// Cột giữa — chữ thô kiểu Notion text: từng chunk theo seq, người nói + thời
// gian. Chỉ render dữ liệu từ API (FE mỏng); auto-scroll bám đáy trừ khi user đã
// cuộn lên để đọc.

import { useEffect, useRef } from "react";

import type { TranscriptChunk } from "@/lib/api";

function fmt(sec: number | null): string {
  if (sec === null) return "--:--";
  const s = Math.floor(sec);
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function TranscriptPanel({
  chunks,
  live,
  interim = "",
}: {
  chunks: TranscriptChunk[];
  live: boolean;
  /** Chữ mic đang nghe, chưa chốt câu — hiện mờ, chưa gửi ingest. */
  interim?: string;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  useEffect(() => {
    if (stickRef.current && boxRef.current) {
      boxRef.current.scrollTop = boxRef.current.scrollHeight;
    }
  }, [chunks.length, interim]);

  return (
    <section className="flex h-full min-h-0 flex-col rounded-md border border-line bg-paper">
      <header className="flex items-center justify-between border-b border-line px-4 py-2">
        <h2 className="text-[13px] font-semibold text-ink">Transcript</h2>
        <span className="flex items-center gap-1.5 text-xs text-ink-3">
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${
              live ? "animate-pulse bg-ok" : "bg-ink-3"
            }`}
          />
          {live ? "đang họp" : "đã dừng"}
        </span>
      </header>
      <div
        ref={boxRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        }}
        className="flex-1 overflow-y-auto px-4 py-3"
      >
        {chunks.length === 0 && (
          <p className="text-sm text-ink-3">
            Chưa có chữ — đang chờ nhịp đầu tiên… (transcript thô hiện ra ở đây khi
            chunk từ STT được ingest)
          </p>
        )}
        {chunks.length === 0 && interim && <div className="h-1" />}
        {chunks.map((c) => (
          <div key={c.chunk_id} className="mb-1.5 text-[15px] leading-relaxed text-ink">
            <span className="mr-1.5 text-ink-3">•</span>
            {c.speaker && (
              <span className="mr-1.5 font-medium text-ink-2">{c.speaker}:</span>
            )}
            {c.text}
            <span className="ml-2 font-mono text-[10px] text-ink-3">{fmt(c.ts_start)}</span>
          </div>
        ))}
        {interim && (
          <div className="mb-1.5 text-[15px] leading-relaxed text-ink-3 italic">
            <span className="mr-1.5">•</span>
            {interim}
            <span className="ml-1 animate-pulse">▍</span>
          </div>
        )}
      </div>
    </section>
  );
}
