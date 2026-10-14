# [Lưu ý] Phạm vi bác sĩ xem hội thoại

Bác sĩ chỉ xem hội thoại từ đầu tới hết phiên gần nhất của mình. Logic nằm ở
`ConsultationService.room_access` (`core/app/services/consultation_service.py`), dùng chung cho
`GET /conversations/{id}/messages` và `GET /conversations/{id}/stream`. Mô tả luồng chat đầy đủ ở
[chat.md](../module/chat.md).

## Quy tắc

| Người xem | Điều kiện | Kết quả |
|---|---|---|
| Chủ hội thoại (bệnh nhân) | luôn | xem hết, không cắt |
| Bác sĩ | phiên gần nhất đang `pending`/`active` | xem từ đầu tới hiện tại, nhận stream live |
| Bác sĩ | phiên gần nhất đã `resolved` | chỉ thấy tới hết tin mốc `consultation_resolved`; stream bị từ chối (403) |
| Người khác / bác sĩ không có phiên nào | | 403 |

"Phiên gần nhất" là phiên mới nhất (theo `requested_at`) của hội thoại mà `status = pending` hoặc
`doctor_id` là bác sĩ đó.

Khi phiên kết thúc, stream của bác sĩ tự đóng ngay sau event `consultation.updated` (`status=resolved`);
tin mốc kết thúc luôn đi trước event này nên bác sĩ vẫn nhận được.

## Điểm cần lưu ý

- **Ca `pending` ai cũng xem được.** Khi phiên mới nhất đang chờ nhận, mọi bác sĩ đều xem được lịch sử tới
  hiện tại (kể cả bác sĩ đã xử lý phiên cũ), để đọc trước khi nhận ca.
- **Ca đã có bác sĩ khác nhận.** Khi ca `active` do bác sĩ A phụ trách, bác sĩ B không còn phiên nào xem được
  nên nhận 403 (trừ khi B từng xử lý một phiên khác của hội thoại, nhưng phiên đó không còn là "mới nhất").
- **Chưa cắt dữ liệu ngoài luồng chat.** `clinical_facts` và báo cáo AI trong `ConsultationSessionOutput` vẫn
  lấy theo bệnh nhân (mọi lần khám), nên bác sĩ có thể thấy dữ kiện sinh ra sau khi phiên của mình kết thúc.
  Muốn cắt thì phải gắn fact theo phiên (đổi `dto/base`, cần duyệt trước).
- **Chặn gửi tin tách riêng.** Việc bác sĩ không gửi được vào ca đã đóng nằm ở `send_doctor_reply`
  (409), không đi qua `room_access`.
- **Ca cũ không có tin mốc.** Phiên tạo trước khi có tin mốc không có `consultation_resolved`; khi đó mốc cắt
  rơi về `resolved_at` của phiên.
- **Chưa kiểm thử end-to-end** trên trình duyệt với 2 tài khoản (bệnh nhân và bác sĩ).
