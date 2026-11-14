"use client";

import { useEffect, useRef, useState } from "react";
import {
  Brain,
  Check,
  ChevronDown,
  Copy,
  Loader2,
  Sparkles,
  Wrench,
} from "lucide-react";
import type { ReasoningStep } from "../types";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

/**
 * Format dữ liệu đầu vào hoặc kết quả thành dạng chuỗi đẹp mắt (JSON format nếu là object).
 */
export function formatContent(data: unknown): string {
  if (data === undefined || data === null) return "";
  if (typeof data === "string") {
    try {
      const parsed = JSON.parse(data);
      if (typeof parsed === "object" && parsed !== null) {
        return JSON.stringify(parsed, null, 2);
      }
    } catch {
      // Giữ nguyên chuỗi nếu không phải JSON
    }
    return data;
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

/**
 * Format toàn bộ các bước suy luận thành văn bản markdown chi tiết để đưa vào clipboard.
 */
export function formatReasoningSteps(steps: ReasoningStep[]): string {
  if (!steps || steps.length === 0) return "";
  return steps
    .map((step, index) => {
      const num = index + 1;
      const typeBadge =
        step.type === "tool"
          ? " [Tool Call]"
          : "";
      let text = `### Bước ${num}: ${step.title}${typeBadge}`;
      const hasInput =
        step.input !== undefined &&
        step.input !== null &&
        step.input !== "";
      if (hasInput) {
        text += `\n\n**Input**:\n\`\`\`json\n${formatContent(step.input)}\n\`\`\``;
      }
      if (step.content?.trim()) {
        const outputPrefix = hasInput ? "**Output**:\n" : "";
        text += `\n\n${outputPrefix}${step.content.trim()}`;
      }
      return text;
    })
    .join("\n\n---\n\n");
}

/**
 * Format một bước suy luận đơn lẻ thành văn bản chi tiết đầy đủ để copy.
 */
export function formatSingleStep(step: ReasoningStep, index?: number): string {
  const prefix = typeof index === "number" ? `Bước ${index + 1}: ` : "Bước: ";
  const typeBadge =
    step.type === "tool"
      ? " [Tool Call]"
      : "";
  let text = `${prefix}${step.title}${typeBadge}`;
  const hasInput =
    step.input !== undefined &&
    step.input !== null &&
    step.input !== "";
  if (hasInput) {
    text += `\n\n[Input]:\n${formatContent(step.input)}`;
  }
  if (step.content?.trim()) {
    const outputPrefix = hasInput ? "[Output]:\n" : "";
    text += `\n\n${outputPrefix}${step.content.trim()}`;
  }
  return text;
}

function StepItem({
  step,
  index,
}: {
  step: ReasoningStep;
  index?: number;
  isLast?: boolean;
}) {
  const isToolCall = step.type === "tool";
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [inputCopied, setInputCopied] = useState(false);
  const [outputCopied, setOutputCopied] = useState(false);
  const processing = step.status === "processing";

  const hasInput =
    step.input !== undefined &&
    step.input !== null &&
    step.input !== "";
  const formattedInput = hasInput ? formatContent(step.input) : "";
  const formattedOutput = step.content ? formatContent(step.content) : "";

  const handleCopyInput = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!formattedInput) return;
    navigator.clipboard.writeText(formattedInput);
    setInputCopied(true);
    toast.success("Đã sao chép input của tool");
    setTimeout(() => setInputCopied(false), 2000);
  };

  const handleCopyOutput = (e: React.MouseEvent) => {
    e.stopPropagation();
    const textToCopy = step.content || formattedOutput;
    if (!textToCopy) return;
    navigator.clipboard.writeText(textToCopy);
    setOutputCopied(true);
    toast.success("Đã sao chép output của tool");
    setTimeout(() => setOutputCopied(false), 2000);
  };

  const handleCopyStep = (e: React.MouseEvent) => {
    e.stopPropagation();
    const text = formatSingleStep(step, index);
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success(`Đã sao chép: ${step.title}`);
    setTimeout(() => setCopied(false), 2000);
  };

  const stepNumber = typeof index === "number" ? String(index + 1).padStart(2, "0") : "01";

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className={cn(
        "relative flex flex-col gap-1 text-left text-xs transition-all duration-200 animate-in fade-in-50 slide-in-from-top-1",
        processing && "rounded-lg bg-brand/5 px-2 py-0.5 -mx-2 ring-1 ring-brand/20 shadow-2xs"
      )}
    >
      <div className="group/item flex w-full items-center gap-2 border-b border-border/40 py-1.5">
        {/* Step index badge */}
        <span
          className={cn(
            "font-mono text-[10px] font-semibold px-1.5 py-0.5 rounded-md shrink-0 flex items-center gap-1 transition-all",
            processing
              ? "bg-brand/20 text-brand ring-1 ring-brand/30 animate-pulse"
              : "bg-brand/10 text-brand"
          )}
        >
          {processing ? (
            <Loader2 className="size-2.5 animate-spin text-brand" />
          ) : (
            <Check className="size-2.5 text-emerald-600 dark:text-emerald-400" />
          )}
          <span>{stepNumber}</span>
        </span>

        {/* Tiêu đề & Badges & Nút thao tác */}
        <div className="flex min-w-0 flex-1 items-center justify-between gap-2 overflow-hidden">
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center justify-between gap-1.5 text-left transition-colors cursor-pointer overflow-hidden py-0.5"
            >
              <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
                <span
                  className={cn(
                    "truncate text-xs transition-colors",
                    processing
                      ? "font-medium text-brand"
                      : open
                      ? "font-semibold text-foreground"
                      : "text-muted-foreground font-normal hover:text-foreground"
                  )}
                  title={step.title}
                >
                  {step.title}
                </span>

                {processing && (
                  <span className="shrink-0 inline-flex items-center gap-1 rounded-full border border-brand/30 bg-brand/10 px-2 py-0.2 font-mono text-[10px] text-brand animate-pulse">
                    <span className="size-1.5 rounded-full bg-brand animate-ping" />
                    Đang xử lý
                  </span>
                )}

                {isToolCall && (
                  <Badge
                    variant="outline"
                    className="shrink-0 border-brand/30 bg-brand/10 text-[10px] text-brand py-0 px-2 font-mono uppercase tracking-wide flex items-center gap-1 rounded-full"
                  >
                    <Wrench className="size-2.5" />
                    Tool
                  </Badge>
                )}
              </div>
              <ChevronDown
                className={cn(
                  "size-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover/item:text-foreground ml-1",
                  open && "rotate-180"
                )}
              />
            </button>
          </CollapsibleTrigger>

          <div className="flex items-center gap-1 shrink-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={handleCopyStep}
                  className="opacity-0 group-hover/item:opacity-100 p-1 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-all cursor-pointer"
                  aria-label="Sao chép bước này"
                >
                  {copied ? (
                    <Check className="size-3 text-brand" />
                  ) : (
                    <Copy className="size-3" />
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">
                {copied ? "Đã sao chép" : "Sao chép bước này"}
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>

      {/* Chi tiết nội dung bước */}
      <CollapsibleContent className="pl-6 animate-in fade-in-0 duration-150">
        <div className="text-xs leading-relaxed text-muted-foreground space-y-2.5 py-2">
          {/* Trường hợp là Tool Call hoặc có input: hiển thị Input ở trên, Output ở dưới, copy độc lập */}
          {isToolCall || hasInput ? (
            <div className="space-y-2.5">
              {/* Tool Input ở bên trên, có thể copy độc lập */}
              {hasInput && (
                <div className="rounded-xl border border-border/70 bg-muted/40 overflow-hidden shadow-2xs">
                  <div className="flex items-center justify-between border-b border-border/50 bg-muted/60 px-3 py-1.5">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-[11px] font-semibold text-brand uppercase tracking-wider">
                        Input
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        (Tham số)
                      </span>
                    </div>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          onClick={handleCopyInput}
                          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-muted-foreground hover:bg-muted hover:text-foreground transition-all cursor-pointer text-[10px]"
                          aria-label="Sao chép input"
                        >
                          {inputCopied ? (
                            <>
                              <Check className="size-3 text-brand" />
                              <span className="text-brand font-medium">Đã chép</span>
                            </>
                          ) : (
                            <>
                              <Copy className="size-3" />
                              <span>Sao chép</span>
                            </>
                          )}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top">Sao chép input của tool</TooltipContent>
                    </Tooltip>
                  </div>
                  <div className="p-3 select-text font-mono text-xs text-foreground whitespace-pre-wrap break-words max-h-72 overflow-y-auto">
                    {formattedInput}
                  </div>
                </div>
              )}

              {/* Tool Output ở bên dưới, có thể copy độc lập */}
              {step.content && (
                <div className="rounded-xl border border-border/70 bg-muted/40 overflow-hidden shadow-2xs">
                  <div className="flex items-center justify-between border-b border-border/50 bg-muted/60 px-3 py-1.5">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                        Output
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        (Kết quả)
                      </span>
                    </div>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          type="button"
                          onClick={handleCopyOutput}
                          className="flex items-center gap-1 px-1.5 py-0.5 rounded text-muted-foreground hover:bg-muted hover:text-foreground transition-all cursor-pointer text-[10px]"
                          aria-label="Sao chép output"
                        >
                          {outputCopied ? (
                            <>
                              <Check className="size-3 text-emerald-500 dark:text-emerald-400" />
                              <span className="text-emerald-600 dark:text-emerald-400 font-medium">Đã chép</span>
                            </>
                          ) : (
                            <>
                              <Copy className="size-3" />
                              <span>Sao chép</span>
                            </>
                          )}
                        </button>
                      </TooltipTrigger>
                      <TooltipContent side="top">Sao chép output của tool</TooltipContent>
                    </Tooltip>
                  </div>
                  <div className="p-3 select-text font-mono text-xs text-foreground whitespace-pre-wrap break-words max-h-80 overflow-y-auto">
                    {formattedOutput}
                  </div>
                </div>
              )}
            </div>
          ) : (
            /* Bước suy luận thông thường (thinking / default) */
            step.content && (
              <div className="rounded-xl border border-border bg-muted/40 p-3 select-text font-mono text-xs text-foreground whitespace-pre-wrap break-words">
                {step.content}
              </div>
            )
          )}
          {processing && (
            <div className="flex items-center gap-2 font-mono text-xs text-brand py-1 animate-pulse">
              <Loader2 className="size-3 animate-spin text-brand" />
              <span>Đang thực hiện bước này...</span>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ReasoningSection({
  steps,
  streaming,
}: {
  steps: ReasoningStep[];
  streaming: boolean;
}) {
  // Bắt đầu mở khi đang streaming (đang load), đóng khi đã hoàn thành
  const [open, setOpen] = useState(streaming);
  const prevStreamingRef = useRef(streaming);

  const processingCount = steps.filter(
    (step) => step.status === "processing"
  ).length;
  const [copied, setCopied] = useState(false);

  // Khi đang load (streaming = true): hiển thị các bước (mở tiến trình)
  // Khi thực hiện xong (streaming: true -> false): tự động thu gọn tiến trình suy luận
  useEffect(() => {
    if (prevStreamingRef.current && !streaming) {
      // Đợi ngắn (450ms) để người dùng kịp nhìn thấy bước cuối hoàn tất rồi thu gọn mượt mà
      const timer = setTimeout(() => {
        setOpen(false);
      }, 450);
      return () => clearTimeout(timer);
    } else if (!prevStreamingRef.current && streaming) {
      setOpen(true);
    }
    prevStreamingRef.current = streaming;
  }, [streaming]);

  if (!steps || steps.length === 0) return null;

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    const fullText = formatReasoningSteps(steps);
    try {
      await navigator.clipboard.writeText(fullText);
      setCopied(true);
      toast.success("Đã sao chép toàn bộ tiến trình suy luận");
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy reasoning steps:", err);
    }
  };

  return (
    <Collapsible
      open={open}
      onOpenChange={setOpen}
      className="my-2.5 w-full text-left"
    >
      <div className="flex items-center justify-start gap-2">
        <div
          className={cn(
            "flex h-9 max-w-full items-center justify-between gap-2 rounded-full border px-3.5 py-1 text-xs shadow-xs transition-all duration-300",
            streaming
              ? "border-brand/40 bg-brand/5 shadow-brand/10 ring-1 ring-brand/20"
              : "border-border bg-card/80 backdrop-blur-xs hover:border-brand/30 hover:bg-card"
          )}
        >
          <CollapsibleTrigger asChild>
            <button
              type="button"
              className="group flex min-w-0 flex-1 items-center gap-2 text-left cursor-pointer overflow-hidden select-none"
            >
              {streaming ? (
                <>
                  <span className="relative flex size-2 shrink-0">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand opacity-75" />
                    <span className="relative inline-flex size-2 rounded-full bg-brand" />
                  </span>
                  <span className="font-semibold text-brand shrink-0 flex items-center gap-1.5">
                    <Sparkles className="size-3.5 text-brand animate-pulse" />
                    Đang suy luận
                  </span>
                  <span className="font-mono text-[10px] text-brand/90 bg-brand/15 px-2 py-0.5 rounded-full shrink-0 font-medium">
                    {processingCount > 0 ? `${processingCount} đang xử lý • ` : ""}{steps.length} bước
                  </span>
                </>
              ) : (
                <>
                  <Brain className="size-3.5 text-brand shrink-0" />
                  <span className="font-medium text-foreground shrink-0">
                    Tiến trình suy luận
                  </span>
                  <span className="font-mono text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-full shrink-0">
                    {steps.length} bước
                  </span>
                  <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-mono text-emerald-600 dark:text-emerald-400 font-medium">
                    <Check className="size-3" />
                    Hoàn tất
                  </span>
                </>
              )}
              <ChevronDown
                className={cn(
                  "size-3.5 shrink-0 text-muted-foreground transition-transform duration-200 group-hover:text-foreground ml-auto",
                  open && "rotate-180"
                )}
              />
            </button>
          </CollapsibleTrigger>

          <div className="flex items-center shrink-0 border-l border-border pl-2 ml-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="p-1 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
                  aria-label="Sao chép toàn bộ suy luận"
                >
                  {copied ? (
                    <Check className="size-3 text-brand" />
                  ) : (
                    <Copy className="size-3" />
                  )}
                </button>
              </TooltipTrigger>
              <TooltipContent side="top">
                {copied ? "Đã sao chép" : "Sao chép toàn bộ"}
              </TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>

      <CollapsibleContent
        className={cn(
          "mt-2 border-l-2 pl-4 ml-3 py-1 space-y-1.5 transition-colors duration-200",
          streaming ? "border-brand/40" : "border-border/60"
        )}
      >
        {steps.map((step, index) => (
          <StepItem
            key={step.id}
            step={step}
            index={index}
            isLast={index === steps.length - 1}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
