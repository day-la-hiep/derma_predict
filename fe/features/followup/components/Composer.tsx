"use client";

import { useEffect, useRef, useState } from "react";
import { ImagePlus, Loader2, SendHorizontal, X } from "lucide-react";
import { toast } from "sonner";
import { Hint } from "@/components/ui/hint";
import { cn } from "@/lib/utils";
import { errorMessage, followupApi, type UploadedImage } from "../api";

const MAX_IMAGES = 4;
const MAX_BYTES = 10 * 1024 * 1024; // khớp giới hạn của POST /uploads
const IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"];

interface Attachment {
  id: string;
  preview: string;
  status: "uploading" | "done" | "error";
  uploaded?: UploadedImage;
}

export function Composer({
  role,
  sending,
  onSend,
}: {
  role: "patient" | "doctor";
  sending: boolean;
  // trả false khi gửi lỗi để composer giữ nguyên nội dung
  onSend: (content: string, files: UploadedImage[]) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [items, setItems] = useState<Attachment[]>([]);
  const [dragging, setDragging] = useState(false);
  const areaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);

  // ô nhập tự cao theo nội dung, tối đa 6 dòng rồi cuộn trong ô
  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 144)}px`;
  }, [text]);

  useEffect(() => () => itemsRef.current.forEach((i) => URL.revokeObjectURL(i.preview)), []);

  const uploading = items.some((i) => i.status === "uploading");
  const ready = items.filter((i) => i.status === "done");
  const canSend = (text.trim().length > 0 || ready.length > 0) && !uploading && !sending;

  const addFiles = (files: File[]) => {
    const images = files.filter((f) => IMAGE_TYPES.includes(f.type));
    if (images.length < files.length) toast.error("Chỉ gửi được ảnh JPG, PNG hoặc WebP.");
    for (const file of images.slice(0, Math.max(0, MAX_IMAGES - itemsRef.current.length))) {
      if (file.size > MAX_BYTES) {
        toast.error(`${file.name} vượt quá 10MB.`);
        continue;
      }
      const id = crypto.randomUUID();
      setItems((prev) => [...prev, { id, preview: URL.createObjectURL(file), status: "uploading" }]);
      followupApi
        .upload(file)
        .then((uploaded) => setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status: "done", uploaded } : i))))
        .catch((e) => {
          toast.error(errorMessage(e));
          setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status: "error" } : i)));
        });
    }
    if (images.length > MAX_IMAGES - itemsRef.current.length) toast.error(`Tối đa ${MAX_IMAGES} ảnh mỗi tin.`);
  };

  const remove = (id: string) =>
    setItems((prev) => {
      const gone = prev.find((i) => i.id === id);
      if (gone) URL.revokeObjectURL(gone.preview);
      return prev.filter((i) => i.id !== id);
    });

  const submit = async () => {
    if (!canSend) return;
    const content = text.trim();
    const files = ready.map((i) => i.uploaded!);
    if (await onSend(content, files)) {
      items.forEach((i) => URL.revokeObjectURL(i.preview));
      setText("");
      setItems([]);
    }
  };

  return (
    <div
      className="shrink-0 border-t border-border bg-background px-3 pb-4 pt-3"
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        addFiles([...e.dataTransfer.files]);
      }}
    >
      <div
        className={cn(
          "rounded-2xl border bg-card transition-colors focus-within:border-brand/40 focus-within:ring-2 focus-within:ring-brand/10",
          dragging ? "border-brand bg-brand/5" : "border-border"
        )}
      >
        {items.length > 0 && (
          <div className="flex flex-wrap gap-2 px-3 pt-3">
            {items.map((i) => (
              <div key={i.id} className="group relative size-16 overflow-hidden rounded-xl border border-border bg-muted">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={i.preview} alt="Ảnh đính kèm" className={cn("size-full object-cover", i.status !== "done" && "opacity-50")} />
                {i.status === "uploading" && <Loader2 className="absolute inset-0 m-auto size-4 animate-spin text-foreground" />}
                {i.status === "error" && <span className="absolute inset-x-0 bottom-0 bg-destructive/90 py-0.5 text-center text-[10px] text-white">Lỗi</span>}
                <button
                  type="button"
                  onClick={() => remove(i.id)}
                  aria-label="Bỏ ảnh"
                  className="absolute right-0.5 top-0.5 flex size-5 items-center justify-center rounded-full bg-foreground/70 text-background opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <textarea
          ref={areaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void submit();
            }
          }}
          onPaste={(e) => {
            const files = [...e.clipboardData.files];
            if (files.length) {
              e.preventDefault();
              addFiles(files);
            }
          }}
          placeholder={role === "doctor" ? "Phản hồi bệnh nhân..." : "Nhắn cho bác sĩ..."}
          aria-label="Tin nhắn"
          rows={1}
          className="block max-h-36 w-full resize-none bg-transparent px-4 pb-1 pt-3 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground focus:outline-none"
        />

        <div className="flex items-center justify-between px-2 pb-2">
          <div className="flex items-center gap-0.5">
            <Hint content="Đính kèm ảnh (hoặc dán/kéo thả vào đây)">
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                disabled={items.length >= MAX_IMAGES}
                aria-label="Đính kèm ảnh"
                className="flex size-9 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
              >
                <ImagePlus className="size-[18px]" />
              </button>
            </Hint>
            <input
              ref={fileRef}
              type="file"
              accept={IMAGE_TYPES.join(",")}
              multiple
              hidden
              onChange={(e) => {
                addFiles([...(e.target.files ?? [])]);
                e.target.value = "";
              }}
            />
            <span className="ml-2 hidden text-[11px] text-muted-foreground/70 sm:inline">Enter để gửi · Shift+Enter xuống dòng</span>
          </div>

          <button
            type="button"
            onClick={() => void submit()}
            disabled={!canSend}
            aria-label="Gửi"
            className={cn(
              "flex size-10 shrink-0 items-center justify-center rounded-full transition-all active:scale-95",
              canSend ? "bg-gradient-to-br from-[var(--brand)] to-[#4D7CFF] text-brand-foreground shadow-sm hover:-translate-y-0.5 hover:shadow-md" : "cursor-not-allowed bg-muted text-muted-foreground opacity-60"
            )}
          >
            {sending ? <Loader2 className="size-4 animate-spin" /> : <SendHorizontal className="size-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}
