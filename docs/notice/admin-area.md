# [Lưu ý] Khu admin tách khỏi khu bác sĩ

Nhập sách (`/admin/documents`) và cấu hình đồ thị tri thức (`/admin/graph-schema`) chỉ dành cho **admin**; bác sĩ chỉ có `/doctor` (ca tư vấn, lịch sử khám).

## Quy tắc

- FE: phiên đăng nhập lưu **riêng theo khu** (`derma-auth-{patient|doctor|admin}-*` trong `localStorage`, khu suy từ đường dẫn): đăng nhập hoặc đăng xuất ở `/doctor`, `/admin`, `/chats` độc lập nhau. Mỗi khu có trang đăng nhập riêng: `/login`, `/doctor/login`, `/admin/login`. `app/access-gate.tsx` chuyển người chưa đăng nhập sang trang đăng nhập của khu (kèm `?next=` cùng khu), người đã đăng nhập mà vào trang đăng nhập thì chuyển về `next` hoặc trang chủ khu. Đăng nhập bằng tài khoản thuộc khu khác thì phiên được lưu ở khu đó và chuyển sang khu đó. Chỉ `/login` có đăng ký. Đăng xuất đưa thẳng về trang đăng nhập của khu. Trang đăng nhập nằm ngoài layout của khu nhờ route group `(portal)`.
- BE: `document_router` và `graph_schema_router` gắn `dependencies=[Depends(require_admin)]` (`app/api/deps.py`), thiếu token → 401, sai vai trò → 403.

## Điểm cần lưu ý

- **`documents.uploaded_by_id` vẫn FK tới `doctors`** (migration `83942f933af4`) và `Document.uploaded_by: Doctor` trong `dto/base`. Hiện không code nào ghi cột này, nên admin upload không lỗi; nếu muốn lưu người tải phải đổi FK sang `users` (đụng `dto/base`, cần duyệt trước).
- Admin hiện không có màn chat/tư vấn; muốn kiểm thử chat phải dùng tài khoản bệnh nhân hoặc bác sĩ.
- Test pipeline override `require_admin`, chưa có test kiểm 401/403 và chưa thử end-to-end trên trình duyệt.
