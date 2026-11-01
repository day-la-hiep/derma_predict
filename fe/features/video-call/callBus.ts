import type { CallEvent } from "./types";

type Listener = (event: CallEvent) => void;
const listeners = new Set<Listener>();

/** Cầu nối event `call.*` từ SSE cuộc gọi của tài khoản (`CallLayer`) sang store cuộc gọi. */
export function onCallEvent(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Trả true nếu là event cuộc gọi (người gọi bỏ qua không xử lý tiếp). */
export function dispatchCallEvent(raw: Record<string, unknown>): boolean {
  if (typeof raw.type !== "string" || !raw.type.startsWith("call.")) return false;
  listeners.forEach((l) => l(raw as unknown as CallEvent));
  return true;
}
