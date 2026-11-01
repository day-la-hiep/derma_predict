# [Lưu ý] Route của khu bác sĩ

URL quyết định ca tư vấn hoặc báo cáo đang mở, nên tải lại trang hay mở link vẫn đúng chỗ (cùng ý với [chat-routes.md](chat-routes.md)).

| Đường dẫn | Ý nghĩa |
|---|---|
| `/doctor/<sessionId>` | một ca tư vấn (danh sách ca, hội thoại, báo cáo AI) |
| `/doctor` | cổng vào: mở ca đã nhớ, không có thì ca đầu theo bộ lọc trạng thái |
| `/doctor/records/<reportId>` | một báo cáo kết luận trong Lịch sử khám |
| `/doctor/records` | Lịch sử khám, hiện báo cáo mới nhất sau bộ lọc |

"Mở ca gốc" ở báo cáo trỏ thẳng tới `/doctor/<sessionId>` (thay cho `/doctor?session=`, link cũ không còn hiệu lực).

## Điểm cần lưu ý

- **Ca gần nhất nhớ theo trình duyệt** (`derma-doctor-prefs`), không theo tài khoản.
- **Hai route group chứa màn hình, không có trong URL.** `app/doctor/(consult)/layout.tsx` vẽ `DoctorConsultationPage` và
  `app/doctor/records/layout.tsx` vẽ `MedicalHistoryPage`; các page chỉ trả `null`. Vẽ trong page thì Next dựng lại component mỗi
  lần đổi đường dẫn (đóng/mở lại SSE, mất bộ lọc). `records` là segment tĩnh nên không bị `[sessionId]` nuốt.
- **`loaded` trong `useDoctorStore`:** URL chỉ được áp vào store sau khi danh sách ca đã tải. Rời màn thì `dispose()` đặt lại
  `loaded` và `activeSessionId` vì room SSE đã đóng, quay lại phải mở lại room.
- **Id ca không tồn tại** (hoặc không thuộc bác sĩ này) thì quay về `/doctor` để chọn lại. Ở dev, bước chuyển này có thể mất
  vài giây ở lần đầu vì Next compile trang theo yêu cầu.
- **Báo cáo trên URL luôn hiện** kể cả khi bộ lọc thời gian / khẩn cấp đang loại nó.
