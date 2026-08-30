"use client";

// Màn hình DUY NHẤT của portal — 3 cột:
//   TRÁI  danh sách note (buổi họp) + nút mở note mới
//   GIỮA  note hiện tại: chờ bắt đầu → bấm "Bắt đầu" tạo buổi họp mới → transcript sống
//   PHẢI  brief theo state (đã chốt / còn treo / việc cần làm)
// FE mỏng tuyệt đối (luật L2): chỉ render + gọi REST. Không cắt nhịp, không phân
// loại, không suy ra state — mọi thứ đó nằm ở engine backend.

import { useCallback, useEffect, useRef, useState } from "react";

import {
  assignProject,
  createMeeting,
  endMeeting,
  getState,
  getTranscript,
  ingestChunk,
  listMeetings,
  listProjects,
  type BeatInfo,
  type MeetingState,
  type MeetingSummary,
  type Project,
  type TranscriptChunk,
} from "@/lib/api";
import { useSpeech } from "@/lib/speech";
import { ActionsPanel } from "./panels/actions";
import { AssignProject } from "./panels/assign-project";
import { DecisionsPanel } from "./panels/decisions";
import { OpenQuestionsPanel } from "./panels/open-questions";
import { TranscriptPanel } from "./panels/transcript";

const POLL_MS = 3000;

const STATUS_LABEL: Record<MeetingSummary["status"], string> = {
  live: "Đang họp",
  unassigned: "Chưa gán dự án",
  ended: "Đã kết thúc",
  packaged: "Đã đóng gói",
};

