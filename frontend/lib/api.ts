// Client API — FE mỏng tuyệt đối: chỉ fetch + type, 0 logic engine.
// Engine (cắt nhịp, state-edit, profile) 100% ở backend; FE chỉ render kết quả.
// Mọi request kèm Firebase ID token (backend verify) khi đã đăng nhập.

import { getSessionToken } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ItemType = "DECISION" | "OPEN" | "ACTION";
export type ItemStatus = "active" | "superseded" | "answered" | "flagged";

export interface StateItem {
  id: string;
  type: ItemType;
  status: ItemStatus;
  subject_key: string;
  core: Record<string, unknown>;
  profile_fields: Record<string, unknown>;
  provenance: { nhip_id: number; quote?: string };
  supersedes: string | null;
  superseded_by: string | null;
  answered_by: string | null;
  created_nhip: number;
  updated_nhip: number;
}

export interface Summary {
  decisions?: number;
  opens?: number;
  actions?: number;
  flagged?: number;
  superseded?: number;
}

export interface MeetingSummary {
  id: string;
  status: "live" | "unassigned" | "ended" | "packaged";
  profile_key: string;
  project_id: string | null;
  calendar_event_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  version: number;
  summary: Summary;
}

export interface MeetingState {
  meeting_id: string;
  status: MeetingSummary["status"];
  profile_key: string;
  version: number;
  items: StateItem[];
  summary: Summary;
}

/** Response POST /meetings — backend trả _meeting_out, hẹp hơn MeetingSummary. */
export interface MeetingRef {
  id: string;
  status: MeetingSummary["status"];
  profile_key: string;
  project_id: string | null;
  calendar_event_id: string | null;
}

export interface IngestResult {
  status: "ok" | "duplicate";
  beat: number | null;
  state_changed: boolean;
  version: number | null;
}

export interface Project {
  slug: string;
  name: string;
  repo_url: string | null;
}

export interface TranscriptChunk {
  chunk_id: string;
  seq: number;
  speaker: string | null;
  text: string;
  ts_start: number | null;
  ts_end: number | null;
}

export interface BeatInfo {
  nhip_id: number;
  status: "open" | "closed";
  transcript: string;
  started_at: string | null;
  closed_at: string | null;
}

export interface TranscriptData {
  meeting_id: string;
  status: MeetingSummary["status"];
  chunks: TranscriptChunk[];
  beats: BeatInfo[];
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = await getSessionToken();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status}: ${body || res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function listMeetings(): Promise<MeetingSummary[]> {
  const data = await request<{ items: MeetingSummary[] }>("/meetings");
  return data.items;
}

// Mở buổi họp mới. Không truyền slug → backend để "unassigned" + profile generic,
// gán dự án sau bằng assignProject (fallback routing, plan §12).
export async function createMeeting(projectSlug?: string): Promise<MeetingRef> {
  return request<MeetingRef>("/meetings", {
    method: "POST",
    body: JSON.stringify(projectSlug ? { project_slug: projectSlug } : {}),
  });
}

// Đẩy một lượt lời thoại vào engine. FE KHÔNG cắt nhịp — chỉ gửi chunk thô,
// backend tự quyết ranh giới nhịp (luật L2). Idempotent theo chunk_id.
export async function ingestChunk(
  meetingId: string,
  chunk: {
    chunk_id: string;
    seq: number;
    speaker: string | null;
    text: string;
    ts_start: number;
    ts_end: number;
  },
): Promise<IngestResult> {
  return request<IngestResult>(`/meetings/${meetingId}/ingest`, {
    method: "POST",
    body: JSON.stringify(chunk),
  });
}

export async function getState(meetingId: string): Promise<MeetingState> {
  return request<MeetingState>(`/meetings/${meetingId}/state`);
}

// Transcript thô + timeline nhịp — chỉ hiển thị (FE render thuần, 0 logic engine).
export async function getTranscript(meetingId: string): Promise<TranscriptData> {
  return request<TranscriptData>(`/meetings/${meetingId}/transcript`);
}

export async function listProjects(): Promise<Project[]> {
  return request<Project[]>("/projects");
}

export async function assignProject(meetingId: string, slug: string): Promise<void> {
  await request(`/meetings/${meetingId}/assign`, {
    method: "POST",
    body: JSON.stringify({ project_slug: slug }),
  });
}

export async function endMeeting(meetingId: string): Promise<void> {
  await request(`/meetings/${meetingId}/end`, { method: "POST" });
}

export async function packageMeeting(meetingId: string): Promise<{ files: string[]; commit: string }> {
  return request(`/meetings/${meetingId}/package`, { method: "POST" });
}
