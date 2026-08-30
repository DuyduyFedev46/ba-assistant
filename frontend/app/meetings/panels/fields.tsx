"use client";

// Hiển thị field chung cho state item — core (trừu tượng) + profile_fields (do
// profile khai báo) trộn làm một dãy key: value. Nhãn tiếng Việt cho key quen
// thuộc; key lạ vẫn hiện tên gốc (profile có thể bơm field bất kỳ).

const LABELS: Record<string, string> = {
  content: "Nội dung",
  reason: "Lý do",
  question: "Câu hỏi",
  context: "Bối cảnh",
  task: "Việc",
  owner: "Người phụ trách",
  due: "Hạn",
  impacts: "Ảnh hưởng",
  status: "Trạng thái",
};

export function Fields({ values }: { values: Record<string, unknown> }) {
  return (
    <dl className="mt-2 space-y-1.5">
      {Object.entries(values).map(([k, v]) => (
        <div key={k} className="flex gap-2 text-sm">
          <dt className="w-28 shrink-0 text-ink-3">{LABELS[k] ?? k}</dt>
          <dd className="min-w-0 break-words text-ink">
            {typeof v === "object" ? JSON.stringify(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