function fmtClock(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function fmtDay(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay ? `Hôm nay ${fmtClock(iso)}` : d.toLocaleDateString("vi-VN");
}

/** Timeline nhịp — nhịp đang mở nhấp nháy, nhịp đã khép đứng yên. */
function BeatTimeline({ beats }: { beats: BeatInfo[] }) {
  if (beats.length === 0) {
    return <p className="text-xs text-ink-3">Chưa có nhịp — engine sẽ cắt khi có tín hiệu.</p>;
  }
  return (
    <ul className="space-y-1">
      {beats.map((b) => (
        <li key={b.nhip_id} className="flex items-center gap-2 text-xs">
          <span
            className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
              b.status === "closed" ? "bg-ink-3" : "animate-pulse bg-ok"
            }`}
          />
          <span className="font-medium text-ink-2">Nhịp {b.nhip_id}</span>
          <span className="text-ink-3">
            {b.status === "closed" ? `khép ${fmtClock(b.closed_at)}` : "đang nói…"}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Workspace() {
  const [meetings, setMeetings] = useState<MeetingSummary[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [state, setState] = useState<MeetingState | null>(null);
  const [chunks, setChunks] = useState<TranscriptChunk[]>([]);
  const [beats, setBeats] = useState<BeatInfo[]>([]);
  const [pickSlug, setPickSlug] = useState("");
  const [speaker, setSpeaker] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ts của chunk tính theo giây kể từ lúc mở họp → khoảng lặng thật giữa 2 lượt
  // nói chính là gap mà segmenter dùng để cắt nhịp.
  const startRef = useRef<number | null>(null);
  const seqRef = useRef(0);

  const active = meetings.find((m) => m.id === activeId) ?? null;
  const isLive = active?.status === "live" || active?.status === "unassigned";

  const refreshList = useCallback(async () => {
    try {
      setMeetings(await listMeetings());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi gọi API");
    }
  }, []);

  const refreshActive = useCallback(async (id: string) => {
    try {
      const [s, t] = await Promise.all([getState(id), getTranscript(id)]);
      setState(s);
      setChunks(t.chunks);
      setBeats(t.beats);
      seqRef.current = Math.max(seqRef.current, t.chunks.length);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi gọi API");
    }
  }, []);

  useEffect(() => {
    refreshList();
    listProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
    try {
      const last = localStorage.getItem("ba.last-meeting");
      if (last) setActiveId(last);
    } catch {
      /* private window */
    }
  }, [refreshList]);

  // Poll khi có note đang mở — bản sau đổi sang SSE/Realtime.
  useEffect(() => {
    if (!activeId) {
      setState(null);
      setChunks([]);
      setBeats([]);
      return;
    }
    try {
      localStorage.setItem("ba.last-meeting", activeId);
    } catch {
      /* private window */
    }
    seqRef.current = 0;
    refreshActive(activeId);
    const t = setInterval(() => {
      refreshActive(activeId);
      refreshList();
    }, POLL_MS);
    return () => clearInterval(t);
  }, [activeId, refreshActive, refreshList]);

  // Mốc thời gian: ưu tiên started_at từ server (sống sót qua F5), fallback now.
  useEffect(() => {
    if (!active) {
      startRef.current = null;
      return;
    }
    startRef.current = active.started_at ? Date.parse(active.started_at) : Date.now();
  }, [active]);

  async function handleStart() {
    setBusy(true);
    try {
      const m = await createMeeting(pickSlug || undefined);
      startRef.current = Date.now();
      seqRef.current = 0;
      await refreshList();
      setActiveId(m.id);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không mở được buổi họp");
    } finally {
      setBusy(false);
    }
  }

  async function handleSay(speaker: string, text: string) {
    if (!activeId) return;
    const now = Date.now();
    const base = startRef.current ?? now;
    const tsStart = (now - base) / 1000;
    // ~3 từ/giây — độ dài lượt nói ước lượng từ số từ, đủ cho segmenter tính beat_sec.
    const tsEnd = tsStart + Math.max(1, text.trim().split(/\s+/).length / 3);
    const seq = seqRef.current + 1;
    seqRef.current = seq;
    try {
      await ingestChunk(activeId, {
        chunk_id: `${activeId}-${seq}`,
        seq,
        speaker: speaker.trim() || null,
        text: text.trim(),
        ts_start: Number(tsStart.toFixed(2)),
        ts_end: Number(tsEnd.toFixed(2)),
      });
      await refreshActive(activeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không gửi được lời thoại");
    }
  }

  // Mic → chữ → cùng đường ingest với ô gõ tay. Mỗi câu hoàn chỉnh = 1 lượt nói.
  const mic = useSpeech({ onFinal: (text) => handleSay(speaker, text) });

  async function handleEnd() {
    if (!activeId) return;
    setBusy(true);
    try {
      await endMeeting(activeId);
      await Promise.all([refreshList(), refreshActive(activeId)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không kết thúc được");
    } finally {
      setBusy(false);
    }
  }

  async function handleAssign(slug: string) {
    if (!activeId) return;
    setBusy(true);
    try {
      await assignProject(activeId, slug);
      await Promise.all([refreshList(), refreshActive(activeId)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không gán được dự án");
    } finally {
      setBusy(false);
    }
  }

  const items = state?.items ?? [];

  return (
    <div className="flex h-screen w-full overflow-hidden bg-canvas">
      {/* ---------------------------------------------------------- CỘT TRÁI */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-line bg-canvas">
        <div className="border-b border-line p-3">
          <button
            onClick={() => setActiveId(null)}
            className="w-full rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            + Note họp mới
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-3">
            Note hiện tại
          </p>
          {active ? (
            <div className="mb-4 rounded-md border border-accent/30 bg-paper p-3">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${
                    isLive ? "animate-pulse bg-ok" : "bg-ink-3"
                  }`}
                />
                <span className="truncate text-sm font-medium text-ink">
                  {active.profile_key}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-ink-3">
                {STATUS_LABEL[active.status]} · {fmtClock(active.started_at)}
              </p>
              <div className="mt-2 border-t border-line pt-2">
                <BeatTimeline beats={beats} />
              </div>
            </div>
          ) : (
            <div className="mb-4 rounded-md border border-accent/30 bg-paper p-3">
              <div className="flex items-center gap-2">
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
                <span className="text-sm font-medium text-ink">Cuộc họp mới</span>
              </div>
              <p className="mt-0.5 text-xs text-ink-3">Đang chờ bắt đầu</p>
            </div>
          )}

          <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-ink-3">
            Lịch sử note
          </p>
          <ul className="space-y-0.5">
            {meetings.length === 0 && (
              <li className="px-2 py-2 text-xs text-ink-3">Chưa có buổi họp nào.</li>
            )}
            {meetings.map((m) => (
              <li key={m.id}>
                <button
                  onClick={() => setActiveId(m.id)}
                  className={`w-full rounded-md p-2.5 text-left transition-colors ${
                    m.id === activeId ? "bg-paper shadow-sm" : "hover:bg-hover"
                  }`}
                >
                  <div className="truncate text-sm font-medium text-ink">{m.profile_key}</div>
                  <div className="mt-0.5 truncate text-xs text-ink-3">
                    {fmtDay(m.started_at)} · {m.summary.decisions ?? 0} chốt ·{" "}
                    {m.summary.opens ?? 0} treo
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </aside>

      {/* ---------------------------------------------------------- CỘT GIỮA */}
      <main className="flex min-w-0 flex-1 flex-col border-r border-line bg-paper">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line px-5">
          <h1 className="text-sm font-semibold text-ink">
            {active ? "Lời thoại buổi họp" : "Note mới"}
          </h1>
          {active && isLive && (
            <button
              onClick={handleEnd}
              disabled={busy}
              className="rounded-md border border-line-2 px-3 py-1.5 text-xs text-ink hover:bg-hover disabled:opacity-50"
            >
              Kết thúc họp
            </button>
          )}
        </header>

        {error && (
          <div className="border-b border-danger-soft bg-danger-soft px-5 py-2 text-xs text-danger">
            {error}
          </div>
        )}

        {!active ? (
          <StartCard
            projects={projects}
            pickSlug={pickSlug}
            onPick={setPickSlug}
            busy={busy}
            onStart={handleStart}
          />
        ) : (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-hidden p-4">
              <TranscriptPanel chunks={chunks} live={!!isLive} interim={mic.interim} />
            </div>
            {isLive && (
              <MicBar
                mic={mic}
                speaker={speaker}
                onSpeaker={setSpeaker}
                onSay={(text) => handleSay(speaker, text)}
              />
            )}
          </div>
        )}
      </main>

      {/* ---------------------------------------------------------- CỘT PHẢI */}
      <aside className="flex w-[420px] shrink-0 flex-col bg-canvas">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-paper px-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                isLive ? "animate-pulse bg-ok" : "bg-ink-3"
              }`}
            />
            Brief theo state
          </h2>
          {active && (
            <AssignProject
              meetingId={active.id}
              status={active.status}
              profileKey={active.profile_key}
              projects={projects}
              busy={busy}
              onAssign={handleAssign}
            />
          )}
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {!active ? (
            <p className="mt-16 text-center text-sm text-ink-3">
              State sẽ tự hiện khi buổi họp bắt đầu.
            </p>
          ) : items.length === 0 ? (
            <p className="mt-16 text-center text-sm text-ink-3">
              Chưa có gì — engine trích xuất sau khi khép nhịp đầu tiên.
            </p>
          ) : (
            <>
              <DecisionsPanel items={items} />
              <OpenQuestionsPanel items={items} />
              <ActionsPanel items={items} />
            </>
          )}
        </div>
      </aside>
    </div>
  );
}

/** Trạng thái chờ — chọn dự án (tuỳ chọn) rồi mở buổi họp. */
function StartCard({
  projects,
  pickSlug,
  onPick,
  busy,
  onStart,
}: {
  projects: Project[];
  pickSlug: string;
  onPick: (v: string) => void;
  busy: boolean;
  onStart: () => void;
}) {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div className="w-full max-w-md rounded-lg border border-line bg-paper p-8 text-center">
        <h2 className="text-base font-semibold text-ink">Note hiện hành đang chờ</h2>
        <p className="mt-2 text-sm text-ink-2">
          Bấm bắt đầu để mở buổi họp mới. Engine tự cắt nhịp và dựng brief bên phải.
        </p>

        <label className="mt-6 block text-left text-xs text-ink-2">
          Dự án
          <select
            value={pickSlug}
            onChange={(e) => onPick(e.target.value)}
            className="mt-1 w-full rounded-md border border-line-2 bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent"
          >
            <option value="">— chưa gán (gán sau) —</option>
            {projects.map((p) => (
              <option key={p.slug} value={p.slug}>
                {p.name}
              </option>
            ))}
          </select>
        </label>

        <button
          onClick={onStart}
          disabled={busy}
          className="mt-4 w-full rounded-md bg-accent px-6 py-3 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Đang mở…" : "Bắt đầu buổi họp"}
        </button>
      </div>
    </div>
  );
}

/** Thanh ghi âm: mic (Web Speech API) là đường chính, ô gõ tay là đường dự phòng
 *  khi trình duyệt không hỗ trợ hoặc nghe sai. Cả hai đổ vào cùng POST /ingest. */
function MicBar({
  mic,
  speaker,
  onSpeaker,
  onSay,
}: {
  mic: ReturnType<typeof useSpeech>;
  speaker: string;
  onSpeaker: (v: string) => void;
  onSay: (text: string) => void;
}) {
  const [text, setText] = useState("");

  function submit() {
    if (!text.trim()) return;
    onSay(text);
    setText("");
  }

  return (
    <div className="shrink-0 border-t border-line bg-canvas p-3">
      <div className="flex items-center gap-2">
        <button
          onClick={() => (mic.listening ? mic.stop() : mic.start())}
          disabled={!mic.supported}
          title={mic.supported ? "Bật/tắt mic" : "Trình duyệt không hỗ trợ nhận dạng giọng nói"}
          className={`flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:opacity-40 ${
            mic.listening
              ? "bg-danger-soft text-danger"
              : "border border-line-2 bg-paper text-ink hover:bg-hover"
          }`}
        >
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              mic.listening ? "animate-pulse bg-danger" : "bg-ink-3"
            }`}
          />
          {mic.listening ? "Đang nghe" : "Bật mic"}
        </button>

        <input
          value={speaker}
          onChange={(e) => onSpeaker(e.target.value)}
          placeholder="Người nói"
          className="w-32 shrink-0 rounded-md border border-line-2 bg-paper px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-accent"
        />
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="…hoặc gõ tay rồi Enter"
          className="min-w-0 flex-1 rounded-md border border-line-2 bg-paper px-3 py-2 text-sm text-ink outline-none placeholder:text-ink-3 focus:border-accent"
        />
        <button
          onClick={submit}
          className="shrink-0 rounded-md bg-ink px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          Gửi
        </button>
      </div>

      {mic.error && <p className="mt-1.5 text-[11px] text-danger">{mic.error}</p>}
      {!mic.error && (
        <p className="mt-1.5 text-[11px] text-ink-3">
          {mic.supported
            ? "Mic nghe tiếng Việt, mỗi câu trọn vẹn gửi thành một lượt nói. Khoảng lặng giữa các lượt là gap engine dùng để cắt nhịp."
            : "Trình duyệt này không nhận dạng giọng nói (Firefox) — dùng Chrome/Edge/Safari, hoặc gõ tay."}
        </p>
      )}
    </div>
  );
}
