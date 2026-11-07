# [Pending] Tách hệ thống thành microservice theo domain

Chương 2 của báo cáo (`bao_cao_latex/chuong2`) mô tả **thiết kế đích** gồm API Gateway và các dịch vụ theo domain, mỗi dịch vụ
có CSDL riêng. Code hiện tại chưa làm vậy: Core, Agent Worker, Ingest Worker cùng một mã nguồn `core/`, dùng chung một
PostgreSQL và chỉ Core ghi vào đó. Tài liệu này ghi cách chia đang dự kiến để chốt trước khi viết chương 2.

## 1. Cách chia đề xuất (chưa chốt)

| Dịch vụ | Domain | Dữ liệu sở hữu |
|---|---|---|
| `user-service` | Tài khoản, đăng nhập, hồ sơ bệnh nhân, bác sĩ, quản trị viên | PostgreSQL (riêng) |
| `chat-service` | Hội thoại, tin nhắn, đẩy sự kiện thời gian thực | PostgreSQL (riêng), Redis |
| `agent-service` | Tác nhân lập luận, công cụ (CNN, truy xuất), bộ nhớ dài hạn | Redis (checkpoint), kho bộ nhớ |
| `appointment-service` | Yêu cầu tư vấn, lịch hẹn, cuộc gọi video, báo cáo tiền khám | PostgreSQL (riêng) |
| `record-service` | Hồ sơ bệnh án, báo cáo kết luận, ca tham khảo | PostgreSQL (riêng), Qdrant (ca bệnh) |
| `knowledge-service` | Tài liệu giáo trình, pipeline số hoá, đồ thị tri thức | PostgreSQL (riêng), MinIO, Qdrant, Neo4j |

## 2. Khác với hiện trạng

- Chưa có API Gateway; hiện giao diện gọi thẳng Core.
- Core đang gộp nhiều domain (user, conversation, appointment, doctor, document).
- Chưa tách CSDL; chưa có cơ chế gọi giữa dịch vụ ngoài RabbitMQ và Redis Pub/Sub.

## 3. Câu hỏi cần chốt

- Bao nhiêu dịch vụ là vừa (đề xuất 6, có thể gộp `record-service` vào `appointment-service`).
- Truy xuất (Qdrant, Neo4j) thuộc `knowledge-service` hay thành dịch vụ riêng.
- Chương 1 mục "Kiến trúc hệ thống" và chương 5, 6 đang mô tả hiện trạng; cần thống nhất với thiết kế đích.
