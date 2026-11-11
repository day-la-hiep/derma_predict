"use client";

import { useMemo } from "react";
import { Calendar } from "lucide-react";
import { cn, formatDateTime } from "@/lib/utils";
import type { PatientJourneyGraph, PatientJourneyNode } from "../types";

interface PatientJourneyTimelineProps {
  graph: PatientJourneyGraph;
  selectedNodeId: string | null;
  onSelectNode: (node: PatientJourneyNode | null) => void;
  activeFilter: string | null;
}

// các nhóm hiển thị trong một lần khám: cạnh nối ra từ node phiên tới nội dung
const GROUPS = [
  { key: "images", title: "Ảnh tổn thương", edges: ["HAS_IMAGE"], filter: "PatientImage" },
  { key: "symptoms", title: "Triệu chứng", edges: ["HAS_SYMPTOM", "REPORTED_FACT"], filter: "Symptom" },
  { key: "conditions", title: "Chẩn đoán", edges: ["HAS_CONDITION", "SUSPECTED_CONDITION"], filter: "Condition" },
  { key: "advices", title: "Dặn dò", edges: ["RECEIVED_ADVICE", "RECOMMENDED_ADVICE"], filter: "Advice" },
] as const;

function timeOf(node: PatientJourneyNode): number {
  const d = node.properties?.date;
  return d ? new Date(d).getTime() : 0;
}

// Dòng thời gian dạng chữ, lần khám mới nhất ở trên cùng; bấm một mục để xem chi tiết ở khung bên phải
export function PatientJourneyTimeline({ graph, selectedNodeId, onSelectNode, activeFilter }: PatientJourneyTimelineProps) {
  const visits = useMemo(() => {
    const chronological = graph.nodes.filter((n) => n.label === "ConsultationSession").sort((a, b) => timeOf(a) - timeOf(b));
    const byId = new Map(graph.nodes.map((n) => [n.id, n]));
    return chronological
      .map((session, i) => {
        const out = graph.edges.filter((e) => e.source === session.id);
        const pick = (types: readonly string[]) =>
          out.filter((e) => types.includes(e.type)).map((e) => byId.get(e.target)).filter((n): n is PatientJourneyNode => Boolean(n));
        return {
          session,
          number: i + 1,
          doctors: pick(["CONDUCTED_BY"]),
          groups: GROUPS.map((g) => ({ ...g, nodes: pick(g.edges) })).filter((g) => g.nodes.length > 0),
        };
      })
      .reverse();
  }, [graph]);

  if (visits.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center p-6 text-center text-muted-foreground">
        <Calendar className="mb-2 size-8 opacity-30" />
        <p className="text-sm">Chưa có lần khám nào được ghi nhận trên đồ thị.</p>
      </div>
    );
  }

  const pickable = (selected: boolean) =>
    cn("text-left text-sm transition-colors hover:text-brand hover:underline", selected ? "font-semibold text-brand underline" : "text-foreground");

  return (
    <div className="h-full overflow-y-auto px-6 py-5">
      <ol className="relative space-y-8 border-l border-border pl-6">
        {visits.map((v, idx) => {
          const sessionSelected = selectedNodeId === v.session.id;
          const matchesFilter =
            !activeFilter || activeFilter === "all" || activeFilter === "ConsultationSession" || v.groups.some((g) => g.filter === activeFilter || g.nodes.some((n) => n.label === activeFilter));
          return (
            <li key={v.session.id} className={cn("relative transition-opacity duration-200", !matchesFilter && "opacity-40")}>
              <span className={cn("absolute -left-[1.85rem] top-1.5 size-2.5 rounded-full border-2 border-background", idx === 0 ? "bg-brand" : "bg-muted-foreground/50")} />
              <header className="mb-2">
                <button type="button" onClick={() => onSelectNode(sessionSelected ? null : v.session)} className={cn("font-serif text-base font-bold", sessionSelected ? "text-brand" : "text-foreground hover:text-brand")}>
                  Lần khám {v.number}
                  {idx === 0 && <span className="ml-2 text-xs font-normal text-muted-foreground">mới nhất</span>}
                </button>
                <p className="text-xs text-muted-foreground">
                  {formatDateTime(v.session.properties?.date) || "Chưa rõ ngày"}
                  {v.doctors.length > 0 && ` · ${v.doctors.map((d) => d.name).join(", ")}`}
                </p>
              </header>

              {v.session.properties?.reason && (
                <p className="mb-2 text-sm text-foreground">
                  <span className="text-muted-foreground">Lý do: </span>
                  {v.session.properties.reason}
                </p>
              )}
              {v.session.properties?.summary && <p className="mb-2 text-sm leading-relaxed text-muted-foreground">{v.session.properties.summary}</p>}

              <dl className="space-y-2">
                {v.groups.map((g) => (
                  <div key={g.key} className="grid gap-1 sm:grid-cols-[7rem_1fr] sm:gap-4">
                    <dt className="pt-0.5 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{g.title}</dt>
                    <dd className="space-y-1">
                      {g.nodes.map((n) => {
                        const selected = selectedNodeId === n.id;
                        const fileId = n.properties?.file_id;
                        const detail = n.properties?.detail || n.properties?.notes || (n.properties?.content !== n.name ? n.properties?.content : "") || n.properties?.body_site;
                        return (
                          <div key={n.id} className="flex items-start gap-2">
                            {g.key === "images" && fileId && (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={`/api/v1/files/${fileId}/view`} alt={n.name} className="size-10 shrink-0 rounded-lg object-cover" />
                            )}
                            <button type="button" onClick={() => onSelectNode(selected ? null : n)} className={pickable(selected)}>
                              {n.name}
                              {detail && <span className="font-normal text-muted-foreground"> — {String(detail)}</span>}
                            </button>
                          </div>
                        );
                      })}
                    </dd>
                  </div>
                ))}
              </dl>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
