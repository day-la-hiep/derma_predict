import { api, getCurrentUserId } from "./client";
import { subscribeSse } from "./sse";
import { endpoints } from "./endpoints";
import {
  toChatMessage,
  toConversation,
  toSendMessageBody,
  toSendMessageResult,
  toStreamEvent,
  type ApiChatMessage,
  type ApiConversation,
  type ApiFileAttachment,
  toFileAttachment,
  type ApiSendMessageResult,
} from "./apiAdapters";
import type {
  AnswerQuestionInput,
  ChatService,
  ChatStreamEvent,
  CreateConversationInput,
  SendMessageInput,
  SendMessageResult,
} from "@/features/chat/types";

// Contract: core/app/api/conversation_api.py; chuyển sang kiểu UI ở `services/apiAdapters.ts`.

const impl = {
  listeners: new Set<(event: ChatStreamEvent) => void>(),

  /** SSE không cần kết nối bền; connect chỉ là để tương thích interface */
  async connect() {
    return;
  },

  disconnect() {
    impl.closeAllRooms();
  },

  async getConversations() {
    // Backend vẫn nhận `user_id` qua query (chưa đọc từ JWT), nên lấy id từ phiên đăng nhập.
    const { data } = await api.get<{ data: ApiConversation[] }>(
      endpoints.conversations,
      { params: { user_id: getCurrentUserId() } }
    );
    return data.data.map(toConversation);
  },

  async getMessages(conversationId: string) {
    const { data } = await api.get<{ data: ApiChatMessage[] }>(
      endpoints.messages(conversationId)
    );
    return data.data.map(toChatMessage);
  },

  async createConversation(input?: Partial<CreateConversationInput> | string) {
    const payload: CreateConversationInput =
      typeof input === "string"
        ? { userId: getCurrentUserId(), content: "", title: input }
        : {
            userId: input?.userId ?? getCurrentUserId(),
            content: input?.content ?? "",
            title: input?.title ?? "",
            patientProfileId: input?.patientProfileId ?? null,
          };

    const { data } = await api.post<{ data: ApiConversation }>(
      endpoints.conversations,
      {
        user_id: payload.userId,
        content: payload.content,
        title: payload.title,
        patient_profile_id: payload.patientProfileId || undefined,
      }
    );
    return toConversation(data.data);
  },

  async updateDocument({
    messageId,
    content,
    isCanvas,
  }: {
    messageId: string;
    content: string;
    isCanvas?: boolean;
  }) {
    await api.put(endpoints.document(messageId), { content, is_canvas: isCanvas });
  },

  onEvent(listener: (event: ChatStreamEvent) => void) {
    impl.listeners.add(listener);
    return () => impl.listeners.delete(listener);
  },

  rooms: new Map<string, () => void>(),
  reconnectListeners: new Set<(conversationId: string) => void>(),

  /** Mở room (SSE dài hạn) của hội thoại nếu chưa mở; Core flush turn đang chờ ngay khi subscribe xong. */
  openRoom(conversationId: string) {
    if (impl.rooms.has(conversationId)) return;
    const close = subscribeSse(endpoints.streamMessage(conversationId), {
      onData: (raw) => {
        const event = toStreamEvent(raw);
        impl.listeners.forEach((listener) => listener(event));
      },
      onOpen: (reconnected) => {
        if (reconnected) impl.reconnectListeners.forEach((l) => l(conversationId));
      },
    });
    impl.rooms.set(conversationId, close);
  },

  closeAllRooms() {
    impl.rooms.forEach((close) => close());
    impl.rooms.clear();
  },

  onRoomReconnect(listener: (conversationId: string) => void) {
    impl.reconnectListeners.add(listener);
    return () => impl.reconnectListeners.delete(listener);
  },

  async sendMessage(input: SendMessageInput): Promise<SendMessageResult> {
    const payload = toSendMessageBody(input);
    // 1. POST -> Core persist user message + tạo sẵn assistant row (status="queued"),
    //    trả về id thật cả 2. Turn CHƯA chạy (chờ SSE subscribe).
    const { data } = await api.post<{ data: ApiSendMessageResult }>(
      endpoints.sendMessage(input.conversationId),
      payload
    );
    const result = toSendMessageResult(data.data);

    // 2. Room đã mở thì Core chạy turn ngay trong POST; chưa mở thì mở ở đây để flush turn đang chờ.
    impl.openRoom(input.conversationId);

    return result;
  },

  async answerQuestion(input: AnswerQuestionInput) {
    await api.post(
      endpoints.answerQuestion(input.conversationId, input.questionId),
      {
        question_id: input.questionId,
        option_id: input.optionId,
        label: input.label,
        custom: input.custom,
      }
    );
    impl.openRoom(input.conversationId);
  },

  async improvePrompt(prompt: string) {
    const { data } = await api.post<{ data: string }>(
      endpoints.improvePrompt,
      { prompt }
    );
    return data.data;
  },

  async uploadAttachment(file: File) {
    const form = new FormData();
    form.append("file", file);
    // `Content-Type: undefined` để axios tự set `multipart/form-data; boundary=...` —
    // client mặc định (`services/client.ts`) fix cứng `application/json`.
    const { data } = await api.post<ApiFileAttachment>(
      endpoints.uploadAttachment,
      form,
      { headers: { "Content-Type": undefined } }
    );
    return toFileAttachment(data);
  },
};

export const chatSse: ChatService = impl;
