import { cn } from "@/lib/utils";
import { KG_LABELS } from "../constants";
import type { KgSource } from "../types";

export const selectBox =
  "h-9 w-full cursor-pointer rounded-xl border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

export function SourceBadge({ builtin, kg }: { builtin: boolean; kg: KgSource }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap",
        builtin ? "border-border bg-muted/50 text-muted-foreground" : "border-brand/30 bg-brand/10 text-brand"
      )}
    >
      {builtin ? KG_LABELS[kg] : "Của bạn"}
    </span>
  );
}

export function Field({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="flex items-center gap-1 text-xs font-medium text-foreground">{label}</span>
      {children}
    </label>
  );
}
