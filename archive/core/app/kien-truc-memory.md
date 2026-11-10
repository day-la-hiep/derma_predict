# Memory dài hạn theo hồ sơ bệnh nhân (Postgres, cập nhật theo batch)

Xem [`kien-truc-agent.md`](./kien-truc-agent.md) cho cách agent chạy một lượt. Tài liệu này chỉ mô tả lớp memory phụ trợ nằm ngoài một lượt. Mã: `agent/tools/memory.py`.

## 1. Memory là gì
- Chuỗi chữ ngắn về thông tin **dùng lâu dài** của một bệnh nhân (tiền sử, bệnh nền, thuốc đang dùng, dị ứng, mang thai…). Không lưu triệu chứng tức thời của lần chat, lời của trợ lý hay suy đoán chẩn đoán.
- Khoá theo **hồ sơ bệnh nhân** (`patient_profile_id`, lấy từ `Conversation` trong `agent/context/builder.py`), không theo tài khoản: một tài khoản quản lý hồ sơ cho cả người nhà nên memory theo tài khoản sẽ trộn người với nhau.
- Mỗi bản ghi: `{content}`; không có vector, không có loại hay nguồn. Memory **tách biệt** với dữ kiện lâm sàng (`diag.facts` / `clinical_facts`): hai bên không đọc hay ghi chéo.

## 2. Lưu ở đâu
- `AsyncPostgresStore` (gói `langgraph-checkpoint-postgres`) trong schema riêng `langgraph` của cùng database, **không cấu hình `index`** nên không embedding, không cần pgvector. Worker mở store lúc khởi động (`agent/worker.py::main`, `agent/persistence.py::postgres_persistence()`, tự tạo bảng, dùng chung kết nối schema với checkpoint hội thoại) rồi gán vào `chat_graph.store`.
- Alembic của Core chỉ soi schema mặc định nên không đụng schema `langgraph` (`python -m alembic check` báo "No new upgrade operations detected").
- Test và `debug_app.py` dùng `InMemoryStore()` (không bền).
- **Ngoại lệ so với quy tắc "chỉ Core ghi Postgres":** worker ghi trực tiếp các bảng của store trong schema `langgraph` (trạng thái nội bộ của agent, không phải dữ liệu nghiệp vụ của Core).

Các namespace, đều theo `(patient_profile_id, …)`:

| Namespace | Nội dung |
|---|---|
| `memories` | memory đang hiệu lực |
| `memory_pending` | bộ đệm tin nhắn của người dùng chờ batch (`{text, conversation_id, at}`) |
| `memory_meta` | mốc `last_batch_at`, `last_consolidated_at`, `changes_since_consolidate` |
| `memories_archive` | bản sao các memory cũ trước mỗi lần gom |

## 3. Đọc
- Graph v2: node đầu `load_memory` đọc **một lần** rồi đặt chuỗi vào `AgentContext.memory_text`; `plan` / `choose_tools` / `reflect` / `answer` chỉ nối chuỗi đó vào prompt (`inject_memory`), không chạm store.
- Graph v1: middleware `inject_long_term_memory` gọi `with_memory` ở mỗi lần gọi model (một truy vấn SQL, rất rẻ vì không embedding).
- Lấy tối đa `MAX_INJECTED = 10` bản **mới cập nhật nhất**, không lọc theo độ liên quan. Người có hơn 10 bản sẽ không thấy các bản cũ hơn trong prompt.

## 4. Ghi: chạy nền, theo batch
Không còn tool `save_memory` hay node ghi trong graph. Sau khi câu trả lời đã gửi, `agent/turn.py::_schedule_memory_update` chạy `after_turn()` bằng `asyncio.create_task` nên lượt không phải chờ.

