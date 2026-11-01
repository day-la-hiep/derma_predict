"use client";

import { MessageSquareText, Quote, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { FACT_TYPE_CONFIG } from "../constants";
import { useDoctorStore } from "../store";
import type { ClinicalFact, DoctorViewMessage, SnapshotMessage } from "../types";
import { FactSources } from "./FactSources";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

function toSnapshotMessage(m: DoctorViewMessage): SnapshotMessage {
  return {
    id: m.id,
    sender: m.sender as "patient" | "ai" | "doctor",
    content: m.content,
    files: (m.attachments ?? []).map((a) => ({
      id: a.id,
      url: a.url ?? null,
      fileName: a.name,
      contentType: a.contentType ?? null,
    })),
    createdAt: m.createdAt,
  };
}

export function ClinicalFactList({ facts }: { facts: ClinicalFact[] }) {
  const messages = useDoctorStore((s) => s.messages);

  if (!facts || facts.length === 0) return null;

  return (
    <section className="space-y-2 px-4 pb-4">
      <div className="flex items-center justify-between">
        <h4 className="font-mono text-[10px] font-medium uppercase tracking-[0.15em] text-muted-foreground">
          Dữ kiện <span className="text-brand">{facts.length}</span>
        </h4>
        <span className="text-[10px] text-muted-foreground/75">Nhấn để xem tin nhắn nguồn</span>
      </div>
      <ul className="space-y-1.5">
        {facts.map((fact) => {
          const cfg = FACT_TYPE_CONFIG[fact.factType] ?? FACT_TYPE_CONFIG.other;
          const Icon = cfg.icon;

          // Danh sách tin nhắn nguồn: kết hợp từ hội thoại hiện tại hoặc từ sourceMessages được lưu trong fact
          const sourceIds = fact.sourceMessageIds ?? [];
          const matchedFromStore = messages.filter((m) => sourceIds.includes(m.id)).map(toSnapshotMessage);
          const directSources: SnapshotMessage[] = (fact.sourceMessages ?? []).map((sm) => ({
            id: sm.id,
            sender: sm.sender,
            content: sm.content,
            files: sm.files ?? [],
            createdAt: sm.createdAt,
          }));
          const sources = matchedFromStore.length > 0 ? matchedFromStore : directSources;
          const hasSources = sources.length > 0 || sourceIds.length > 0;

          return (
            <li key={fact.id}>
              <Popover>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    className={cn(
                      "group flex w-full items-start gap-2.5 rounded-xl border border-transparent p-2 text-left transition-all",
                      "hover:border-border/60 hover:bg-muted/60 active:scale-[0.99] cursor-pointer",
                      "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    )}
                  >
                    <span className={cn("mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-lg border", cfg.colorClass)}>
                      <Icon className="size-3.5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-1.5">
                        <span className="truncate text-xs font-semibold text-foreground group-hover:text-brand transition-colors">
                          {fact.templateLabel}
                        </span>
                        {hasSources && (
                          <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground group-hover:bg-brand/10 group-hover:text-brand transition-colors">
                            <MessageSquareText className="size-3" />
                            <span>{sources.length || sourceIds.length}</span>
                          </span>
                        )}
                      </div>
                      <span className="line-clamp-2 block text-[11px] leading-relaxed text-muted-foreground">
                        {fact.detail}
                      </span>
                    </div>
                  </button>
                </PopoverTrigger>

                <PopoverContent
                  side="left"
                  align="start"
                  sideOffset={10}
                  className="z-50 w-[360px] sm:w-[400px] p-0 rounded-2xl border border-border bg-popover shadow-2xl overflow-hidden flex flex-col max-h-[460px]"
                >
                  {/* Header popup dữ kiện */}
                  <div className="border-b border-border bg-muted/40 p-3.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-lg border", cfg.colorClass)}>
                          <Icon className="size-3.5" />
                        </span>
                        <h4 className="truncate text-xs font-semibold text-foreground">{fact.templateLabel}</h4>
                      </div>
                      <span className="shrink-0 rounded-md border border-border/60 bg-background/80 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                        {cfg.label}
                      </span>
                    </div>
                    {fact.detail && (
                      <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground pl-8">
                        {fact.detail}
                      </p>
                    )}
                  </div>

                  {/* Danh sách tin nhắn nguồn */}
                  <div className="flex-1 overflow-y-auto p-3.5 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <p className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
                        <Quote className="size-3.5 text-brand" />
                        <span>Đoạn chat nguồn làm căn cứ</span>
                      </p>
                      {sources.length > 0 && (
                        <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-semibold text-brand">
                          {sources.length} tin nhắn
                        </span>
                      )}
                    </div>

                    {sources.length > 0 ? (
                      <div className="pt-0.5">
                        <FactSources sources={sources} compact={false} />
                      </div>
                    ) : (
                      <div className="rounded-xl border border-dashed border-border/80 bg-muted/20 p-4 text-center">
                        <Info className="mx-auto size-5 text-muted-foreground/60 mb-1" />
                        <p className="text-xs font-medium text-foreground">Chưa có tin nhắn nguồn liên kết</p>
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                          Dữ kiện có thể được khai thác từ tiền sử hoặc do bác sĩ ghi nhận bổ sung.
                        </p>
                      </div>
                    )}
                  </div>
                </PopoverContent>
              </Popover>
            </li>
          );
        })}
      </ul>
    </section>
  );
}


