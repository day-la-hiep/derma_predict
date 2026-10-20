"use client";

import { useMemo } from "react";
import {
  Calendar,
  Activity,
  HeartPulse,
  Sparkles,
  Stethoscope,
  ArrowDown,
  Clock,
  FileText,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Hint } from "@/components/ui/hint";
import { JOURNEY_NODE_CONFIG } from "../constants";
import type { PatientJourneyGraph, PatientJourneyNode } from "../types";

interface PatientJourneyTimelineProps {
  graph: PatientJourneyGraph;
  selectedNodeId: string | null;
  onSelectNode: (node: PatientJourneyNode | null) => void;
  activeFilter: string | null;
}

export function PatientJourneyTimeline({
  graph,
  selectedNodeId,
  onSelectNode,
  activeFilter,
}: PatientJourneyTimelineProps) {
  // Gom nhóm dữ liệu theo từng phiên tư vấn
  const sessionJourney = useMemo(() => {
    const sessions = graph.nodes.filter((n) => n.label === "ConsultationSession");

    // Sắp xếp các phiên theo thời gian tăng dần
    sessions.sort((a, b) => {
      const dateA = a.properties?.date ? new Date(a.properties.date).getTime() : 0;
      const dateB = b.properties?.date ? new Date(b.properties.date).getTime() : 0;
      return dateA - dateB;
    });

    return sessions.map((session, index) => {
      const outgoingEdges = graph.edges.filter((e) => e.source === session.id);

      const symptoms = outgoingEdges
        .filter((e) => e.type === "HAS_SYMPTOM" || e.type === "REPORTED_FACT")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      const conditions = outgoingEdges
        .filter((e) => e.type === "HAS_CONDITION" || e.type === "SUSPECTED_CONDITION")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      const advices = outgoingEdges
        .filter((e) => e.type === "RECEIVED_ADVICE" || e.type === "RECOMMENDED_ADVICE")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      const doctors = outgoingEdges
        .filter((e) => e.type === "CONDUCTED_BY")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      const hasNext = outgoingEdges.some((e) => e.type === "NEXT");

      return {
        session,
        index: index + 1,
        symptoms,
        conditions,
        advices,
        doctors,
        hasNext,
      };
    });
  }, [graph]);

  if (!sessionJourney.length) {
    return (
      <div className="flex h-64 flex-col items-center justify-center p-6 text-center text-muted-foreground">
        <Calendar className="mb-2 size-8 opacity-30" />
        <p className="text-sm">Chưa có phiên tư vấn nào được ghi nhận trên đồ thị.</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-8">
      {sessionJourney.map((step, idx) => {
        const isSessionSelected = selectedNodeId === step.session.id;
        const sessionDate = step.session.properties?.date
          ? new Date(step.session.properties.date).toLocaleString("vi-VN", {
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })
          : "Chưa rõ ngày";

        const isFiltered =
          activeFilter &&
          activeFilter !== "all" &&
          activeFilter !== "ConsultationSession" &&
          !step.symptoms.some((s) => s.label === activeFilter) &&
          !step.conditions.some((c) => c.label === activeFilter) &&
          !step.advices.some((a) => a.label === activeFilter);

        return (
          <div
            key={step.session.id}
            className={cn("relative transition-opacity duration-200", isFiltered && "opacity-40")}
          >
            {/* Cột mốc thời gian bên trái */}
            <div className="flex items-start gap-4">
              <div className="flex flex-col items-center shrink-0">
                <button
                  type="button"
                  onClick={() => onSelectNode(isSessionSelected ? null : step.session)}
                  className={cn(
                    "flex size-10 items-center justify-center rounded-2xl border transition-all duration-200 shadow-sm",
                    isSessionSelected
                      ? "border-brand bg-brand text-brand-foreground ring-4 ring-brand/20 scale-105"
                      : "border-indigo-300 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950/60 dark:text-indigo-300"
                  )}
                >
                  <Calendar className="size-5" />
                </button>
                {/* Đường nối sang phiên tiếp theo */}
                {idx < sessionJourney.length - 1 && (
                  <div className="my-2 h-full w-0.5 min-h-16 bg-gradient-to-b from-indigo-400 to-indigo-200 dark:from-indigo-700 dark:to-border" />
                )}
              </div>

              {/* Thẻ nội dung phiên tư vấn */}
              <div className="flex-1 space-y-4 rounded-2xl border border-border bg-card p-5 shadow-xs transition-colors hover:border-brand/40">
                {/* Header phiên */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-indigo-500/10 px-2 py-0.5 text-xs font-semibold text-indigo-600 dark:text-indigo-400">
                        Phiên #{step.index}
                      </span>
                      <h4 className="font-serif text-base font-bold text-foreground">
                        {step.session.name}
                      </h4>
                    </div>
                    <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Clock className="size-3.5" /> {sessionDate}
                    </p>
                  </div>

                  {/* Bác sĩ phụ trách */}
                  {step.doctors.map((doc) => (
                    <Hint key={doc.id} side="left" content="Bác sĩ phụ trách và chốt bệnh án cho phiên này">
                      <button
                        type="button"
                        onClick={() => onSelectNode(selectedNodeId === doc.id ? null : doc)}
                        className="flex items-center gap-1.5 rounded-full border border-purple-200 bg-purple-50 px-3 py-1 text-xs font-medium text-purple-700 transition-colors hover:bg-purple-100 dark:border-purple-900/60 dark:bg-purple-950/50 dark:text-purple-300"
                      >
                        <Stethoscope className="size-3.5 text-purple-600 dark:text-purple-400" />
                        {doc.name}
                      </button>
                    </Hint>
                  ))}
                </div>

                {/* Lý do tư vấn & Tóm tắt AI */}
                {step.session.properties?.reason && (
                  <div className="text-xs">
                    <span className="font-semibold text-muted-foreground">Lý do tư vấn: </span>
                    <span className="text-foreground">{step.session.properties.reason}</span>
                  </div>
                )}
                {step.session.properties?.summary && (
                  <div className="rounded-xl bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
                    <p className="flex items-center gap-1 font-medium text-foreground mb-1">
                      <FileText className="size-3.5 text-brand" /> Tóm tắt phiên:
                    </p>
                    {step.session.properties.summary}
                  </div>
                )}

                {/* Khối Triệu chứng */}
                {step.symptoms.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400 flex items-center gap-1">
                      <Activity className="size-3.5" /> Triệu chứng ghi nhận ({step.symptoms.length})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {step.symptoms.map((symp) => {
                        const isSelected = selectedNodeId === symp.id;
                        return (
                          <button
                            key={symp.id}
                            type="button"
                            onClick={() => onSelectNode(isSelected ? null : symp)}
                            className={cn(
                              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs text-left transition-all",
                              isSelected
                                ? "border-amber-500 bg-amber-500/15 ring-2 ring-amber-500/20 text-amber-900 dark:text-amber-100"
                                : "border-amber-200/80 bg-amber-50/50 text-amber-800 hover:bg-amber-100/70 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300"
                            )}
                          >
                            <span className="size-1.5 rounded-full bg-amber-500" />
                            <span className="font-medium">{symp.name}</span>
                            {symp.properties?.detail && (
                              <span className="text-[11px] opacity-75">· {symp.properties.detail}</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Khối Chẩn đoán của Bác sĩ */}
                {step.conditions.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-rose-600 dark:text-rose-400 flex items-center gap-1">
                      <HeartPulse className="size-3.5" /> Chẩn đoán ({step.conditions.length})
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {step.conditions.map((cond) => {
                        const isSelected = selectedNodeId === cond.id;
                        return (
                          <button
                            key={cond.id}
                            type="button"
                            onClick={() => onSelectNode(isSelected ? null : cond)}
                            className={cn(
                              "flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs text-left transition-all",
                              isSelected
                                ? "border-rose-500 bg-rose-500/15 ring-2 ring-rose-500/20 text-rose-900 dark:text-rose-100"
                                : "border-rose-200/80 bg-rose-50/50 text-rose-800 hover:bg-rose-100/70 dark:border-rose-900/50 dark:bg-rose-950/30 dark:text-rose-300"
                            )}
                          >
                            <span className="size-1.5 rounded-full bg-rose-500" />
                            <span className="font-semibold">{cond.name}</span>
                            {cond.properties?.notes && (
                              <span className="text-[11px] opacity-75">({cond.properties.notes})</span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Khối Lời dặn / Hướng dẫn điều trị */}
                {step.advices.length > 0 && (
                  <div className="space-y-1.5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400 flex items-center gap-1">
                      <Sparkles className="size-3.5" /> Dặn dò & Điều trị ({step.advices.length})
                    </p>
                    <div className="space-y-1.5">
                      {step.advices.map((adv) => {
                        const isSelected = selectedNodeId === adv.id;
                        return (
                          <button
                            key={adv.id}
                            type="button"
                            onClick={() => onSelectNode(isSelected ? null : adv)}
                            className={cn(
                              "flex w-full items-start gap-2 rounded-xl border p-2.5 text-xs text-left transition-all",
                              isSelected
                                ? "border-emerald-500 bg-emerald-500/15 ring-2 ring-emerald-500/20 text-emerald-950 dark:text-emerald-100"
                                : "border-emerald-200/70 bg-emerald-50/40 text-emerald-800 hover:bg-emerald-100/60 dark:border-emerald-900/40 dark:bg-emerald-950/20 dark:text-emerald-300"
                            )}
                          >
                            <CheckCircle2 className="size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400 mt-0.5" />
                            <div className="min-w-0 flex-1">
                              <span className="font-medium text-foreground">{adv.name}</span>
                              {adv.properties?.content && adv.properties.content !== adv.name && (
                                <p className="mt-0.5 text-[11px] text-muted-foreground leading-relaxed">
                                  {adv.properties.content}
                                </p>
                              )}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