1. `after_turn` ghi tin nhắn người dùng vào bộ đệm `memory_pending` (không gọi LLM). Lần đầu thấy hồ sơ thì đặt mốc `last_batch_at = bây giờ` để batch đầu cũng đợi đủ một chu kỳ.
2. Đủ điều kiện thì chạy batch: bộ đệm có ≥ `AGENT_MEMORY_BATCH_MAX_PENDING` tin (mặc định 20), hoặc đã qua ≥ `AGENT_MEMORY_BATCH_INTERVAL_MIN` phút (mặc định 60; đặt 0 để chỉ batch theo số tin) kể từ batch trước. Không có cron: batch chỉ chạy khi hồ sơ đó có lượt mới.
3. Batch (`run_batch`): một lần gọi LLM nhận memory hiện có (nhãn M1, M2…) và toàn bộ tin trong bộ đệm, trả các thao tác `add` / `update` (ghi đè bản `target_key`, dùng khi cùng chủ đề hoặc mâu thuẫn như "đã sinh" so với "đang mang thai") / `skip`. Nhãn lạ coi là `add`. Mọi quyết định `logger.info` kèm nội dung cũ và mới. Xong thì xoá bộ đệm.
4. Lỗi LLM: ghi `logger.warning`, **giữ nguyên bộ đệm** để lần sau thử lại. Lỗi store: `logger.exception`, không làm sập worker.
5. Hai batch của cùng một hồ sơ không chạy đè nhau (khoá theo hồ sơ trong tiến trình worker).

## 5. Gom định kỳ
Chạy ngay sau một batch thành công khi: số bản ghi ≥ `AGENT_MEMORY_CONSOLIDATE_AT` (15), **hoặc** đã qua `AGENT_MEMORY_CONSOLIDATE_DAYS` ngày (7) kể từ lần gom trước và có ≥ 5 thay đổi. Một lần gọi LLM trả danh sách gọn (tối đa 10 mục: gộp trùng, bản mới thắng khi mâu thuẫn, không thêm thông tin). Trước khi thay, bản cũ được chép sang `memories_archive`; kết quả rỗng, quá 10 mục hoặc lỗi thì giữ nguyên danh sách và ghi warning.

## 6. Giới hạn đã biết
- Quyết định thêm / ghi đè / gom do LLM, có thể sai (gộp hoặc ghi đè nhầm thông tin y tế); bù bằng log và archive, chưa có giao diện khôi phục.
- Memory mới chỉ có tác dụng sau khi batch chạy, nên cuộc trò chuyện ngay sau đó có thể chưa thấy; người ngừng chat thì bộ đệm chưa được xử lý tới lượt kế.
- Tác vụ nền mất nếu worker tắt giữa lúc batch; bộ đệm vẫn còn nên batch sau xử lý lại. Khoá theo hồ sơ chỉ có hiệu lực trong một worker (nhiều worker cần khoá phân tán).
- Chưa có chính sách xoá memory, bộ đệm và archive khi xoá hồ sơ (chưa tìm thấy API xoá hồ sơ trong code); đây là dữ liệu y tế.
- **Thử với LLM thật (hồ sơ thử, Postgres thật):** batch ghi đúng thông tin dài hạn và bỏ qua triệu chứng tức thời; ghi đè khi bệnh nhân đính chính hoạt động. **Rủi ro đã thấy:** tin "em không bị dị ứng penicillin nữa, đã thử lại ổn" khiến bản "dị ứng penicillin" bị ghi đè thành "không còn dị ứng", tức dị ứng bị xoá chỉ dựa vào lời bệnh nhân. Chưa có quy tắc bảo vệ dị ứng (ví dụ chỉ chú thích "bệnh nhân báo đã hết, chưa xác nhận" thay vì xoá).
- **Chất lượng bước gom chưa được kiểm chứng:** lần thử duy nhất dùng dữ liệu tự tạo mâu thuẫn nên không đánh giá được; chưa có kiểm tra tự động chặn kết quả gom chứa thông tin không có trong danh sách cũ.
- `debug_app.py` chạy graph trực tiếp nên không chạy hook ghi memory.
