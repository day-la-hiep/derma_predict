"use client";

import { useState } from "react";
import { HintIcon } from "@/components/ui/hint";
import { cn } from "@/lib/utils";
import { EntityTypeSection } from "./EntityTypeSection";
import { RelationSection } from "./RelationSection";

const TABS = [
  { id: "relations", label: "Quan hệ" },
  { id: "entities", label: "Loại thực thể" },
] as const;

export function GraphSchemaPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("relations");
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-foreground">
          Quan hệ đồ thị
          <HintIcon
            side="right"
            content="Danh mục quan hệ và loại thực thể mà bước “Trích quan hệ” được phép lấy từ sách. Các mục có sẵn thuộc PrimeKG/DermO; bạn có thể thêm mục riêng. Thay đổi chỉ áp dụng cho lần trích tiếp theo."
          />
        </h1>
        <div className="flex gap-1 rounded-xl border border-border bg-muted/40 p-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={cn(
                "cursor-pointer rounded-lg px-3 py-1 text-sm font-medium transition-colors",
                tab === t.id ? "bg-background text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {tab === "relations" ? <RelationSection /> : <EntityTypeSection />}
    </div>
  );
}
