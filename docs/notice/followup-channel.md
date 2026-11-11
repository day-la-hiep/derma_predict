# [Lưu ý] Kênh theo dõi sau khám (bác sĩ ↔ bệnh nhân)

Bệnh nhân chỉ chat với chatbot trước khi khám. Chat với bác sĩ (và gọi video) chỉ có ở **kênh theo dõi** của một lần khám đã diễn ra. Code: `consultation_service` (`FollowupService`, `FollowupController`, `VideoCallService`); clinical gọi sang qua `ConsultationClient`.

## Quy tắc

- **Mỗi lần khám (`Encounter`) có tối đa 1 kênh.** Kênh là một `conversations` với `kind = doctor_followup`, `encounter_id`, `doctor_id`, `user_id` = tài khoản chủ hồ sơ. Ràng buộc DB: `encounter_id` khác NULL ⇔ kind theo dõi; `UNIQUE(encounter_id)`.
- **Mở kênh** khi bác sĩ "Bắt đầu khám" (`AppointmentService.startEncounter`, gọi sau commit). Lỗi mạng chỉ `log.warn`, khám vẫn tiến hành; kênh được tạo bù lúc chốt.
- **Hạn kênh** (`followup_until`) đặt khi chốt kết luận = chốt + `derma.followup-days` (clinical, mặc định 30). Trước khi chốt `followup_until` = NULL, kênh coi là đang mở. Lỗi gọi consultation lúc chốt chỉ `log.error`, báo cáo không rollback (kênh thiếu hạn vẫn mở; nên kiểm log).
- **Hết hạn thì chỉ đọc**: đọc tin vẫn được, gửi tin và gọi video → 409. Không có gia hạn: hết hạn rồi thì phải tái khám, tạo kênh mới.
- **Quyền**: chỉ bệnh nhân chủ kênh và bác sĩ `doctor_id` của kênh xem và gửi tin. Bác sĩ khác nhận 403 khi đọc, 404 khi gửi. Hội thoại AI (`ai_chat`) chỉ chủ sở hữu; bác sĩ **không** xem được.
- **AI im lặng** trong kênh: gửi tin chỉ ghi DB và đẩy qua SSE `/conversations/{id}/stream`, không tạo lượt AI. Người gửi (`sender`) lấy theo vai trò: `patient` hoặc `doctor`.
- **Danh sách hội thoại AI của bệnh nhân** (`GET /conversations`) lọc `kind = ai_chat` nên kênh theo dõi không lẫn vào; FE lấy kênh qua `GET /followup-channels/by-encounter/{encounterId}`.
- **Video call**: WebRTC P2P, server chỉ giữ vòng đời và relay signaling. Chỉ bác sĩ của kênh khởi tạo, kênh phải còn mở, mỗi kênh tối đa 1 cuộc gọi chưa kết thúc. Event cuộc gọi đi qua Pub/Sub `user:calls:{user_id}` (không qua stream hội thoại); chat ghi hai tin hệ thống `video_call` (bắt đầu, kết thúc). Không có timer phía server: bên gọi đóng tab giữa chừng thì cuộc gọi treo tới khi một bên kết thúc và chặn gọi mới trong kênh đó.

## Điểm cần lưu ý

- **Dữ liệu cũ giữ nguyên**: `consultation_sessions`, `pre_consultation_reports`, `video_calls.consultation_session_id`, `messages.consultation_session_id`, `finalize_reports.consultation_session_id` không bị drop. Entity phiên đã bỏ khỏi code nên các bảng đó chỉ còn để đọc/đối chiếu. `V2` điền `conversation_id` cho cuộc gọi cũ để tra cứu, nhưng chúng trỏ hội thoại AI nên không accept/end/signal được (404).
- Tin cũ của phiên tư vấn (marker, `sender = doctor`) vẫn hiện trong hội thoại AI cũ của bệnh nhân.
- **Chưa có `lab_orders`, `follow_ups`, `diagnosis_revisions`**: chưa ghi "đáp ứng điều trị" hay sửa chẩn đoán từ kênh (xem `docs/pending/followup-forms.md`).
- Không thông báo realtime khi có tin mới ngoài kênh đang mở; không đếm tin chưa đọc.
- Chưa thử end-to-end trên trình duyệt với hai tài khoản.
