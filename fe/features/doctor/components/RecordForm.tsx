"use client";

import { useState } from "react";
import { ChevronDown, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { FACT_TYPE_CONFIG, URGENCY_CONFIG, URGENCY_ORDER } from "../constants";
import type { ClinicalFactType, FactDraft, FactOrigin, FinalizeInput } from "../types";
import { FactSources } from "./FactSources";
import { OriginBadge } from "./RecordBadges";

export const EMPTY_FINALIZE: FinalizeInput = {
  diagnosis: "",
  notes: "",
  isReferenceCase: false,
  reasoning: "",
  urgency: "monitor",
  instructions: [""],
  facts: [],
};

/** Khớp cách server gán origin lúc chốt: sửa dữ kiện có sẵn → bác sĩ sửa; tự thêm → bác sĩ ghi nhận */
export function displayOrigin(f: FactDraft): FactOrigin {
  if (!f.original) return "doctor_observed";
  const changed =
    f.label.trim() !== f.original.label || f.detail.trim() !== f.original.detail || f.factType !== f.original.factType;
  return changed ? "doctor_corrected" : f.original.origin;
}

function Label({ children, hint }: { children: React.ReactNode; hint?: string }) {
  const text = <span className="text-xs font-semibold text-foreground">{children}</span>;
  return hint ? (
    <Hint side="top" content={hint}>
      <span className="w-fit">{text}</span>
    </Hint>
  ) : (
    text
  );
}

function FactRow({
  fact,
  onChange,
  onRemove,
}: {
  fact: FactDraft;
  onChange: (f: FactDraft) => void;
  onRemove: () => void;
}) {
  const [showSources, setShowSources] = useState(false);
  return (
    <li className="space-y-2 rounded-xl border border-border bg-card/60 p-3">
      <div className="flex items-center gap-2">
        <Select value={fact.factType} onValueChange={(v) => onChange({ ...fact, factType: v as ClinicalFactType })}>
          <SelectTrigger size="sm" className="h-8 w-32 shrink-0 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent position="popper" side="bottom" align="start">
            {Object.entries(FACT_TYPE_CONFIG).map(([v, c]) => (
              <SelectItem key={v} value={v}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={fact.label}
          onChange={(e) => onChange({ ...fact, label: e.target.value })}
          placeholder="Tên dữ kiện"
          aria-label="Tên dữ kiện"
          className="h-8 text-sm font-medium"
        />
        <Button type="button" variant="ghost" size="icon" aria-label="Bỏ dữ kiện" onClick={onRemove} className="size-8 shrink-0">
          <X className="size-4" />
        </Button>
      </div>
      <Textarea
        rows={2}
        value={fact.detail}
        onChange={(e) => onChange({ ...fact, detail: e.target.value })}
        placeholder="Chi tiết"
        aria-label="Chi tiết dữ kiện"
        className="text-xs"
      />
      <div className="flex items-center justify-between gap-2">
        <OriginBadge origin={displayOrigin(fact)} />
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
      </div>
      {showSources && <FactSources sources={fact.sources} compact />}
    </li>
  );
}

/** Thân form chốt bệnh án — dùng chung cho chốt từ ca tư vấn và khám trực tiếp */
export function RecordForm({ value, onChange }: { value: FinalizeInput; onChange: (v: FinalizeInput) => void }) {
  const set = <K extends keyof FinalizeInput>(k: K, v: FinalizeInput[K]) => onChange({ ...value, [k]: v });
  const setFact = (i: number, f: FactDraft) => set("facts", value.facts.map((x, j) => (j === i ? f : x)));
  const addFact = () =>
    set("facts", [
      ...value.facts,
      { key: `new-${Date.now()}`, sourceFactId: null, factType: "lesion", label: "", detail: "", original: null, sources: [] },
    ]);

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <section className="space-y-4">
        <div className="space-y-1.5">
          <Label>Nhận định</Label>
          <Input
            value={value.diagnosis}
            onChange={(e) => set("diagnosis", e.target.value)}
            placeholder="Vd: Nghi vảy nến mảng"
            autoFocus
          />
        </div>
        <div className="space-y-1.5">
          <Label hint="Cơ sở dẫn tới nhận định. Chỉ bác sĩ xem, bệnh nhân không thấy.">Cơ sở nhận định</Label>
          <Textarea rows={3} value={value.reasoning} onChange={(e) => set("reasoning", e.target.value)} className="text-sm" />
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
          <Label hint="Hướng điều trị, hẹn tái khám… Bệnh nhân xem được ở tab Bệnh án.">Ghi chú</Label>
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
        <div className="flex items-center justify-between">
          <Label hint="Dữ kiện lâm sàng được chốt vào phiếu. Sửa dữ kiện có sẵn sẽ ghi là 'Bác sĩ sửa', thêm mới ghi là 'Bác sĩ ghi nhận'.">
            Dữ kiện <span className="font-mono text-muted-foreground">{value.facts.length}</span>
          </Label>
          <Button type="button" variant="ghost" size="xs" className="gap-1 text-muted-foreground" onClick={addFact}>
            <Plus className="size-3.5" /> Thêm dữ kiện
          </Button>
        </div>
        {value.facts.length === 0 ? (
          <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
            Chưa có dữ kiện
          </p>
        ) : (
          <ul className="space-y-2">
            {value.facts.map((f, i) => (
              <FactRow
                key={f.key}
                fact={f}
                onChange={(nf) => setFact(i, nf)}
                onRemove={() => set("facts", value.facts.filter((_, j) => j !== i))}
              />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
