"use client";

import type { FinalizeDraft, FinalizeInput } from "../types";

function Chip({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-border bg-background px-2.5 py-1 text-left text-[11px] text-foreground hover:border-brand disabled:cursor-default"
      disabled={!onClick}
    >
      {children}
    </button>
  );
}

// Gợi ý từ đồ thị: bấm để đưa vào form, bác sĩ vẫn tự quyết nội dung kết luận
export function SuggestionPanel({
  suggestions: s,
  onPick,
}: {
  suggestions: FinalizeDraft["suggestions"];
  onPick: (fn: (prev: FinalizeInput) => FinalizeInput) => void;
}) {
  const groups = [
    { title: "Nhận định ở các phiên trước (bấm để dùng làm nhận định)", items: s.previousConditions, pick: (t: string) => onPick((p) => ({ ...p, diagnosis: t })) },
    { title: "Lời khuyên đã dùng trước đây (bấm để thêm vào dặn dò)", items: s.previousAdvice, pick: (t: string) => onPick((p) => ({ ...p, instructions: p.instructions.includes(t) ? p.instructions : [...p.instructions, t] })) },
    { title: "Bệnh ứng viên theo đồ thị tri thức", items: s.candidateDiseases },
    { title: "Dấu hiệu cảnh báo (cờ đỏ) cần lưu ý", items: s.redFlags },
  ].filter((g) => g.items.length > 0);
  if (groups.length === 0 && s.notes.length === 0) return null;
  return (
    <section className="space-y-2 rounded-lg border border-border bg-muted/30 p-3">
      <div className="text-xs font-semibold text-foreground">Gợi ý tổng hợp từ đồ thị</div>
      {groups.map((g) => (
        <div key={g.title} className="space-y-1">
          <div className="text-[11px] text-muted-foreground">{g.title}</div>
          <div className="flex flex-wrap gap-1.5">
            {g.items.map((t) => (
              <Chip key={t} onClick={g.pick ? () => g.pick!(t) : undefined}>{t}</Chip>
            ))}
          </div>
        </div>
      ))}
      {s.notes.map((n) => (
        <div key={n} className="text-[11px] text-muted-foreground">{n}</div>
      ))}
      <div className="text-[11px] italic text-muted-foreground">Chỉ là gợi ý hỗ trợ, không phải chẩn đoán y khoa.</div>
    </section>
  );
}
