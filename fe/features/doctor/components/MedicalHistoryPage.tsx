"use client";

import { useState } from "react";
import { ChevronDown, Plus, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Hint } from "@/components/ui/hint";
import { Input } from "@/components/ui/input";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { cn } from "@/lib/utils";
import { TIME_FILTERS, URGENCY_CONFIG, URGENCY_ORDER } from "../constants";
import { useMyMedicalRecords } from "../hooks";
import type { Urgency } from "../types";
import { CreateMedicalRecordDialog } from "./CreateMedicalRecordDialog";
import { MedicalRecordDetail } from "./MedicalRecordDetail";
import { MedicalRecordTable } from "./MedicalRecordTable";

const DAY_MS = 24 * 3600 * 1000;

function FilterChip<T extends string>({
  label,
  value,
  options,
  onChange,
  active,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  active: boolean;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex items-center gap-1 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
            active ? "border-brand/40 bg-brand/10 text-brand" : "border-border bg-card text-foreground hover:bg-muted"
          )}
        >
          {label}
          <ChevronDown className="size-3 opacity-60" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-40">
        <DropdownMenuRadioGroup value={value} onValueChange={(v) => onChange(v as T)}>
          {options.map((o) => (
            <DropdownMenuRadioItem key={o.value} value={o.value} className="text-xs">
              {o.label}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function MedicalHistoryPage() {
  const [query, setQuery] = useState("");
  const [days, setDays] = useState<string>("30");
  const [urgency, setUrgency] = useState<Urgency | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const { data: all = [], isLoading } = useMyMedicalRecords(useDebouncedValue(query.trim()));
  // mốc "bây giờ" cố định khi mở màn để bộ lọc thời gian không đổi giữa các lần render
  const [now] = useState(() => Date.now());

  const since = days === "all" ? null : now - Number(days) * DAY_MS;
  const records = all.filter(
    (r) =>
      (since === null || new Date(r.createdAt).getTime() >= since) &&
      (urgency === "all" || r.snapshot?.assessment.urgency === urgency)
  );
  // chưa chọn (hoặc bản đang chọn bị lọc mất) thì hiện bản mới nhất
  const selected = records.find((r) => r.id === selectedId) ?? records[0] ?? null;
  const timeLabel = TIME_FILTERS.find((t) => String(t.days ?? "all") === days)?.label ?? "";

  return (
    <div className="flex h-full w-full flex-col gap-4 overflow-hidden bg-background p-4 sm:p-6 print:block print:h-auto print:overflow-visible print:p-0">
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <FilterChip
          label={`Thời gian: ${timeLabel}`}
          value={days}
          active={days !== "30"}
          options={TIME_FILTERS.map((t) => ({ value: String(t.days ?? "all"), label: t.label }))}
          onChange={setDays}
        />
        <FilterChip<Urgency | "all">
          label={urgency === "all" ? "Mức khẩn cấp" : `Khẩn cấp: ${URGENCY_CONFIG[urgency].label}`}
          value={urgency}
          active={urgency !== "all"}
          options={[{ value: "all", label: "Tất cả" }, ...URGENCY_ORDER.map((u) => ({ value: u, label: URGENCY_CONFIG[u].label }))]}
          onChange={setUrgency}
        />
        <div className="relative ml-auto w-full max-w-64">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Tìm bệnh nhân, nhận định"
            aria-label="Tìm theo tên bệnh nhân hoặc nhận định"
            className="h-8 rounded-full pl-8 text-xs"
          />
        </div>
        <Hint side="bottom" content="Ghi bệnh án cho ca khám trực tiếp: chọn hồ sơ bệnh nhân rồi chốt kết quả.">
          <Button size="sm" variant="brand" onClick={() => setCreating(true)} className="gap-1 rounded-full">
            <Plus className="size-3.5" /> Ghi bệnh án
          </Button>
        </Hint>
      </div>

      <div className="flex min-h-0 flex-1 gap-4 print:block">
        <div className="min-w-0 flex-1 print:hidden">
          <MedicalRecordTable
            records={records}
            total={all.length}
            loading={isLoading}
            selectedId={selected?.id ?? null}
            onSelect={setSelectedId}
          />
        </div>
        <div className="w-full max-w-md shrink-0 xl:max-w-lg print:max-w-none">
          <MedicalRecordDetail record={selected} />
        </div>
      </div>

      <CreateMedicalRecordDialog
        open={creating}
        onOpenChange={setCreating}
        onCreated={(r) => {
          setQuery("");
          setDays("30");
          setUrgency("all");
          setSelectedId(r.id);
        }}
      />
    </div>
  );
}
