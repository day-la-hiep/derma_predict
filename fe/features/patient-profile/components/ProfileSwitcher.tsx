"use client";

import { UserRound } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { RELATIONSHIP_LABELS } from "../constants";
import { useActiveProfile } from "../hooks";

export function ProfileSwitcher({ onSwitch, compact }: { onSwitch?: (profileId: string) => void; compact?: boolean }) {
  const { profiles, activeProfile, setActiveProfileId } = useActiveProfile();
  if (profiles.length === 0) return null;
  return (
    <Select
      value={activeProfile?.id ?? ""}
      onValueChange={(id) => {
        setActiveProfileId(id);
        onSwitch?.(id);
      }}
    >
      <SelectTrigger
        size="sm"
        className={cn("w-full rounded-xl text-xs", compact && "h-8 justify-end flex-row-reverse border-transparent bg-transparent px-3 text-muted-foreground shadow-none hover:bg-muted/70 hover:text-foreground [&>svg]:size-3.5")}
        aria-label="Hồ sơ đang dùng"
        title="Hồ sơ đang dùng — lịch sử tư vấn bên dưới thuộc hồ sơ này"
      >
        {!compact && <UserRound className="size-3.5 text-muted-foreground" />}
        <SelectValue placeholder="Chọn hồ sơ" />
      </SelectTrigger>
      {/* popper: danh sách mở xuống dưới ô chọn thay vì đè lên chính ô (mặc định item-aligned của Radix) */}
      <SelectContent position="popper" side="bottom" align="start">
        {profiles.map((p) => (
          <SelectItem key={p.id} value={p.id} className="text-xs">
            {p.full_name} · {RELATIONSHIP_LABELS[p.relationship]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
