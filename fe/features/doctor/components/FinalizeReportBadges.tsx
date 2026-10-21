import { Hint } from "@/components/ui/hint";
import { cn } from "@/lib/utils";
import { FACT_ORIGIN_CONFIG, URGENCY_CONFIG } from "../constants";
import type { FactOrigin, Urgency } from "../types";

const BADGE = "inline-flex w-fit shrink-0 items-center rounded-full border px-2 py-0.5 text-[10px] font-medium";

export function UrgencyBadge({ urgency, className }: { urgency: Urgency; className?: string }) {
  const cfg = URGENCY_CONFIG[urgency];
  return (
    <Hint content={cfg.hint}>
      <span className={cn(BADGE, cfg.badgeClass, className)}>{cfg.label}</span>
    </Hint>
  );
}

export function OriginBadge({ origin, className }: { origin: FactOrigin; className?: string }) {
  const cfg = FACT_ORIGIN_CONFIG[origin];
  return (
    <Hint content={cfg.hint}>
      <span className={cn(BADGE, cfg.badgeClass, className)}>{cfg.label}</span>
    </Hint>
  );
}
