"""Tên queue (RabbitMQ) và channel (Redis Pub/Sub) dùng chung toàn app."""

# ----- RabbitMQ queues -----
AGENT_REQUEST_QUEUE = "agent_request_queue"  # Backend -> Agent (yêu cầu 1 turn)
AGENT_RESPONSE_QUEUE = "agent_response_queue"  # Agent -> Backend (kết quả để persist DB)
DOCUMENT_INGEST_QUEUE = "document_ingest_queue"  # Backend -> Ingest worker (chạy 1 bước pipeline tài liệu)

# ----- Redis Pub/Sub -----
# "Room" của hội thoại: agent, bệnh nhân và bác sĩ cùng publish vào đây, mỗi bên giữ 1 SSE dài hạn tới channel này
CONVERSATION_ROOM_CHANNEL = "conversation:room:{conversation_id}"
USER_CALL_CHANNEL = "user:calls:{user_id}"  # Core -> SSE cuộc gọi của một tài khoản (không phụ thuộc đang xem hội thoại nào)
DOCTOR_INBOX_CHANNEL = "doctor:inbox"  # Core -> SSE danh sách ca của bác sĩ (ca mới / đổi trạng thái)
DOCUMENT_INGEST_CANCEL_CHANNEL = "document:ingest:cancel"  # Backend -> Ingest worker (bấm Dừng bước đang chạy)
STREAM_DONE_SENTINEL = "[DONE]"  # hết 1 turn; stream room dài hạn nên client bỏ qua, không đóng kết nối

# ----- Redis key (không phải Pub/Sub) -----
# Giá trị = messageId của turn đang chạy (kể cả đang chờ trả lời `ask_user`) — còn key thì
# `POST .../messages` trả 409 (không có Steer). Set khi mở turn, xoá khi turn message.done.
AGENT_ACTIVE_TURN_KEY = "agent:active_turn:{conversation_id}"

# Giá trị = `TurnRequest` JSON của turn/resume đã persist nhưng CHƯA đẩy vào
# `agent_request_queue` — Core hoãn publish tới khi client thực sự mở SSE (`GET
# .../stream`) để không mất event đầu luồng (Redis Pub/Sub không replay). Handler SSE
# `GETDEL` key này ngay sau khi `subscribe` xong rồi mới publish cho Worker.
# Xem docs/async-api-doc.md mục 1 + 6.
AGENT_PENDING_TURN_KEY = "agent:pending_turn:{conversation_id}"

# Cờ "đã bấm Dừng" cho bước chưa kịp được worker nhận (Pub/Sub không replay). Worker xoá khi nhận message.
DOCUMENT_CANCEL_KEY = "document:ingest:cancel:{document_id}:{stage_id}"

# ----- Database -----
# Naming convention cho constraint (index/fk/uq/ck/pk) — giúp Alembic autogenerate đặt tên nhất quán,
# tránh migration bị lệch tên constraint giữa các lần chạy.
DB_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
