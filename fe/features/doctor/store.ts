"use client";

import { create } from "zustand";
import { toast } from "sonner";
import type {
  ConsultationSession,
  ConsultationStatus,
  DoctorViewMessage,
} from "./types";
import { endpoints } from "@/services/endpoints";
import { subscribeSse } from "@/services/sse";
import { doctorApi, adaptSession, errorMessage } from "./api";

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

interface DoctorConsultationState {
  /** Danh sách phiên tư vấn */
  sessions: ConsultationSession[];
  /** ID phiên đang xem */
  activeSessionId: string | null;
  /** Tin nhắn của cuộc hội thoại đang xem */
  messages: DoctorViewMessage[];
  /** Đang tải danh sách */
  loading: boolean;
  /** Đã tải xong danh sách ít nhất một lần (từ lúc vào màn này) */
  loaded: boolean;
  /** Đang tải tin nhắn */
  loadingMessages: boolean;
  /** Đang thực hiện hành động (nhận ca / đóng ca) */
  actionLoading: boolean;
  /** Filter theo status */
  statusFilter: ConsultationStatus | "all";

  /** Khởi tạo — load danh sách phiên và nghe ca mới; ca đang mở do URL (/doctor/<id>) quyết định, không tự chọn */
  init: () => Promise<void>;
  /** Rời màn hình — đóng các SSE */
  dispose: () => void;
  /** Chọn phiên tư vấn */
  selectSession: (sessionId: string) => Promise<void>;
  /** Đổi filter status */
  setStatusFilter: (status: ConsultationStatus | "all") => void;
  /** Bác sĩ nhận ca */
  acceptSession: (sessionId: string) => Promise<void>;
  /** Bác sĩ đóng ca */
  resolveSession: (sessionId: string) => Promise<void>;
  /** Cập nhật trạng thái sau khi chốt báo cáo kết luận (server đã đóng ca trong cùng request) */
  markSessionResolved: (sessionId: string) => void;
  /** Bác sĩ gửi tin nhắn phản hồi bệnh nhân */
  sendMessage: (content: string) => Promise<void>;
}

let closeInbox: (() => void) | null = null;
let closeRoom: (() => void) | null = null;

