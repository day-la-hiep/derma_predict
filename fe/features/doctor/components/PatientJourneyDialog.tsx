"use client";

import { useState } from "react";
import {
  Network,
  GitCommitHorizontal,
  X,
  RotateCw,
  Info,
  Calendar,
  Activity,
  HeartPulse,
  Sparkles,
  Stethoscope,
  User,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Hint } from "@/components/ui/hint";
import { Skeleton } from "@/components/ui/skeleton";
import { usePatientJourneyGraph } from "../hooks";
import { errorMessage } from "../api";
import { JOURNEY_NODE_CONFIG } from "../constants";
import type { PatientJourneyNode } from "../types";
import { PatientJourneyCanvas } from "./PatientJourneyCanvas";
import { PatientJourneyTimeline } from "./PatientJourneyTimeline";

interface PatientJourneyDialogProps {
  patientId: string;
  patientName?: string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  trigger?: React.ReactNode;
}

export function PatientJourneyDialog({
  patientId,
  patientName,
  open: controlledOpen,
  onOpenChange: setControlledOpen,
  trigger,
}: PatientJourneyDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen !== undefined ? controlledOpen : internalOpen;
  const setOpen = setControlledOpen !== undefined ? setControlledOpen : setInternalOpen;

  const [viewMode, setViewMode] = useState<"graph" | "timeline">("graph");
  const [activeFilter, setActiveFilter] = useState<string>("all");
  const [selectedNode, setSelectedNode] = useState<PatientJourneyNode | null>(null);

  const { data: graph, isLoading, isError, error, refetch } = usePatientJourneyGraph(open ? patientId : null);

  // Thống kê nhanh số lượng thực thể
  const stats = {
    sessions: graph?.nodes.filter((n) => n.label === "ConsultationSession").length ?? 0,
    symptoms:
      graph?.nodes.filter((n) => n.label === "Symptom" || n.label === "Lesion" || n.label === "ClinicalFact")
        .length ?? 0,
    conditions:
      graph?.nodes.filter((n) => n.label === "Condition" || n.label === "SuspectedCondition").length ?? 0,
    advices: graph?.nodes.filter((n) => n.label === "Advice").length ?? 0,
    images: graph?.nodes.filter((n) => n.label === "PatientImage").length ?? 0,
  };

  const FILTER_TABS = [
    { id: "all", label: "Tất cả", count: graph?.nodes.length ?? 0 },
    { id: "ConsultationSession", label: "Phiên tư vấn", count: stats.sessions },
    { id: "PatientImage", label: "Ảnh bệnh", count: stats.images },
    { id: "Symptom", label: "Triệu chứng", count: stats.symptoms },
    { id: "Condition", label: "Chẩn đoán", count: stats.conditions },
    { id: "Advice", label: "Dặn dò", count: stats.advices },
  ];

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {trigger ? (
        <DialogTrigger asChild>{trigger}</DialogTrigger>
      ) : (
        <DialogTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5 border-brand/30 text-brand hover:bg-brand/10">
            <Network className="size-3.5" /> Hành trình bệnh
          </Button>
        </DialogTrigger>
      )}

      <DialogContent
        showCloseButton={false}
        className="flex h-[90vh] max-h-[900px] w-[95vw] max-w-6xl flex-col gap-0 p-0 overflow-hidden sm:rounded-2xl"
      >
        {/* Header Bar */}
        <DialogHeader className="border-b border-border bg-card/60 px-6 py-4 backdrop-blur-md">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2.5">
                <div className="flex size-8 items-center justify-center rounded-xl bg-brand/10 text-brand">
                  <Network className="size-4" />
                </div>
                <div>
                  <DialogTitle className="font-serif text-lg font-bold text-foreground">
                    Hành trình bệnh {patientName ? `· ${patientName}` : ""}
                  </DialogTitle>
                  <DialogDescription className="text-xs text-muted-foreground">
                    Đồ thị tri thức bệnh nhân (Personal Knowledge Graph) liên kết qua các phiên tư vấn
                  </DialogDescription>
                </div>
              </div>
            </div>

            {/* Controls: Mode Switcher & Close */}
            <div className="flex items-center gap-2">
              <div className="flex rounded-xl border border-border bg-muted/40 p-1">
                <button
                  type="button"
                  onClick={() => setViewMode("graph")}
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
                    viewMode === "graph"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Network className="size-3.5" /> Đồ thị mạng
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("timeline")}
                  className={cn(
                    "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all",
                    viewMode === "timeline"
                      ? "bg-background text-foreground shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <GitCommitHorizontal className="size-3.5" /> Dòng thời gian
                </button>
              </div>

              <Hint side="bottom" content="Làm mới dữ liệu từ Neo4j">
                <Button variant="ghost" size="icon-sm" onClick={() => void refetch()}>
                  <RotateCw className="size-4" />
                </Button>
              </Hint>

              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => setOpen(false)}
                className="rounded-lg text-muted-foreground hover:text-foreground"
              >
                <X className="size-4" />
              </Button>
            </div>
          </div>

          {/* Filter Bar & Quick Stats */}
          <div className="flex flex-wrap items-center justify-between gap-3 pt-3">
            <div className="flex flex-wrap items-center gap-1.5">
              {FILTER_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveFilter(tab.id)}
                  className={cn(
                    "flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
                    activeFilter === tab.id
                      ? "bg-brand text-brand-foreground"
                      : "bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  {tab.label}
                  <span
                    className={cn(
                      "text-[10px] px-1 rounded-full",
                      activeFilter === tab.id ? "bg-brand-foreground/20 text-brand-foreground" : "bg-border text-foreground"
                    )}
                  >
                    {tab.count}
                  </span>
                </button>
              ))}
            </div>

            <div className="hidden sm:flex items-center gap-3 text-xs text-muted-foreground">
              <span>{stats.sessions} phiên tư vấn</span>
              <span>•</span>
              <span>{stats.symptoms} triệu chứng</span>
              <span>•</span>
              <span>{stats.conditions} chẩn đoán</span>
            </div>
          </div>
        </DialogHeader>

        {/* Content Area */}
        <div className="relative flex flex-1 min-h-0 overflow-hidden bg-background">
          {isLoading ? (
            <div className="flex flex-1 items-center justify-center p-8 space-y-4">
              <div className="w-full max-w-md space-y-3 text-center">
                <Skeleton className="h-8 w-48 mx-auto rounded-lg" />
                <Skeleton className="h-64 w-full rounded-2xl" />
                <p className="text-xs text-muted-foreground">Đang tải cấu trúc đồ thị từ cơ sở dữ liệu tri thức…</p>
              </div>
            </div>
          ) : isError ? (
            <div className="flex flex-1 flex-col items-center justify-center p-8 text-center">
              <Info className="size-8 text-destructive mb-2" />
              <p className="text-sm font-semibold text-foreground">Không thể tải đồ thị hành trình</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm">
                {error ? errorMessage(error) : "Đã xảy ra lỗi khi kết nối đồ thị bệnh nhân trên Neo4j."}
              </p>
              <Button size="sm" variant="outline" onClick={() => void refetch()} className="mt-4 gap-1.5">
                <RotateCw className="size-3.5" /> Thử lại
              </Button>
            </div>
          ) : !graph || graph.nodes.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center p-8 text-center text-muted-foreground">
              <Network className="size-12 opacity-30 mb-3" />
              <p className="text-sm font-medium text-foreground">Chưa có hành trình tư vấn</p>
              <p className="text-xs text-muted-foreground mt-1 max-w-sm">
                Bệnh nhân chưa có dữ kiện lâm sàng hoặc phiên tư vấn nào được đồng bộ lên đồ thị tri thức.
              </p>
            </div>
          ) : (
            <div className="flex h-full w-full">
              {/* Left Canvas or Timeline */}
              <div className="flex-1 min-w-0 h-full relative">
                {viewMode === "graph" ? (
                  <PatientJourneyCanvas
                    graph={graph}
                    selectedNodeId={selectedNode?.id ?? null}
                    onSelectNode={setSelectedNode}
                    activeFilter={activeFilter}
                  />
                ) : (
                  <PatientJourneyTimeline
                    graph={graph}
                    selectedNodeId={selectedNode?.id ?? null}
                    onSelectNode={setSelectedNode}
                    activeFilter={activeFilter}
                  />
                )}
              </div>

              {/* Right Side Inspector (Khi click chọn một node) */}
              {selectedNode && (
                <aside className="w-80 shrink-0 border-l border-border bg-card/80 p-5 flex flex-col justify-between backdrop-blur-md overflow-y-auto animate-in slide-in-from-right duration-200">
                  <div className="space-y-4">
                    <div className="flex items-start justify-between gap-2 border-b border-border pb-3">
                      <div className="space-y-1">
                        <span
                          className={cn(
                            "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-semibold",
                            JOURNEY_NODE_CONFIG[selectedNode.label]?.badgeClass ?? "bg-muted text-muted-foreground"
                          )}
                        >
                          {JOURNEY_NODE_CONFIG[selectedNode.label]?.label ?? selectedNode.label}
                        </span>
                        <h4 className="font-serif text-base font-bold text-foreground leading-tight">
                          {selectedNode.name}
                        </h4>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon-xs"
                        onClick={() => setSelectedNode(null)}
                        className="text-muted-foreground hover:text-foreground shrink-0"
                      >
                        <X className="size-3.5" />
                      </Button>
                    </div>

                    {/* Node Properties */}
                    <div className="space-y-3 text-xs">
                      {selectedNode.label === "PatientImage" && (
                        <div className="space-y-3 pb-2 border-b border-border/50">
                          {selectedNode.properties?.file_id && (
                            <div className="overflow-hidden rounded-xl border border-border bg-muted/30">
                              <img
                                src={`/api/v1/files/${selectedNode.properties.file_id}/view`}
                                alt={selectedNode.name}
                                className="max-h-48 w-full object-cover"
                              />
                            </div>
                          )}
                          {selectedNode.properties?.body_site && (
                            <div>
                              <p className="font-medium text-muted-foreground">Vị trí cơ thể:</p>
                              <p className="text-foreground mt-0.5 font-medium">
                                {selectedNode.properties.body_site}
                              </p>
                            </div>
                          )}
                          {selectedNode.properties?.confirmed_label && (
                            <div>
                              <p className="font-medium text-muted-foreground">Bác sĩ xác nhận:</p>
                              <p className="text-rose-600 dark:text-rose-400 font-semibold mt-0.5">
                                {selectedNode.properties.confirmed_label}
                              </p>
                            </div>
                          )}
                          {selectedNode.properties?.description && (
                            <div>
                              <p className="font-medium text-muted-foreground">Mô tả lâm sàng:</p>
                              <p className="text-foreground mt-0.5 leading-relaxed">
                                {selectedNode.properties.description}
                              </p>
                            </div>
                          )}
                        </div>
                      )}
                      {selectedNode.properties?.date && (
                        <div>
                          <p className="font-medium text-muted-foreground">Thời gian:</p>
                          <p className="text-foreground mt-0.5">
                            {new Date(selectedNode.properties.date).toLocaleString("vi-VN")}
                          </p>
                        </div>
                      )}
                      {selectedNode.properties?.reason && (
                        <div>
                          <p className="font-medium text-muted-foreground">Lý do:</p>
                          <p className="text-foreground mt-0.5 leading-relaxed">
                            {selectedNode.properties.reason}
                          </p>
                        </div>
                      )}
                      {selectedNode.properties?.summary && (
                        <div>
                          <p className="font-medium text-muted-foreground">Tóm tắt:</p>
                          <p className="text-muted-foreground mt-0.5 rounded-lg bg-muted/40 p-2.5 leading-relaxed">
                            {selectedNode.properties.summary}
                          </p>
                        </div>
                      )}
                      {selectedNode.properties?.detail && (
                        <div>
                          <p className="font-medium text-muted-foreground">Chi tiết biểu hiện:</p>
                          <p className="text-foreground mt-0.5 leading-relaxed">
                            {selectedNode.properties.detail}
                          </p>
                        </div>
                      )}
                      {selectedNode.properties?.notes && (
                        <div>
                          <p className="font-medium text-muted-foreground">Ghi chú chuyên môn:</p>
                          <p className="text-foreground mt-0.5 leading-relaxed">
                            {selectedNode.properties.notes}
                          </p>
                        </div>
                      )}
                      {selectedNode.properties?.content && (
                        <div>
                          <p className="font-medium text-muted-foreground">Nội dung hướng dẫn:</p>
                          <p className="text-foreground mt-0.5 rounded-lg bg-emerald-500/10 p-2.5 leading-relaxed text-emerald-950 dark:text-emerald-100 border border-emerald-500/20">
                            {selectedNode.properties.content}
                          </p>
                        </div>
                      )}
                      {selectedNode.properties?.department && (
                        <div>
                          <p className="font-medium text-muted-foreground">Chuyên khoa:</p>
                          <p className="text-foreground mt-0.5">{selectedNode.properties.department}</p>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="pt-4 border-t border-border">
                    <p className="text-[11px] text-muted-foreground italic text-center">
                      Nút dữ liệu đồ thị tri thức Neo4j
                    </p>
                  </div>
                </aside>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
