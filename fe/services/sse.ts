import { clearAccessToken, getAccessToken } from "./client";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";
const RETRY_BASE_MS = 1000;
const RETRY_MAX_MS = 15000;

interface SubscribeOptions {
  onData: (data: Record<string, unknown>) => void;
  /** `reconnected=true` từ lần nối lại thứ 2 — nơi nên refetch dữ liệu (kênh Pub/Sub của hộp thư và cuộc gọi không replay). */
  onOpen?: (reconnected: boolean) => void;
}

/** SSE dài hạn qua `fetch` (để gắn được header Bearer), tự nối lại khi đứt; trả về hàm đóng. */
export function subscribeSse(path: string, { onData, onOpen }: SubscribeOptions): () => void {
  const controller = new AbortController();
  let attempt = 0;
  let opened = false;
  // id event cuối đã nhận (Redis Stream của hội thoại có `id:`): gửi lại khi nối lại để server không phát lại event cũ
  let lastEventId = "";

  const run = async () => {
    while (!controller.signal.aborted) {
      try {
        const token = getAccessToken();
        const res = await fetch(`${API_BASE}${path}`, {
          method: "GET",
          headers: {
            Accept: "text/event-stream",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}),
          },
          signal: controller.signal,
        });
        if (res.status === 401) {
          clearAccessToken();
          window.location.reload();
          return;
        }
        // 403/404: không có quyền hoặc hội thoại không còn — nối lại cũng vô ích
        if (res.status === 403 || res.status === 404) return;
        if (!res.ok || !res.body) throw new Error(`SSE thất bại: ${res.status}`);

        onOpen?.(opened);
        opened = true;
        attempt = 0;

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary: number;
          while ((boundary = buffer.indexOf("\n\n")) !== -1) {
            const rawEvent = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            for (const line of rawEvent.split("\n")) {
              if (line.startsWith("id:")) lastEventId = line.slice(3).trim();
              if (!line.startsWith("data:")) continue;
              const data = line.slice(5).trim();
              if (!data || data === "[DONE]") continue;
              try {
                onData(JSON.parse(data) as Record<string, unknown>);
              } catch {
                // frame không phải JSON thì bỏ qua
              }
            }
          }
        }
      } catch {
        if (controller.signal.aborted) return;
      }
      if (controller.signal.aborted) return;
      attempt += 1;
      const delay = Math.min(RETRY_BASE_MS * 2 ** (attempt - 1), RETRY_MAX_MS);
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  };

  void run();
  return () => controller.abort();
}
