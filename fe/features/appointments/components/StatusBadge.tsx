import { Hint } from "@/components/ui/hint";
import { cn } from "@/lib/utils";
import { APPOINTMENT_STATUS } from "../constants";
import type { AppointmentStatus } from "../types";

export function StatusBadge({ status }: { status: AppointmentStatus }) {
  const c = APPOINTMENT_STATUS[status];
  return (
    <Hint content={c.hint}>
      <span className={cn("inline-flex w-fit shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium", c.className)}>{c.label}</span>
    </Hint>
  );
}