function upsertSession(list: ConsultationSession[], next: ConsultationSession): ConsultationSession[] {
  const exists = list.some((s) => s.id === next.id);
  return exists ? list.map((s) => (s.id === next.id ? next : s)) : [next, ...list];
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

export const useDoctorStore = create<DoctorConsultationState>((set, get) => {
  function appendMessage(message: DoctorViewMessage) {
    set((s) => (s.messages.some((m) => m.id === message.id) ? s : { messages: [...s.messages, message] }));
  }

  function patchMessage(id: string, patch: (m: DoctorViewMessage) => DoctorViewMessage) {
    set((s) => ({ messages: s.messages.map((m) => (m.id === id ? patch(m) : m)) }));
  }

  // Event của room: tin người + stream của AI. Bác sĩ bỏ qua reasoning/tool/câu hỏi vì chỉ bệnh nhân trả lời được.
  function handleRoomEvent(conversationId: string, raw: Record<string, unknown>) {
    switch (raw.type) {
      case "message.created": {
        appendMessage(doctorApi.adaptRoomMessage(raw.message, conversationId));
        break;
      }
      case "message.started": {
        const id = str(raw.message_id);
        if (!id) break;
        appendMessage({
          id,
          conversationId,
          sender: "ai",
          messageType: "text",
          content: "",
          createdAt: new Date().toISOString(),
        });
        break;
      }
      case "message.delta": {
        const id = str(raw.message_id);
        const delta = str(raw.delta);
        if (id && delta) patchMessage(id, (m) => ({ ...m, content: m.content + delta }));
        break;
      }
      case "message.done": {
        const id = str(raw.message_id);
        const content = str(raw.content);
        if (!id || !content) break;
        const sender = raw.sender === "doctor" ? "doctor" : "ai";
        appendMessage({
          id,
          conversationId,
          sender,
          messageType: "text",
          content,
          createdAt: new Date().toISOString(),
        });
        patchMessage(id, (m) => ({ ...m, content }));
        break;
      }
      case "consultation.updated": {
        const sessionId = str(raw.session_id);
        const status = raw.status as ConsultationStatus;
        const doctorId = typeof raw.doctor_id === "string" ? raw.doctor_id : null;
        set((s) => ({
          sessions: s.sessions.map((sess) =>
            sess.id === sessionId ? { ...sess, status, doctorId } : sess
          ),
        }));
        break;
      }
    }
  }

  function openRoom(conversationId: string) {
    closeRoom?.();
    if (USE_MOCK) return;
    closeRoom = subscribeSse(endpoints.streamMessage(conversationId), {
      onData: (raw) => handleRoomEvent(conversationId, raw),
      onOpen: (reconnected) => {
        // Pub/Sub không replay: nối lại thì kéo lại lịch sử để không lỡ tin
        if (!reconnected) return;
        void doctorApi
          .getMessages(conversationId)
          .then((messages) => {
            if (get().sessions.find((s) => s.id === get().activeSessionId)?.conversationId === conversationId) {
              set({ messages });
            }
          })
          .catch(() => undefined);
      },
    });
  }

  function openInbox() {
    closeInbox?.();
    if (USE_MOCK) return;
    closeInbox = subscribeSse(endpoints.doctorConsultationsStream, {
      onData: (raw) => {
        if (raw.type !== "consultation.updated" || !raw.session) return;
        const session = adaptSession(raw.session);
        set((s) => ({ sessions: upsertSession(s.sessions, session) }));
      },
      onOpen: (reconnected) => {
        if (!reconnected) return;
        void doctorApi
          .listSessions()
          .then((sessions) => set({ sessions }))
          .catch(() => undefined);
      },
    });
  }

  return {
    sessions: [],
    activeSessionId: null,
    messages: [],
    loading: false,
    loaded: false,
    loadingMessages: false,
    actionLoading: false,
    statusFilter: "all",

    async init() {
      set({ loading: true });
      try {
        const sessions = await doctorApi.listSessions();
        set({ sessions, loading: false, loaded: true });
        openInbox();
      } catch (e) {
        set({ loading: false });
        toast.error(errorMessage(e));
      }
    },

    dispose() {
      closeInbox?.();
      closeRoom?.();
      closeInbox = null;
      closeRoom = null;
      // room đã đóng: quay lại màn này phải chọn lại ca (mở lại room) theo URL
      set({ loaded: false, activeSessionId: null, messages: [] });
    },

    async selectSession(sessionId) {
      set({ activeSessionId: sessionId, loadingMessages: true });
      const session = get().sessions.find((s) => s.id === sessionId);
      if (!session) {
        set({ loadingMessages: false, messages: [] });
        return;
      }
      openRoom(session.conversationId);
      try {
        const messages = await doctorApi.getMessages(session.conversationId);
        // giữ tin room đã tới trong lúc tải lịch sử
        set((s) => {
          const known = new Set(messages.map((m) => m.id));
          const live = s.messages.filter(
            (m) => m.conversationId === session.conversationId && !known.has(m.id)
          );
          return { messages: [...messages, ...live], loadingMessages: false };
        });
      } catch (e) {
        set({ loadingMessages: false });
        toast.error(errorMessage(e));
      }
    },

    setStatusFilter(status) {
      set({ statusFilter: status });
    },

    async acceptSession(sessionId) {
      set({ actionLoading: true });
      try {
        const updated = await doctorApi.acceptSession(sessionId);
        set((s) => ({
          sessions: updated ? upsertSession(s.sessions, updated) : s.sessions,
          actionLoading: false,
        }));
        toast.success("Đã tiếp quản ca tư vấn thành công");
      } catch (e) {
        set({ actionLoading: false });
        toast.error(errorMessage(e));
      }
    },

    async resolveSession(sessionId) {
      set({ actionLoading: true });
      try {
        const updated = await doctorApi.resolveSession(sessionId);
        set((s) => ({
          sessions: updated ? upsertSession(s.sessions, updated) : s.sessions,
          actionLoading: false,
        }));
        toast.success("Đã đóng phiên tư vấn");
      } catch (e) {
        set({ actionLoading: false });
        toast.error(errorMessage(e));
      }
    },

    markSessionResolved(sessionId) {
      set((s) => ({
        sessions: s.sessions.map((sess) =>
          sess.id === sessionId
            ? { ...sess, status: "resolved" as ConsultationStatus, resolvedAt: new Date().toISOString() }
            : sess
        ),
      }));
    },

    async sendMessage(content) {
      const trimmed = content.trim();
      if (!trimmed) return;

      const { activeSessionId, sessions } = get();
      const session = sessions.find((s) => s.id === activeSessionId);
      if (!session || session.status === "resolved") return;

      try {
        const sent = await doctorApi.sendDoctorMessage(session.id, session.conversationId, trimmed);
        appendMessage(sent);
        // gửi tin = tự nhận ca; trạng thái chính thức đến từ event consultation.updated của room
      } catch (e) {
        toast.error(errorMessage(e));
      }
    },
  };
});
