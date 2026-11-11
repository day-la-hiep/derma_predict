import { Hint } from "@/components/ui/hint";
import { cn, textOnly } from "@/lib/utils";
import { APPOINTMENT_STATUS } from "../constants";
import type { AppointmentStatus } from "../types";

export function StatusBadge({ status }: { status: AppointmentStatus }) {
  const c = APPOINTMENT_STATUS[status];
  return (
    <Hint content={c.hint}>
      <span className={cn("inline-flex w-fit shrink-0 items-center gap-1.5 text-xs font-medium", textOnly(c.className))}>
        <span className="size-1.5 rounded-full bg-current" />
        {c.label}
      </span>
    </Hint>
  );
}
