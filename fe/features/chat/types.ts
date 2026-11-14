export type ChatRole = "user" | "assistant" | "doctor";

export type MessageStatus =
  | "pending"
  | "streaming"
  | "done"
  | "queued";

export type ReasoningStepStatus = "processing" | "done";

export type ReasoningStepType = "default" | "tool" | "thinking";

/** Một bước trong chuỗi suy luận của AI */
export interface ReasoningStep {
  id: string;
  /** tiêu đề ngắn gọn của bước, hiển thị khi thu gọn */
  title: string;
  /** nội dung chi tiết, được stream từng token khi mở rộng (output của tool nếu type là tool) */
  content: string;
  /** Tham số đầu vào khi gọi tool (nếu type là tool) */
  input?: unknown;
  status: ReasoningStepStatus;
  /** Loại bước suy luận: default (thông thường), tool hoặc thinking */
  type?: ReasoningStepType;
}

/** `id` là id tạm phía client, sau `POST /uploads` được thay bằng object key MinIO thật. */
export interface FileAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
  url?: string;
  /** true khi đã upload xong lên backend — gửi tin nhắn trước khi upload xong sẽ chặn UI */
  uploaded?: boolean;
}

/** Văn bản soạn sẵn (document) kèm theo tin nhắn assistant, có thể chỉnh sửa */
export interface ComposedDocument {
  id: string;
  title: string;
  /** nội dung dạng HTML để chỉnh sửa bằng OnlyOffice */
  content: string;
  /** đánh dấu block đã được mở/chỉnh sửa như một canvas */
  isCanvas?: boolean;
}

export interface ChatMessage {
  id: string;
  conversationId: string;
  role: ChatRole;
  content: string;
  /** Chuỗi các bước lý luận của AI, hiển thị theo danh sách */
  reasoning?: ReasoningStep[];
  /** văn bản soạn sẵn kèm tin assistant, có thể chỉnh sửa (canvas) */
  document?: ComposedDocument;
  /** tệp đính kèm (chủ yếu cho tin nhắn của user) */
  attachments?: FileAttachment[];
  createdAt: string;
  status: MessageStatus;
  /** `consultation_*` = tin mốc đầu/cuối phiên bác sĩ, hiện thành đường chia thay vì bubble */
  messageType?: string;
}

