"use client";

import { UserRound } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RELATIONSHIP_LABELS } from "../constants";
import { useActiveProfile } from "../hooks";

export function ProfileSwitcher({ onSwitch }: { onSwitch?: (profileId: string) => void }) {
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
      <SelectTrigger size="sm" className="w-full rounded-xl text-xs" aria-label="Chọn hồ sơ">
        <UserRound className="size-3.5 text-muted-foreground" />
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
