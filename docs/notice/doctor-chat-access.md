# [Lưu ý] Phạm vi bác sĩ xem hội thoại

Bác sĩ **không** xem hội thoại AI của bệnh nhân. Bác sĩ chỉ vào được kênh theo dõi sau khám mà mình là `doctor_id`
(logic ở `FollowupService.requireAccess`, dùng chung cho `GET /conversations/{id}/messages` và `/stream`).
Quy tắc đầy đủ: [followup-channel.md](followup-channel.md).

| Người xem | Hội thoại AI (`ai_chat`) | Kênh theo dõi (`doctor_followup`) |
|---|---|---|
| Chủ hội thoại (bệnh nhân) | xem hết | xem hết, kể cả khi đã hết hạn |
| Bác sĩ `doctor_id` của kênh | 403 | xem và gửi tin khi kênh còn mở |
| Bác sĩ/người khác | 403 | 403 (đọc), 404 (gửi) |

- Bác sĩ thấy dữ kiện lâm sàng của bệnh nhân qua lịch hẹn/lần khám (clinical), không qua chat AI.
- Phiên tư vấn cũ (`consultation_sessions`) không còn tham gia kiểm quyền; tin cũ của phiên vẫn nằm trong hội thoại AI cũ.