export interface Conversation {
  id: string;
  patientProfileId?: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export type MessageStatusType =
  | "message.started"
  | "message.delta"
  | "message.done";

export type ReasoningStatusType =
  | "reasoning.step_started"
  | "reasoning.step_completed"
  | "reasoning_step_delta";

export interface ToolMetadata {
  name: string;
}

export interface MessageMetadata {
  status: MessageStatusType;
  content: string;
}

export interface ReasoningMetadata {
  status: ReasoningStatusType;
  title: string;
  content: string;
  toolMetadata?: ToolMetadata;
  stepId?: string;
  stepType?: "default" | "tool_call";
}

export interface ConversationStreamEvent {
  corr_id?: string | null;
  message_id?: string | null;
  conversation_id: string;
  metadata: MessageMetadata | ReasoningMetadata;
}

export type FlatStreamEvent =
  | {
      type: "message.started";
      corrId: string;
      clientMessageId?: string;
      conversationId: string;
      messageId: string;
    }
  | {
      type: "reasoning.step_started";
      messageId: string;
      conversationId: string;
      stepId: string;
      title: string;
      stepType?: "default" | "tool_call";
        }
  | {
      type: "reasoning.step_delta";
      messageId: string;
      conversationId: string;
      stepId: string;
      delta: string;
    }
  | {
      type: "reasoning.step_completed";
      messageId: string;
      conversationId: string;
      stepId: string;
      stepType?: "default" | "tool_call";
        }
  | {
      type: "message.delta";
      messageId: string;
      conversationId: string;
      delta: string;
    }
  | {
      type: "message.done";
      messageId: string;
      conversationId: string;
      /** Backend thật (`core/app/agent/worker.py`) gửi content cuối cùng ở đây — mock
       * (`services/mock/mockChatService.ts`) không gửi field này, dựa vào content đã
       * tích luỹ qua `message.delta` + `reasoning` bên dưới thay vào đó. */
      content?: string;
      reasoning?: ReasoningStep[];
    }
  /** Tin của bệnh nhân/bác sĩ đã ghi DB (room). `message` là `ApiChatMessage` snake_case, chuyển bằng `toChatMessage`. */
  | {
      type: "message.created";
      conversationId: string;
      message: unknown;
    }
  /** Tool bắt đầu chạy; `stepId` trùng với `message.tool_result` sau đó để cùng một bước. */
  | {
      type: "message.tool_start";
      messageId: string;
      conversationId: string;
      stepId?: string;
      tool: string;
      input?: unknown;
    }
  /** Kết quả 1 tool nghiệp vụ (không phải `ask_user`) vừa chạy xong — chỉ backend thật
   * gửi (`core/app/agent/graph.py::_emit_tool_result`), hiển thị như 1 bước trong
   * `ReasoningSection`. */
  | {
      type: "message.tool_result";
      messageId: string;
      conversationId: string;
      stepId?: string;
      tool: string;
      input?: unknown;
      content: string;
    }
  /** Một bước suy luận mỗi lần LLM được gọi; gửi nguyên khối, mỗi event là bước mới. */
  | {
      type: "message.thinking";
      messageId: string;
      conversationId: string;
      content: string;
    }
  | {
      type: "document.started";
      messageId: string;
      conversationId: string;
      documentId: string;
      title: string;
    }
  | {
      type: "document.delta";
      messageId: string;
      conversationId: string;
      documentId: string;
      delta: string;
    }
  | {
      type: "document.done";
      messageId: string;
      conversationId: string;
      documentId: string;
      document?: ComposedDocument;
    };

/**
 * Các sự kiện stream từ backend (SSE — server push qua POST response).
 */
export type ChatStreamEvent = ConversationStreamEvent | FlatStreamEvent;

export interface CreateConversationInput {
  userId: string;
  /** tin nhắn đầu tiên — cùng tên `Message.content` ở base */
  content: string;
  title?: string;
  /** hồ sơ bệnh nhân của hội thoại; bỏ trống = backend dùng hồ sơ tạo sớm nhất */
  patientProfileId?: string | null;
}

/** Input nội bộ store → chatService. Adapter (services/apiAdapters.ts) map sang wire body. */
export interface SendMessageInput {
  conversationId: string;
  corrId: string;
  clientMessageId?: string;
  content: string;
  modelId?: string;
  attachments?: FileAttachment[];
}

/** Kết quả `POST /conversations/{id}/messages` — Core trả về CẢ user message vừa lưu
 * lẫn row assistant tạo sẵn (`status="queued"`). FE gắn `assistantMessage.id` vào bubble
 * assistant rồi lắng nghe SSE theo id đó (không cần chờ `message.started`). */
export interface SendMessageResult {
  userMessage: ChatMessage;
  /** null khi bác sĩ đang phụ trách ca: AI không tạo turn */
  assistantMessage: ChatMessage | null;
}

export interface ChatService {
  connect(): Promise<void>;
  disconnect(): void;
  getConversations(): Promise<Conversation[]>;
  getMessages(conversationId: string): Promise<ChatMessage[]>;
  createConversation(input?: Partial<CreateConversationInput> | string): Promise<Conversation>;
  sendMessage(input: SendMessageInput): Promise<SendMessageResult | void> | void;
  /** Dừng turn đang chạy; kết quả về qua `message.done`. Bản mock không có. */
  cancelTurn?(conversationId: string): Promise<void>;
  updateDocument(input: {
    messageId: string;
    content: string;
    isCanvas?: boolean;
  }): Promise<void> | void;
  onEvent(listener: (event: ChatStreamEvent) => void): () => void;
  improvePrompt(prompt: string): Promise<string>;
  /** Upload 1 file lên backend TRƯỚC khi gửi tin nhắn — trả về `FileAttachment` với
   * `id` = object key thật (backend dùng để đọc lại file cho Agent) và `url` preview. */
  uploadAttachment(file: File): Promise<FileAttachment>;
  /** Mở room (SSE dài hạn) của hội thoại; bản mock không có. */
  openRoom?(conversationId: string): void;
  /** Gọi khi room nối lại sau khi đứt — nơi refetch tin nhắn bị lỡ. */
  onRoomReconnect?(listener: (conversationId: string) => void): () => void;
}
