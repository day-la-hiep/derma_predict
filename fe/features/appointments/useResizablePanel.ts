"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const MIN = 300;
const MAX = 720;
const KEY_WIDTH = "derma.doctor.chatWidth";
const KEY_COLLAPSED = "derma.doctor.chatCollapsed";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null; // trình duyệt chặn lưu trữ: dùng giá trị mặc định
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // không lưu được thì chỉ mất ghi nhớ giữa các lần mở
  }
}

const clamp = (w: number) => Math.min(MAX, Math.max(MIN, Math.round(w)));

// Cột dán mép phải màn hình: kéo thanh dọc để đổi bề rộng, có thể thu gọn; nhớ lựa chọn theo trình duyệt
export function useResizablePanel(defaultWidth: number) {
  const [width, setWidth] = useState(() => clamp(Number(read(KEY_WIDTH)) || defaultWidth));
  const [collapsed, setCollapsed] = useState(() => read(KEY_COLLAPSED) === "1");
  const [dragging, setDragging] = useState(false);
  const widthRef = useRef(width);

  useEffect(() => {
    widthRef.current = width;
  }, [width]);

  const toggle = useCallback(() => {
    setCollapsed((c) => {
      write(KEY_COLLAPSED, c ? "0" : "1");
      return !c;
    });
  }, []);

  // cập nhật ref ngay trong handler: lúc thả chuột effect chưa chắc đã kịp chạy nên lưu sẽ lệch một nhịp
  const resizeTo = useCallback((w: number) => {
    widthRef.current = clamp(w);
    setWidth(widthRef.current);
  }, []);

  const startDrag = useCallback(
    (e: React.PointerEvent<HTMLElement>) => {
      e.preventDefault();
      e.currentTarget.setPointerCapture(e.pointerId);
      setDragging(true);
      const move = (ev: PointerEvent) => resizeTo(window.innerWidth - ev.clientX);
      const stop = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", stop);
        window.removeEventListener("pointercancel", stop);
        setDragging(false);
        write(KEY_WIDTH, String(widthRef.current));
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", stop);
      window.addEventListener("pointercancel", stop);
    },
    [resizeTo]
  );

  const nudge = useCallback((delta: number) => {
    resizeTo(widthRef.current + delta);
    write(KEY_WIDTH, String(widthRef.current));
  }, [resizeTo]);

  const reset = useCallback(() => {
    resizeTo(defaultWidth);
    write(KEY_WIDTH, String(defaultWidth));
  }, [defaultWidth, resizeTo]);

  return { width, collapsed, dragging, toggle, startDrag, nudge, reset };
}
