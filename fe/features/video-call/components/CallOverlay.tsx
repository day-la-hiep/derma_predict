"use client";

import { useEffect, useRef, useState } from "react";
import { Maximize2, Mic, MicOff, Minimize2, Phone, PhoneOff, Video, VideoOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Hint } from "@/components/ui/hint";
import { cn } from "@/lib/utils";
import { useCallStore } from "../store";

function StreamVideo({ stream, muted, className }: { stream: MediaStream | null; muted?: boolean; className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.srcObject = stream;
  }, [stream]);
  return <video ref={ref} autoPlay playsInline muted={muted} className={className} />;
}

/** Hiện ở mọi màn có thể nhận/gọi cuộc gọi (chat bệnh nhân, màn bác sĩ). */
export function CallOverlay() {
  const phase = useCallStore((s) => s.phase);
  const localStream = useCallStore((s) => s.localStream);
  const remoteStream = useCallStore((s) => s.remoteStream);
  const micOn = useCallStore((s) => s.micOn);
  const camOn = useCallStore((s) => s.camOn);
  const minimized = useCallStore((s) => s.minimized);
  const remoteMedia = useCallStore((s) => s.remoteMedia);
  const endCall = useCallStore((s) => s.endCall);
  const toggleMic = useCallStore((s) => s.toggleMic);
  const toggleCamera = useCallStore((s) => s.toggleCamera);
  const setMinimized = useCallStore((s) => s.setMinimized);
  const mode = useCallStore((s) => s.mode);
  const acceptCall = useCallStore((s) => s.acceptCall);

  // vị trí cửa sổ thu nhỏ do người dùng kéo; null = vị trí mặc định (góc phải, dưới header)
  const rootRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);

  const onDragStart = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!minimized || !rootRef.current || (e.target as HTMLElement).closest("button")) return;
    const r = rootRef.current.getBoundingClientRect();
    dragRef.current = { dx: e.clientX - r.left, dy: e.clientY - r.top };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onDragMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || !rootRef.current) return;
    const { width, height } = rootRef.current.getBoundingClientRect();
    setPos({
      x: Math.min(Math.max(0, e.clientX - drag.dx), window.innerWidth - width),
      y: Math.min(Math.max(0, e.clientY - drag.dy), window.innerHeight - height),
    });
  };
  const onDragEnd = () => {
    dragRef.current = null;
  };

  if (phase === "idle") return null;

  if (phase === "ringing_in" || phase === "ringing_out") {
    const incoming = phase === "ringing_in";
    return (
      <div
        role="alertdialog"
        aria-label={incoming ? "Cuộc gọi đến" : "Đang gọi"}
        // không có lớp nền chắn: các phần còn lại của trang vẫn thao tác được khi đang đổ chuông
        className="fixed right-4 top-16 z-50 flex w-72 max-w-[calc(100vw-2rem)] flex-col gap-3 rounded-2xl border border-border bg-card p-4 shadow-xl"
      >
        <div className="flex items-center gap-3">
          <span className="relative flex size-10 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-600">
            <span className="absolute inset-0 animate-ping rounded-full bg-emerald-500/20" />
            {mode === "video" ? <Video className="size-5" /> : <Phone className="size-5" />}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">{incoming ? "Bác sĩ đang gọi" : "Đang gọi bệnh nhân…"}</p>
            <p className="text-xs text-muted-foreground">{mode === "video" ? "Cuộc gọi video" : "Cuộc gọi thoại"}</p>
          </div>
        </div>
        <div className="flex gap-2">
          {incoming && (
            <Button className="flex-1 gap-1.5 bg-emerald-600 text-white hover:bg-emerald-700" onClick={() => void acceptCall()}>
              <Phone className="size-4" /> Chấp nhận
            </Button>
          )}
          <Button variant="destructive" className="flex-1 gap-1.5" onClick={() => void endCall()}>
            <PhoneOff className="size-4" /> {incoming ? "Từ chối" : "Huỷ"}
          </Button>
        </div>
      </div>
    );
  }

  const showRemoteVideo = remoteMedia.video;
  const btn = minimized ? "iconSm" : "icon";

  // Cùng một cây phần tử cho cả hai chế độ (chỉ đổi class) để thẻ <video> không bị mount lại, tiếng không bị ngắt khi thu nhỏ/phóng to.
  return (
    <div
      ref={rootRef}
      role="dialog"
      aria-label="Cuộc gọi"
      style={minimized && pos ? { left: pos.x, top: pos.y } : undefined}
      className={cn(
        "fixed z-50 flex flex-col bg-black text-white",
        minimized
          ? cn("w-64 overflow-hidden rounded-2xl border border-white/15 shadow-2xl sm:w-72", !pos && "right-4 top-16")
          : "inset-0"
      )}
    >
      <div
        onPointerDown={onDragStart}
        onPointerMove={onDragMove}
        onPointerUp={onDragEnd}
        onPointerCancel={onDragEnd}
        className={cn(
          "relative flex items-center justify-center overflow-hidden",
          minimized ? "h-36 cursor-grab touch-none select-none active:cursor-grabbing" : "flex-1"
        )}
      >
        {/* luôn render để phát tiếng; ẩn hình khi bên kia tắt camera */}
        <StreamVideo
          stream={remoteStream}
          className={cn("h-full w-full", minimized ? "object-cover" : "object-contain", !showRemoteVideo && "hidden")}
        />
        {!showRemoteVideo && (
          <div className="flex flex-col items-center gap-2 text-white/70">
            <span className={cn("flex items-center justify-center rounded-full bg-white/10", minimized ? "size-12" : "size-24")}>
              <Phone className={minimized ? "size-5" : "size-10"} />
            </span>
            <p className="text-xs sm:text-sm">{phase === "connecting" ? "Đang kết nối…" : "Đang thoại"}</p>
          </div>
        )}
        {!remoteMedia.audio && phase === "connected" && (
          <span className="absolute left-2 top-2 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-xs">
            <MicOff className="size-3.5" /> {minimized ? "Tắt mic" : "Bên kia đã tắt mic"}
          </span>
        )}
        {camOn && (
          <StreamVideo
            stream={localStream}
            muted
            className={cn(
              "absolute -scale-x-100 rounded-lg border border-white/20 bg-black object-cover",
              minimized ? "bottom-2 right-2 aspect-video w-20" : "bottom-4 right-4 aspect-video w-32 sm:w-48"
            )}
          />
        )}
        <Hint content={minimized ? "Phóng to toàn màn hình." : "Thu nhỏ để thao tác phần khác; cuộc gọi vẫn tiếp tục."} side="bottom">
          <Button
            variant="secondary"
            size="iconSm"
            aria-label={minimized ? "Phóng to" : "Thu nhỏ"}
            onClick={() => setMinimized(!minimized)}
            className="absolute right-2 top-2 rounded-full bg-black/50 text-white hover:bg-black/70"
          >
            {minimized ? <Maximize2 className="size-4" /> : <Minimize2 className="size-4" />}
          </Button>
        </Hint>
      </div>

      <div className={cn("flex items-center justify-center border-t border-white/10 bg-black/80", minimized ? "gap-2 p-2" : "gap-3 p-4")}>
        <Hint content={micOn ? "Tắt mic của bạn." : "Bật lại mic."}>
          <Button variant="secondary" size={btn} aria-label={micOn ? "Tắt mic" : "Bật mic"} onClick={toggleMic} className="rounded-full">
            {micOn ? <Mic className="size-4" /> : <MicOff className="size-4 text-destructive" />}
          </Button>
        </Hint>
        <Hint content={camOn ? "Tắt camera." : "Bật camera; nếu đang gọi thoại sẽ nâng cấp thành video."}>
          <Button
            variant="secondary"
            size={btn}
            aria-label={camOn ? "Tắt camera" : "Bật camera"}
            onClick={() => void toggleCamera()}
            className="rounded-full"
          >
            {camOn ? <Video className="size-4" /> : <VideoOff className="size-4 text-destructive" />}
          </Button>
        </Hint>
        <Hint content="Kết thúc cuộc gọi.">
          <Button variant="destructive" size={btn} aria-label="Kết thúc" onClick={() => void endCall()} className="rounded-full">
            <PhoneOff className="size-4" />
          </Button>
        </Hint>
      </div>
    </div>
  );
}
