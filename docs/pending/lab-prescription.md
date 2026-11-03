# [Pending] Xét nghiệm, đơn thuốc và mức chắc chắn chẩn đoán trong lần khám

Hoãn ở Đợt 0 (2026-11-03) để luồng chính (chat → đợt bệnh → đặt lịch → khám → chốt có mã → chỉ số AI) chạy trước. Thiết kế liên quan: `tmp/plan/2026-11-03-de-xuat-schema.html`.

## Vấn đề
- Lần khám (`encounters`) chưa ghi được xét nghiệm (sinh thiết, soi nấm KOH, cấy, patch test, máu) và đơn thuốc.
- Không phân biệt được chẩn đoán lâm sàng với chẩn đoán đã có xét nghiệm xác nhận → chỉ số AI chưa tách được "đúng so với bác sĩ" và "đúng so với kết quả xét nghiệm".

## Luồng đề xuất
1. `lab_orders` (gắn `encounter_id`): `test_type` (biopsy | koh | culture | patch_test | blood | other), `status` (ordered | resulted | cancelled), `result`, `result_file_id`, `resulted_at`. Kết quả nhập 1 lần, được nhập cả sau khi lần khám đã đóng (sinh thiết thường về sau vài ngày).
2. `prescriptions` (gắn `encounter_id`): `items` JSONB `[{drug_name, dose, frequency, duration, note}]`. Mỗi thuốc ghi thêm fact `medication` dài hạn (nhật ký nguồn `doctor`). Thuốc trùng fact `allergy` → cảnh báo, không chặn.
3. `finalize_reports.diagnosis_certainty` (clinical | lab_confirmed): `lab_confirmed` chỉ hợp lệ khi lần khám có ≥ 1 xét nghiệm đã có kết quả.
4. Kết quả xét nghiệm về sau làm đổi chẩn đoán → `diagnosis_revisions` (P6) → chỉ số tính theo mã mới nhất.

## Câu hỏi cần chốt
- Kết quả xét nghiệm có cần cấu trúc (vd KOH dương / âm) để tự động gợi ý sửa chẩn đoán, hay chỉ chữ + file?
- Đơn thuốc có cần in / xuất PDF cho bệnh nhân không?

## Phụ thuộc
- Đợt 5 (encounters + chốt kết luận có mã) đã xong.
