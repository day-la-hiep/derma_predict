// Toàn bộ đường dẫn API.
export const endpoints = {
  conversations: "/conversations",
  messages: (conversationId: string) => `/conversations/${conversationId}/messages`,
  sendMessage: (conversationId: string) => `/conversations/${conversationId}/messages`,
  /** room của hội thoại: SSE dài hạn cho bệnh nhân, bác sĩ và agent */
  streamMessage: (conversationId: string) => `/conversations/${conversationId}/stream`,
  /** ca tư vấn mới / đổi trạng thái, cho danh sách ca của bác sĩ */
  doctorConsultationsStream: "/doctor/consultations/stream",
  /** trả lời 1 câu hỏi (`tool_ask`) agent đang chờ — KHÔNG dùng sendMessage cho việc này */
  answerQuestion: (conversationId: string, questionId: string) =>
    `/conversations/${conversationId}/questions/${questionId}/answer`,
  /** lưu văn bản soạn sẵn (canvas) của một tin nhắn */
  document: (messageId: string) => `/conversations/messages/${messageId}/document`,
  /** cải thiện prompt hiện hành */
  improvePrompt: "/conversations/improve-prompt",
  /** cuộc gọi video: tạo (bác sĩ), bắt máy, kết thúc, relay signaling WebRTC */
  startCall: (conversationId: string) => `/conversations/${conversationId}/video-calls`,
  /** SSE riêng của tài khoản: cuộc gọi đến, đổi trạng thái, signaling (không phụ thuộc hội thoại đang xem) */
  callsStream: "/video-calls/stream",
  acceptCall: (callId: string) => `/video-calls/${callId}/accept`,
  endCall: (callId: string) => `/video-calls/${callId}/end`,
  signalCall: (callId: string) => `/video-calls/${callId}/signal`,
  iceConfig: "/video-calls/ice-config",
  /** upload ảnh đính kèm — gọi TRƯỚC sendMessage, gắn response vào `attachments` */
  uploadAttachment: "/uploads",
} as const;
