# [Pending] Sinh hiệu trong lượt khám trực tiếp

Tạm hoãn khỏi đề xuất luồng khám trực tiếp (`tmp/plan/2026-11-02-*`). Các lượt khám da liễu ít khi cần sinh hiệu để tiền chẩn đoán, nên làm sau khi vòng dữ liệu chính (đặt lịch → khám → kết luận có mã → đánh giá AI) đã chạy.

## Vấn đề
Lượt khám (`encounters`) chưa ghi sinh hiệu. Vì vậy AI không biết các dấu hiệu toàn thân, ví dụ sốt kèm phát ban (cờ đỏ: nhiễm trùng, phản ứng thuốc nặng).

## Luồng đề xuất
1. Bảng `vital_signs` thuộc clinical-record, gắn `encounter_id`. Các cột: nhiệt độ, huyết áp tâm thu/tâm trương, mạch, SpO2, cân nặng, chiều cao, `measured_at`.
2. Chỉ ghi khi lượt khám đang `open`. Ghi thêm tab "Sinh hiệu" trên trang lượt khám.
3. Kiểm tra khoảng hợp lệ, ngoài khoảng thì từ chối và báo rõ lỗi. Khoảng tham khảo: nhiệt độ 34–43 °C, mạch 30–220, SpO2 50–100 %, tâm thu > tâm trương, cân nặng 1–300 kg.
4. Thêm sinh hiệu gần nhất vào `GET /internal/patients/{id}/clinical-context` để agent dùng. Có thể dùng cho cờ đỏ, ví dụ sốt.

## Câu hỏi cần chốt
- Bệnh nhân có được tự khai sinh hiệu trong chat AI không (nhiệt độ tự đo), hay chỉ bác sĩ ghi?
- Có cần quy đổi cân nặng, tuổi sang liều thuốc không? Hiện ngoài phạm vi, vì AI không kê đơn.

## Phụ thuộc
- Có `encounters` và clinical-record service (mốc M2, M4 trong plan).
