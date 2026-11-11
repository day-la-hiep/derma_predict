"use client";

import { useState } from "react";
import { ChevronDown, Plus, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { FACT_TYPE_CONFIG, URGENCY_CONFIG, URGENCY_ORDER } from "../constants";
import type { FactDraft, FinalizeInput } from "../types";
import { FactSources } from "./FactSources";

export const EMPTY_FINALIZE: FinalizeInput = {
  diagnosis: "",
  notes: "",
  isReferenceCase: false,
  reasoning: "",
  description: "",
  urgency: "monitor",
  instructions: [""],
  facts: [],
  images: [],
};

/** Ba trường bắt buộc của kết luận: nhận định, cơ sở nhận định, mô tả của bác sĩ */
export function isFinalizeComplete(v: FinalizeInput): boolean {
  return Boolean(v.diagnosis.trim() && v.reasoning.trim() && v.description.trim());
}

function Label({ children, hint, required }: { children: React.ReactNode; hint?: string; required?: boolean }) {
  const text = (
    <span className="text-xs font-semibold text-foreground">
      {children}
      {required && <span className="ml-0.5 text-destructive" aria-hidden="true">*</span>}
    </span>
  );
  return hint ? (
    <Hint side="top" content={hint}>
      <span className="w-fit">{text}</span>
    </Hint>
  ) : (
    text
  );
}

// dữ kiện AI ghi nhận: chỉ xem, giữ nguyên hoặc bỏ (bỏ rồi vẫn khôi phục được trước khi lưu)
function FactRow({ fact, onToggle }: { fact: FactDraft; onToggle: () => void }) {
  const [showSources, setShowSources] = useState(false);
  const removed = Boolean(fact.removed);
  return (
    <li className={cn("space-y-1.5 py-3 transition-opacity", removed && "opacity-50")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className={cn("text-sm text-foreground", removed && "line-through")}>
            <span className="font-medium">{fact.label}</span>
            <span className="ml-2 text-xs text-muted-foreground">{FACT_TYPE_CONFIG[fact.factType]?.label ?? fact.factType}</span>
          </p>
          {fact.detail && <p className="text-xs text-muted-foreground">{fact.detail}</p>}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="xs"
          onClick={onToggle}
          className="shrink-0 gap-1 text-muted-foreground hover:text-foreground"
          aria-label={removed ? "Giữ lại dữ kiện" : "Bỏ dữ kiện"}
        >
          {removed ? <RotateCcw className="size-3.5" /> : <X className="size-3.5" />}
          {removed ? "Giữ lại" : "Bỏ"}
        </Button>
      </div>
      {fact.sources.length > 0 && (
        <button
          type="button"
          onClick={() => setShowSources((v) => !v)}
          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
        >
          Nguồn ({fact.sources.length})
          <ChevronDown className={cn("size-3 transition-transform", showSources && "rotate-180")} />
        </button>
      )}
      {showSources && <FactSources sources={fact.sources} compact />}
    </li>
  );
}

/** Thân form kết luận lần khám: nhận định, cơ sở, mô tả của bác sĩ (bắt buộc) và dữ kiện AI để giữ / bỏ */
export function FinalizeReportForm({ value, onChange }: { value: FinalizeInput; onChange: (v: FinalizeInput) => void }) {
  const set = <K extends keyof FinalizeInput>(k: K, v: FinalizeInput[K]) => onChange({ ...value, [k]: v });
  const toggleFact = (i: number) => set("facts", value.facts.map((x, j) => (j === i ? { ...x, removed: !x.removed } : x)));
  const kept = value.facts.filter((f) => !f.removed).length;

  return (
    <div className="grid gap-8 md:grid-cols-2">
      <section className="space-y-4">
        <div className="space-y-1.5">
          <Label required>Nhận định</Label>
          <Input
            value={value.diagnosis}
            onChange={(e) => set("diagnosis", e.target.value)}
            placeholder="Vd: Nghi vảy nến mảng"
            aria-required="true"
            autoFocus
          />
        </div>
        <div className="space-y-1.5">
          <Label required hint="Cơ sở dẫn tới nhận định. Chỉ bác sĩ xem, bệnh nhân không thấy.">
            Cơ sở nhận định
          </Label>
          <Textarea rows={3} value={value.reasoning} onChange={(e) => set("reasoning", e.target.value)} aria-required="true" className="text-sm" />
        </div>
        <div className="space-y-1.5">
          <Label required hint="Mô tả những gì bạn khám thấy. Khi lưu kết luận, hệ thống đọc mô tả và chuyển thành dữ kiện đã xác nhận.">
            Mô tả của bác sĩ
          </Label>
          <Textarea
            rows={5}
            value={value.description}
            onChange={(e) => set("description", e.target.value)}
            placeholder="Vd: Mảng đỏ ranh giới rõ, phủ vảy trắng ở khuỷu tay phải, kích thước khoảng 3 cm, không có dịch tiết."
            aria-required="true"
            className="text-sm"
          />
        </div>
        <div className="space-y-1.5">
          <Label>Mức khẩn cấp</Label>
          <div className="grid grid-cols-3 gap-1 rounded-xl bg-muted p-1" role="radiogroup" aria-label="Mức khẩn cấp">
            {URGENCY_ORDER.map((u) => (
              <Hint key={u} content={URGENCY_CONFIG[u].hint}>
                <button
                  type="button"
                  role="radio"
                  aria-checked={value.urgency === u}
                  onClick={() => set("urgency", u)}
                  className={cn(
                    "rounded-lg px-2 py-1.5 text-xs font-medium transition-all",
                    value.urgency === u ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  {URGENCY_CONFIG[u].label}
                </button>
              </Hint>
            ))}
          </div>
        </div>
        <div className="space-y-1.5">
          <Label hint="Hướng dẫn bệnh nhân sau khám, mỗi dòng một ý.">Dặn dò bệnh nhân</Label>
          <ul className="space-y-1.5">
            {value.instructions.map((ins, i) => (
              <li key={i} className="flex gap-1.5">
                <Input
                  value={ins}
                  onChange={(e) => set("instructions", value.instructions.map((x, j) => (j === i ? e.target.value : x)))}
                  placeholder="Vd: Dưỡng ẩm thường xuyên"
                  className="h-8 text-sm"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label="Bỏ dòng dặn dò"
                  className="size-8 shrink-0"
                  onClick={() => set("instructions", value.instructions.filter((_, j) => j !== i))}
                >
                  <X className="size-4" />
                </Button>
              </li>
            ))}
          </ul>
          <Button type="button" variant="ghost" size="xs" className="gap-1 text-muted-foreground" onClick={() => set("instructions", [...value.instructions, ""])}>
            <Plus className="size-3.5" /> Thêm dòng
          </Button>
        </div>
        <div className="space-y-1.5">
          <Label hint="Hướng điều trị, hẹn tái khám… Bệnh nhân xem được ở tab Kết luận.">Ghi chú</Label>
          <Textarea rows={2} value={value.notes} onChange={(e) => set("notes", e.target.value)} className="text-sm" />
        </div>
        <Hint side="right" content="Đánh dấu ca này để cân nhắc đưa vào kho tri thức tham khảo (ẩn định danh bệnh nhân).">
          <label className="flex w-fit items-center gap-2 text-xs text-muted-foreground">
            <Switch size="sm" checked={value.isReferenceCase} onCheckedChange={(v) => set("isReferenceCase", v)} />
            Ca tham khảo
          </label>
        </Hint>
      </section>

      <section className="space-y-2">
        <div>
          <Label hint="Dữ kiện AI ghi nhận từ cuộc trò chuyện. Giữ nguyên thì được đánh dấu đã xác nhận, bỏ đi thì bị xoá khỏi hồ sơ. Không sửa trực tiếp: điều bạn khám thấy hãy ghi ở phần mô tả.">
            Dữ kiện do AI ghi nhận <span className="font-mono text-muted-foreground">{kept}/{value.facts.length}</span>
          </Label>
        </div>
        {value.facts.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            AI chưa ghi nhận dữ kiện nào. Các dữ kiện từ phần mô tả sẽ được thêm khi lưu kết luận.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {value.facts.map((f, i) => (
              <FactRow key={f.key} fact={f} onToggle={() => toggleFact(i)} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
