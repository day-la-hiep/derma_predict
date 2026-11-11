# [Pending] Form theo dõi sau khám (`follow_ups`, `diagnosis_revisions`)

Bước 9 của `tmp/plan/2026-11-02-luong-nghiep-vu.html` còn các phần chưa làm. Kênh chat và video đã có ([followup-channel](../notice/followup-channel.md)), nhưng:

- **`follow_ups`**: bác sĩ ghi đáp ứng điều trị (`improved` / `stable` / `worse`) và hẹn tái khám qua form trong kênh. Chưa có bảng, API, màn hình.
- **`diagnosis_revisions`**: kết quả xét nghiệm hoặc tái khám sửa chẩn đoán (lý do `lab` / `revisit` / `other`), sinh sự kiện `clinical.diagnosis_revised` để cập nhật chỉ số và re-index. Báo cáo kết luận vẫn bất biến, chưa có đường sửa.
- **Tái khám từ kênh**: nút "Đặt lịch tái khám" trong kênh theo dõi, quay lại bước đặt lịch; hiện bệnh nhân đặt lịch từ chat AI.
- **Gia hạn bằng form** hoặc tự gia hạn khi có lịch tái khám; hiện chỉ có `extend` thủ công.

Câu hỏi cần chốt: gắn `follow_ups` vào `Encounter` hay vào kênh; có cho bệnh nhân gửi ảnh tiến triển vào `patient_images` hay chỉ làm tệp đính kèm tin nhắn.
