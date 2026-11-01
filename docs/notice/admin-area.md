# [Lưu ý] Khu admin tách khỏi khu bác sĩ

Nhập sách (`/admin/documents`) và cấu hình đồ thị tri thức (`/admin/graph-schema`) chỉ dành cho **admin**; bác sĩ chỉ có `/doctor` (ca tư vấn, lịch sử khám).

## Quy tắc

- FE: `app/access-gate.tsx` đưa mỗi vai trò về đúng khu (`admin → /admin`, `doctor → /doctor`); admin vào `/doctor` hoặc bác sĩ vào `/admin` đều bị chuyển đi.
- BE: `document_router` và `graph_schema_router` gắn `dependencies=[Depends(require_admin)]` (`app/api/deps.py`), thiếu token → 401, sai vai trò → 403.

## Điểm cần lưu ý

- **`documents.uploaded_by_id` vẫn FK tới `doctors`** (migration `83942f933af4`) và `Document.uploaded_by: Doctor` trong `dto/base`. Hiện không code nào ghi cột này, nên admin upload không lỗi; nếu muốn lưu người tải phải đổi FK sang `users` (đụng `dto/base`, cần duyệt trước).
- Admin hiện không có màn chat/tư vấn; muốn kiểm thử chat phải dùng tài khoản bệnh nhân hoặc bác sĩ.
- Test pipeline override `require_admin`, chưa có test kiểm 401/403 và chưa thử end-to-end trên trình duyệt.
