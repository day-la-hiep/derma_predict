---
name: derma-report-writing
description: Quy ước viết báo cáo đồ án Derma Hospital trong `bao_cao_latex/` (LaTeX, tiếng Việt) với văn phong kỹ thuật, câu ngắn, ít tính từ. Dùng mỗi khi viết, sửa, rút gọn, dịch hoặc rà soát nội dung các chương, mục mở đầu, kết luận, bảng, hình, công thức của báo cáo; khi người dùng nói "viết chương", "viết mục", "sửa câu từ", "làm gọn báo cáo", "bao_cao_latex", kể cả khi không nhắc tên skill.
---

# Viết báo cáo đồ án (`bao_cao_latex/`)

Người đọc là hội đồng chấm đồ án. Họ cần biết hệ thống làm gì, bằng cách nào, kết quả ra sao. Câu dài và tính từ khen ngợi làm loãng thông tin và khó kiểm chứng, nên văn phong dưới đây ưu tiên sự kiện đo được.

## Văn phong

- **Câu ngắn:** một câu một ý, khoảng 25 từ trở xuống. Tách câu có nhiều mệnh đề nối bằng "và", "đồng thời", "nhằm".
- **Chủ ngữ rõ:** nêu thành phần thực hiện hành động (Core, Agent Worker, CNN). Tránh "được thực hiện", "được sử dụng" khi nêu được chủ thể.
- **Hạn chế tính từ và trạng từ đánh giá:** bỏ "mạnh mẽ", "hiệu quả", "linh hoạt", "toàn diện", "tối ưu", "đáng tin cậy", "thông minh", "dễ dàng", "nhanh chóng". Thay bằng sự kiện: số liệu, tên kỹ thuật, cơ chế. Tính từ mô tả kỹ thuật được giữ (đa tỷ lệ, bất đồng bộ, thưa, dư).
  - Tránh: "Hệ thống sử dụng kiến trúc linh hoạt giúp xử lý nhanh chóng."
  - Dùng: "Core đẩy yêu cầu vào RabbitMQ; Agent Worker xử lý ở tiến trình riêng nên HTTP trả về ngay."
- **Nêu lý do chọn công nghệ bằng đặc tính cụ thể:** "Qdrant lưu được vector dense và sparse trong cùng một point", không viết "Qdrant phù hợp nhất".
- **Số liệu kèm đơn vị và nguồn:** 22 lớp, 500 MB, 10 bản ghi. Số chưa có thì ghi `% TODO: bổ sung số liệu`, không tự điền.
- **Không khẳng định quá mức:** kết quả AI là giả thuyết hoặc gợi ý. Mọi đoạn nói về kết quả mô hình hay chatbot giữ nguyên ý "không phải chẩn đoán y khoa".
- **Thuật ngữ:** tiếng Việt kèm tiếng Anh trong ngoặc ở lần đầu (truy xuất tăng cường sinh văn bản (RAG)), sau đó dùng một dạng nhất quán. Tên công nghệ, hàm, bảng, endpoint giữ nguyên tiếng Anh, đặt trong `\texttt{}`.
- **Liệt kê:** dùng `itemize` khi có từ ba mục song song; mỗi mục bắt đầu bằng thành phần in đậm, sau đó là một mệnh đề. Đoạn văn dài hơn 6 câu thì tách hoặc chuyển thành bảng.
- **Không lặp:** mục kết luận chương tóm tắt một lần, không chép lại nguyên câu của các mục trước.

## Đối chiếu với code trước khi viết

Báo cáo mô tả hệ thống thật. Trước khi viết về một thành phần, đọc nguồn tương ứng:

| Chủ đề | Nguồn |
|---|---|
| Chức năng, trạng thái | `docs/overview/requirements.md` |
| Kiến trúc, thành phần | `docs/overview/system-overview.md` |
| Cơ sở dữ liệu | `docs/overview/db-tables.md`, `db-diagram.dbml` |
| Chat, agent, tool | `docs/module/chat.md` |
| Pipeline sách, đồ thị | `docs/module/book-ingest-pipeline.md`, `knowledge-graph.md` |
| Giới hạn đã biết | `docs/notice/`, `docs/pending/`, mục 7 của `CLAUDE.md` |

Tên mô hình, số lớp, tham số mà tài liệu không ghi thì hỏi người dùng hoặc đánh dấu TODO.

## Quy ước LaTeX

- Mỗi chương một thư mục `chuongN/chuongN.tex` (ảnh để trong `chuongN/hinh/`); `main.tex` nạp bằng `\input`. Mở đầu nằm ở `mo_dau/`.
- Cấu trúc `\chapter` → `\section` → `\subsection` (tự đánh số 1.1, 1.1.1). Không đánh số tay trong tiêu đề. Kết thúc chương bằng `\section{Kết luận chương}`.
- Nhãn: `\label{ch:chuongN}` cho chương; hình `fig:`, bảng `tab:`, công thức `eq:`. Tham chiếu bằng `Chương~\ref{...}`, `Hình~\ref{...}` (dấu `~` giữ liền với số).
- Bảng và hình dùng `[H]` (đã nạp gói `float`), có `\caption`; chú thích bảng đặt dưới bảng như các bảng hiện có. Hình dùng `\includegraphics[width=0.95\linewidth,height=0.7\textheight,keepaspectratio]{chuongN/hinh/...}`.
- Công thức dùng môi trường `equation` và giải thích ký hiệu ngay sau công thức ("Trong đó, ...").
- Dấu ngoặc kép tiếng Việt viết ``...'' (hai dấu huyền, hai dấu nháy đơn). Ký tự đặc biệt phải escape: `\_`, `\%`, `\&`.
- Không chỉnh gói, lề, cỡ chữ trong `main.tex` khi chỉ viết nội dung. Định dạng đã khai báo ở đó: Times New Roman 13 pt; giãn dòng 1,5 cho nội dung; giãn đoạn trước 0 pt, sau 6 pt; giãn dòng đơn cho bảng (kể cả `longtable`), chú thích hình/bảng, trích dẫn khối và tài liệu tham khảo. Tiêu đề chương là `\chapter[\MakeUppercase{Tên}]{Tên}` để mục lục và đầu trang in hoa.
- Không commit file sinh ra khi biên dịch (`*.aux`, `*.log`, `*.synctex.gz`); `.gitignore` của thư mục đã xử lý phần lớn.

## Quy trình

1. Đọc `main.tex` và chương liên quan để khớp cấu trúc, nhãn và thuật ngữ đã dùng.
2. Đọc nguồn trong bảng trên.
3. Viết, rồi tự rà một lượt: gạch các tính từ đánh giá, tách câu dài, thay khẳng định chung bằng sự kiện.
4. Biên dịch kiểm tra: `cd bao_cao_latex && xelatex -interaction=nonstopmode -halt-on-error main.tex` (chạy hai lần nếu đổi mục lục hoặc tham chiếu). Báo lỗi nếu có; nói rõ nếu chưa xem PDF.
5. Cuối câu trả lời liệt kê các chỗ để TODO hoặc chưa đối chiếu được với code.
