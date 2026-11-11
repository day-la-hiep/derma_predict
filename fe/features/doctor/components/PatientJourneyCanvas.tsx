"use client";

import { useMemo, useState, useRef, useEffect, useCallback } from "react";
import { ZoomIn, ZoomOut, RotateCcw, Maximize2, CircleDot } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import {
  JOURNEY_NODE_CONFIG,
  JOURNEY_EDGE_CONFIG,
  DEFAULT_JOURNEY_NODE_CONFIG,
} from "../constants";
import type {
  PatientJourneyGraph,
  PatientJourneyNode,
} from "../types";

interface PositionedNode extends PatientJourneyNode {
  x: number;
  y: number;
  radius: number;
}

interface PatientJourneyCanvasProps {
  graph: PatientJourneyGraph;
  selectedNodeId: string | null;
  onSelectNode: (node: PatientJourneyNode | null) => void;
  activeFilter: string | null;
}

export function PatientJourneyCanvas({
  graph,
  selectedNodeId,
  onSelectNode,
  activeFilter,
}: PatientJourneyCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 40, y: 40 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const movedRef = useRef(false);
  const pressRef = useRef({ x: 0, y: 0 });

  // Tính toán toạ độ vị trí cho từng node theo timeline xương sống (Session 1 -> Session 2 ...)
  const { positionedNodes, nodeMap } = useMemo(() => {
    const pNodes: PositionedNode[] = [];
    const map = new Map<string, PositionedNode>();

    const patientNode = graph.nodes.find((n) => n.label === "Patient");
    const sessionNodes = graph.nodes.filter((n) => n.label === "ConsultationSession");

    // Sắp xếp các phiên tư vấn theo thứ tự ngày hoặc theo cạnh NEXT
    sessionNodes.sort((a, b) => {
      const dateA = a.properties?.date ? new Date(a.properties.date).getTime() : 0;
      const dateB = b.properties?.date ? new Date(b.properties.date).getTime() : 0;
      return dateA - dateB;
    });

    const startX = 80;
    const centerY = 270;
    const sessionSpacingX = 240;

    // 1. Vị trí node Bệnh nhân
    if (patientNode) {
      let patientDisplayName = patientNode.name;
      if (patientDisplayName.startsWith("pp-") || patientDisplayName.startsWith("user-")) {
        patientDisplayName = (patientNode.properties?.name as string) || "Bệnh nhân";
      }
      const pNode: PositionedNode = {
        ...patientNode,
        name: patientDisplayName,
        x: startX,
        y: centerY,
        radius: 44,
      };
      pNodes.push(pNode);
      map.set(pNode.id, pNode);
    }

    // 2. Vị trí các Sessions theo trục ngang
    sessionNodes.forEach((sNode, idx) => {
      const dateVal = sNode.properties?.date as string | undefined;
      let dateShort = "";
      if (dateVal) {
        try {
          const d = new Date(dateVal);
          if (!isNaN(d.getTime())) {
            dateShort = ` · ${formatDate(d)}`;
          }
        } catch {}
      }
      const displayName = `Lần khám ${idx + 1}${dateShort}`;

      const sPos: PositionedNode = {
        ...sNode,
        name: displayName,
        x: startX + 180 + idx * sessionSpacingX,
        y: centerY,
        radius: 40,
      };
      pNodes.push(sPos);
      map.set(sPos.id, sPos);

      // Tìm các node liên quan trực tiếp đến session này
      const connectedEdges = graph.edges.filter((e) => e.source === sNode.id);

      const symptoms = connectedEdges
        .filter((e) => e.type === "HAS_SYMPTOM" || e.type === "REPORTED_FACT")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      const conditions = connectedEdges
        .filter((e) => e.type === "HAS_CONDITION" || e.type === "SUSPECTED_CONDITION")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      const advices = connectedEdges
        .filter((e) => e.type === "RECEIVED_ADVICE" || e.type === "RECOMMENDED_ADVICE")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      const doctors = connectedEdges
        .filter((e) => e.type === "CONDUCTED_BY")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      const images = connectedEdges
        .filter((e) => e.type === "HAS_IMAGE")
        .map((e) => graph.nodes.find((n) => n.id === e.target))
        .filter((n): n is PatientJourneyNode => Boolean(n));

      // Phân bổ Symptoms (ở phía trên session)
      symptoms.forEach((symp, sIdx) => {
        if (!map.has(symp.id)) {
          const offsetX = (sIdx - (symptoms.length - 1) / 2) * 110;
          const pos: PositionedNode = {
            ...symp,
            x: sPos.x + offsetX,
            y: centerY - 140,
            radius: 32,
          };
          pNodes.push(pos);
          map.set(symp.id, pos);
        }
      });

      // Phân bổ Images (ở phía trên cao, hơi lệch trái để không đè symptom)
      images.forEach((imgNode, imgIdx) => {
        if (!map.has(imgNode.id)) {
          const offsetX = (imgIdx - (images.length - 1) / 2) * 100;
          const pos: PositionedNode = {
            ...imgNode,
            x: sPos.x - 70 + offsetX,
            y: centerY - 230,
            radius: 34,
          };
          pNodes.push(pos);
          map.set(imgNode.id, pos);
        }
      });

      // Phân bổ Doctors (ở phía trên cao hơn)
      doctors.forEach((doc) => {
        if (!map.has(doc.id)) {
          const pos: PositionedNode = {
            ...doc,
            x: sPos.x + 80,
            y: centerY - 210,
            radius: 34,
          };
          pNodes.push(pos);
          map.set(doc.id, pos);
        }
      });

      // Phân bổ Conditions (ở phía dưới bên trái)
      conditions.forEach((cond, cIdx) => {
        if (!map.has(cond.id)) {
          const pos: PositionedNode = {
            ...cond,
            x: sPos.x - 70 + cIdx * 90,
            y: centerY + 130,
            radius: 34,
          };
          pNodes.push(pos);
          map.set(cond.id, pos);
        }
      });

      // Phân bổ Advices (ở phía dưới bên phải)
      advices.forEach((adv, aIdx) => {
        if (!map.has(adv.id)) {
          const offsetX = (aIdx - (advices.length - 1) / 2) * 110;
          const pos: PositionedNode = {
            ...adv,
            x: sPos.x + 70 + offsetX,
            y: centerY + 210,
            radius: 32,
          };
          pNodes.push(pos);
          map.set(adv.id, pos);
        }
      });
    });

    // Thêm các node mồ côi nếu có
    graph.nodes.forEach((n) => {
      if (!map.has(n.id)) {
        const pos: PositionedNode = {
          ...n,
          x: startX + pNodes.length * 70,
          y: centerY + 280,
          radius: 30,
        };
        pNodes.push(pos);
        map.set(n.id, pos);
      }
    });

    return { positionedNodes: pNodes, nodeMap: map };
  }, [graph]);

  // Các cạnh hợp lệ có cả source và target toạ độ
  const edgesWithCoords = useMemo(() => {
    return graph.edges
      .map((edge) => {
        const source = nodeMap.get(edge.source);
        const target = nodeMap.get(edge.target);
        if (!source || !target) return null;
        return { ...edge, sourceNode: source, targetNode: target };
      })
      .filter((e): e is NonNullable<typeof e> => Boolean(e));
  }, [graph.edges, nodeMap]);

  // Hover: làm nổi node + láng giềng + cạnh nối trực tiếp (hiện nhãn quan hệ). Click (selected): tập trung, ẩn gần hết phần còn lại.
  const focusId = selectedNodeId;
  const activeId = focusId ?? hoveredNodeId;
  const { activeEdges, activeNodes } = useMemo(() => {
    const edges = new Set<number>();
    const nodes = new Set<string>();
    if (!activeId) return { activeEdges: edges, activeNodes: nodes };
    nodes.add(activeId);
    edgesWithCoords.forEach((e, idx) => {
      if (e.source === activeId || e.target === activeId) {
        edges.add(idx);
        nodes.add(e.source);
        nodes.add(e.target);
      }
    });
    return { activeEdges: edges, activeNodes: nodes };
  }, [activeId, edgesWithCoords]);
  const fadedOpacity = focusId ? "opacity-[0.08]" : "opacity-25";

  // Xử lý kéo thả canvas
  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest(".node-element")) return;
    movedRef.current = false;
    pressRef.current = { x: e.clientX, y: e.clientY };
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging) return;
    if (Math.abs(e.clientX - pressRef.current.x) + Math.abs(e.clientY - pressRef.current.y) > 3) movedRef.current = true;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  }, [isDragging, dragStart]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
      return () => {
        window.removeEventListener("mousemove", handleMouseMove);
        window.removeEventListener("mouseup", handleMouseUp);
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  // Zoom bằng cuộn chuột
  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
    setZoom((prev) => Math.min(Math.max(prev * zoomFactor, 0.35), 2.5));
  };

  // Tự động căn chỉnh toàn bộ các node vào vừa vặn giữa khung nhìn
  const fitView = useCallback(() => {
    if (!containerRef.current || positionedNodes.length === 0) return;
    const { clientWidth: width, clientHeight: height } = containerRef.current;
    if (width === 0 || height === 0) return;

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    positionedNodes.forEach((n) => {
      minX = Math.min(minX, n.x - n.radius - 30);
      maxX = Math.max(maxX, n.x + n.radius + 30);
      minY = Math.min(minY, n.y - n.radius - 30);
      maxY = Math.max(maxY, n.y + n.radius + 40);
    });

    const graphWidth = maxX - minX;
    const graphHeight = maxY - minY;

    const padding = 40;
    const availableWidth = Math.max(width - padding * 2, 100);
    const availableHeight = Math.max(height - padding * 2, 100);

    const scaleX = availableWidth / graphWidth;
    const scaleY = availableHeight / graphHeight;
    const newZoom = Math.min(Math.max(Math.min(scaleX, scaleY), 0.35), 1.1);

    const centerX = (minX + maxX) / 2;
    const centerYPos = (minY + maxY) / 2;

    const newPanX = width / 2 - centerX * newZoom;
    const newPanY = height / 2 - centerYPos * newZoom;

    setZoom(Number(newZoom.toFixed(2)));
    setPan({ x: Math.round(newPanX), y: Math.round(newPanY) });
  }, [positionedNodes]);

  // Tự động căn chỉnh khi đồ thị được nạp lần đầu hoặc kích thước container thay đổi
  useEffect(() => {
    if (positionedNodes.length === 0 || !containerRef.current) return;
    const el = containerRef.current;

    // Chạy fitView ngay khi mount và sau đó 120ms (sau khi modal transition hoàn tất)
    fitView();
    const timer = setTimeout(() => {
      fitView();
    }, 120);

    const observer = new ResizeObserver(() => {
      fitView();
    });
    observer.observe(el);

    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, [positionedNodes.length, fitView]);

  return (
    <div
      ref={containerRef}
      onMouseDown={handleMouseDown}
      // bấm vào nền (không phải kéo) thì bỏ tập trung
      onClick={(e) => {
        if (!(e.target as HTMLElement).closest(".node-element") && !movedRef.current && selectedNodeId) onSelectNode(null);
      }}
      onWheel={handleWheel}
      className={cn(
        "relative h-full w-full overflow-hidden select-none bg-radial from-muted/20 to-background",
        isDragging ? "cursor-grabbing" : "cursor-grab"
      )}
    >
      {/* Background Dots Pattern */}
      <svg className="absolute inset-0 h-full w-full pointer-events-none opacity-20">
        <defs>
          <pattern id="graph-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <circle cx="2" cy="2" r="1" className="fill-foreground" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#graph-grid)" />
      </svg>

      {/* Floating Controls Toolbar */}
      <div className="absolute bottom-4 left-4 z-10 flex items-center gap-1 rounded-xl border border-border bg-card/90 p-1 shadow-md backdrop-blur-md">
        <Hint side="top" content="Phóng to">
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setZoom((z) => Math.min(z + 0.15, 2.5))}
          >
            <ZoomIn className="size-4" />
          </Button>
        </Hint>
        <Hint side="top" content="Thu nhỏ">
          <Button
            variant="ghost"
            size="icon-xs"
            onClick={() => setZoom((z) => Math.max(z - 0.15, 0.35))}
          >
            <ZoomOut className="size-4" />
          </Button>
        </Hint>
        <div className="h-4 w-px bg-border my-auto mx-0.5" />
        <Hint side="top" content="Vừa khung nhìn (Fit view)">
          <Button variant="ghost" size="icon-xs" onClick={() => fitView()}>
            <Maximize2 className="size-4" />
          </Button>
        </Hint>
        <Hint side="top" content="Đặt lại 100%">
          <Button variant="ghost" size="icon-xs" onClick={() => { setZoom(1); fitView(); }}>
            <RotateCcw className="size-4" />
          </Button>
        </Hint>
        <Hint side="top" content={`Tỷ lệ: ${Math.round(zoom * 100)}%`}>
          <span className="px-1.5 text-[11px] font-mono text-muted-foreground">
            {Math.round(zoom * 100)}%
          </span>
        </Hint>
      </div>

      {/* SVG Canvas */}
      <svg className="h-full w-full overflow-hidden">
        <defs>
          {/* Mũi tên định hướng cho từng loại liên kết */}
          {Object.entries(JOURNEY_EDGE_CONFIG).map(([type, cfg]) => (
            <marker
              key={type}
              id={`arrow-${type}`}
              viewBox="0 0 10 10"
              refX="18"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1.5 L 8 5 L 0 8.5 z" fill={cfg.strokeColor} />
            </marker>
          ))}
          <filter id="node-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" floodOpacity="0.15" />
          </filter>
        </defs>

        {/* Viewport Transform Group */}
        <g
          transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}
          style={{
            transformOrigin: "0 0",
            transition: isDragging ? "none" : "transform 0.08s ease-out",
          }}
        >

        {/* 1. Render Edges */}
        <g className="edges-layer">
          {edgesWithCoords.map((edge, idx) => {
            const isHighlighted = activeEdges.has(idx);
            const isDimmed = Boolean(activeId) && !isHighlighted;
            const edgeCfg = JOURNEY_EDGE_CONFIG[edge.type] ?? {
              label: edge.type,
              strokeColor: "#94a3b8",
            };
            const isNext = edge.type === "NEXT";

            // Đường cong Bezier giữa source và target
            const sx = edge.sourceNode.x;
            const sy = edge.sourceNode.y;
            const tx = edge.targetNode.x;
            const ty = edge.targetNode.y;
            const dx = tx - sx;
            const dy = ty - sy;

            // Uốn cong đường NEXT lên trên, và uốn cong HAD_SESSION xa xuống dưới để tránh đâm xuyên tâm các session
            const isHadSessionLong = edge.type === "HAD_SESSION" && Math.abs(dx) > 250;
            const cx = sx + dx / 2;
            const cy = isNext
              ? sy - 45
              : isHadSessionLong
              ? sy + 75 + Math.min(Math.abs(dx) / 10, 40)
              : sy + dy / 2;

            const isCurved = isNext || isHadSessionLong;
            const pathData = isCurved
              ? `M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}`
              : `M ${sx} ${sy} L ${tx} ${ty}`;

            return (
              <g
                key={`edge-${idx}`}
                className={cn("pointer-events-none transition-opacity duration-200", isDimmed && fadedOpacity)}
              >
                {/* Đường dẫn chính */}
                <path
                  d={pathData}
                  fill="none"
                  stroke={edgeCfg.strokeColor}
                  strokeWidth={isHighlighted ? 2.5 : isNext ? 2 : 1.5}
                  strokeDasharray={isNext ? "6 4" : isHadSessionLong ? "3 3" : undefined}
                  markerEnd={`url(#arrow-${edge.type})`}
                />
                {/* Nhãn quan hệ chỉ hiện cho cạnh của node đang hover / tập trung, để đồ thị không rối */}
                {isHighlighted && (
                <text
                  x={cx}
                  y={isNext ? cy - 8 : isHadSessionLong ? cy + 14 : (sy + ty) / 2 - 6}
                  textAnchor="middle"
                  className={cn(
                    "text-[10px] font-semibold tracking-wide fill-foreground pointer-events-none select-none"
                  )}
                  style={{
                    backgroundColor: "var(--background)",
                    paintOrder: "stroke",
                    stroke: "var(--card)",
                    strokeWidth: 3,
                    strokeLinejoin: "round",
                  }}
                >
                  {edgeCfg.label}
                </text>
                )}
              </g>
            );
          })}
        </g>

        {/* 2. Render Nodes */}
        <g className="nodes-layer">
          {positionedNodes.map((node) => {
            const isSelected = selectedNodeId === node.id;
            const isHovered = hoveredNodeId === node.id;
            const isFaded = Boolean(activeId) && !activeNodes.has(node.id);
            const isFilteredOut =
              activeFilter &&
              activeFilter !== "all" &&
              (activeFilter === "Symptom"
                ? node.label !== "Symptom" && node.label !== "Lesion" && node.label !== "ClinicalFact"
                : activeFilter === "Condition"
                ? node.label !== "Condition" && node.label !== "SuspectedCondition"
                : activeFilter === "PatientImage"
                ? node.label !== "PatientImage"
                : node.label !== activeFilter);
            const cfg = JOURNEY_NODE_CONFIG[node.label] ?? DEFAULT_JOURNEY_NODE_CONFIG;
            const Icon = cfg.icon ?? CircleDot;

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectNode(isSelected ? null : node);
                }}
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId(null)}
                className={cn(
                  "node-element cursor-pointer transition-opacity duration-200",
                  isFilteredOut && "opacity-25 grayscale",
                  isFaded && fadedOpacity
                )}
              >
                {/* Quầng sáng khi hover (không dùng scale: CSS scale trên <g> SVG lấy gốc ở góc khung nên node bị lệch) */}
                {isHovered && !isSelected && <circle r={node.radius + 5} fill={cfg.dotColor} fillOpacity="0.12" stroke={cfg.dotColor} strokeOpacity="0.5" strokeWidth="1.5" />}
                {/* Vòng hào quang khi selected */}
                {isSelected && (
                  <circle
                    r={node.radius + 6}
                    fill="none"
                    stroke={cfg.dotColor}
                    strokeWidth="2.5"
                    strokeDasharray="4 2"
                    className="animate-spin"
                    style={{ transformOrigin: "0 0" }}
                  />
                )}

                {/* Vòng tròn thân Node */}
                <circle
                  r={node.radius}
                  fill="var(--card)"
                  stroke={cfg.dotColor}
                  strokeWidth={isSelected || isHovered ? 2.5 : 1.5}
                  filter="url(#node-shadow)"
                />

                {/* Chấm chỉ báo màu */}
                <circle
                  r={node.radius - 4}
                  fill={cfg.dotColor}
                  fillOpacity="0.12"
                />

                {/* Icon ở trung tâm */}
                <foreignObject
                  x={-12}
                  y={node.label === "ConsultationSession" || node.label === "Patient" ? -18 : -12}
                  width="24"
                  height="24"
                  className="pointer-events-none"
                >
                  <div className="flex h-full w-full items-center justify-center text-foreground">
                    {Icon ? <Icon className="size-4" style={{ color: cfg.dotColor }} /> : null}
                  </div>
                </foreignObject>

                {/* Label ngắn gọn phía dưới */}
                <text
                  x="0"
                  y={node.radius + 15}
                  textAnchor="middle"
                  className="text-[11px] font-semibold fill-foreground pointer-events-none select-none"
                  style={{ paintOrder: "stroke", stroke: "var(--background)", strokeWidth: 3, strokeLinejoin: "round" }}
                >
                  {isHovered || isSelected || node.name.length <= 18 ? node.name : `${node.name.slice(0, 16)}…`}
                </text>

                {/* Sub-label loại node */}
                <text
                  x="0"
                  y={node.radius + 27}
                  textAnchor="middle"
                  className="text-[9px] font-medium fill-muted-foreground pointer-events-none select-none"
                >
                  {cfg.label}
                </text>
              </g>
            );
          })}
        </g>
        </g>
      </svg>
    </div>
  );
}
