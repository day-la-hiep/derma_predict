# Graph theo dõi fact của bệnh nhân (namespace `Pt*` trong Neo4j)

Thiết kế: `tmp/plan/2026-11-12-tracking-fact-triple-neo4j.md` (không theo dõi git). Code: `knowledge_service/app/services/patient_fact_*.py`, `patient_graph_context_service.py`; `ai_service/app/reasoning/patient_fact_extractor.py`, `patient_fact_store.py`, `tools/query_patient_graph.py`.

## Quy tắc
- **Fact đang theo dõi nằm ở Neo4j**, tách khỏi đồ thị tri thức bằng nhãn `PtLesion`, `PtLiteral` và quan hệ `PT_*`; nút `Patient` dùng chung với journey graph (kho ca tương tự), mọi cạnh `PT_*` đều **không** mang `source` (truy vấn cạnh sách lọc `r.source = 'DOC'` nên không lọt vào đó). Neo4j Community chỉ có một database người dùng nên không tách bằng database.
- **5 nhóm** (`category` 1-5, gộp từ mẫu 14 nhóm cũ ngày 2026-11-14): 1 triệu chứng (`PT_HAS_SYMPTOM`) · 2 tổn thương (`PT_HAS_MORPHOLOGY`, `kind` primary/secondary) · 3 đặc điểm (`PT_HAS_ATTRIBUTE`, đơn trị theo `name`: `location`/`distribution`/`arrangement`/`course`/tên tự do) · 4 yếu tố tác động (có `effect` → `PT_TRIGGERED_BY`; không có → `PT_EXPOSED_TO`) · 5 tiền sử / thuốc (`PT_HAS_HISTORY` / `PT_TAKES_DRUG`). Nhóm 3 giữ một giá trị cho mỗi `name` (giá trị mới → cạnh cũ `superseded`), các nhóm còn lại nhiều giá trị (nhắc lại → cập nhật `last_confirmed_at`; "đã hết" → `resolved`). `name=location` không có cạnh, ghi vào `PtLesion.site_text`. `scope=body` (sốt, kết quả xét nghiệm) gắn thẳng `Patient`, không gắn tổn thương. **Dữ liệu ghi theo mẫu 14 nhóm cũ không tương thích**: nạp lại bằng seed (`make reseed-users`) thay vì đọc lại.
- **Phủ định**: "không ngứa" lưu `present=false` trên cạnh; khi mở rộng, bệnh thường có triệu chứng đó bị trừ 2.0 điểm (không loại hẳn).
- **Id tổn thương do ai_service tự sinh** (`uuid`); knowledge tạo tổn thương nếu chưa có, từ chối nếu id thuộc bệnh nhân khác.
- **`onset_at` do knowledge quy đổi** từ `onset_text` (`onset_resolver.py`, theo ngày của tin nguồn); không chắc ("từ nhỏ", "vài ngày") thì để trống.
- **Khớp nút lúc ghi** (`patient_fact_linker.py`): khớp tên chính xác → LLM dịch sang tên chuẩn rồi khớp chính xác → tìm ứng viên chứa tên + LLM chọn → để trống. Tối đa hai lần gọi LLM cho cả lô, chỉ khi còn nhãn chưa khớp. Không khớp thì fact giữ dạng chữ (`link_method='none'`) và không tham gia mở rộng.
- **Cạnh sách luôn dùng khi mở rộng** (`EDGE_SOURCES = ["KG", "DOC"]`, không theo `KG_EDGE_SOURCES` toàn cục mặc định `["KG"]`). Chỉ PrimeKG thì ứng viên toàn bệnh hiếm ngoài da liễu.
- **Tool `query_patient_graph`** ghi sớm fact của chính lượt này (`turn_facts_saved`) rồi mới mở rộng, vì `turn.py` chỉ ghi cuối lượt. Khoá "lệnh đã gọi" của tool này kèm dấu vết bộ fact (`STATEFUL_TOOLS`, `get_facts_fingerprint`) để không bị coi là lệnh trùng ở các lượt sau (`done_calls` lưu theo cả hội thoại).

## Điểm dễ nhầm
- **Không có transaction chung** giữa Neo4j và Postgres, và ghi graph chỉ log khi lỗi (ai_service không để mất câu trả lời): lượt ghi hỏng làm graph thiếu fact của lượt đó.
- **Ghi graph nằm trước khi trả kết quả cho consultation** (`finish_turn`); khi có nhãn chưa khớp, thêm 1-2 lần gọi LLM (vài giây) nên tin assistant `queued` lâu hơn một chút.
- **Chất lượng ứng viên bệnh phụ thuộc đồ thị thưa**: đo ngày 2026-11-12 với "ngứa + ban đỏ + mụn nước": chỉ cạnh PrimeKG → epidermolysis bullosa, Hennekam-Beemer; thêm cạnh sách → dermatitis herpetiformis, atopic dermatitis, scabies. Đồng điểm sắp xếp tuỳ ý. Kết quả chỉ là gợi ý (H#), không phải chẩn đoán.
- **Độ khớp nút** (35 nhãn tiếng Việt, một lần chạy, LLM không tất định): chỉ khớp chính xác 49% (17/35); thêm bước LLM chọn ứng viên 77% (27/35). Mọi nút khớp đều đúng nghĩa trong lần đo; khớp hụt: "rát", "khô da", "vảy tiết", "vảy da", "vết xước do gãi", "kem corticoid"... (một số lần "chàm", "bong vảy" cũng hụt). Nhóm hình thái/tổn thương thứ phát khớp kém nhất.
- **Phủ định thưa**: `DISEASE_PHENOTYPE_NEGATIVE` có 2.386 cạnh PrimeKG + 159 cạnh sách so với 300.634 + 4.012 cạnh dương, nên tác dụng trừ điểm hạn chế.

## Quy ước dữ liệu (một nguồn cho dữ kiện lâm sàng)
- **Identity (Postgres):** tài khoản, hồ sơ hành chính. **Graph theo dõi (Neo4j `Pt*`):** mọi dữ kiện lâm sàng của bệnh nhân, từ chat lẫn form hồ sơ (dị ứng/tiền sử/thuốc qua `PUT /internal/patient-facts/{id}/profile`). **Clinical (Postgres):** những gì có tính chốt: đợt, giả thuyết, ảnh, lịch hẹn, lần khám, báo cáo kết luận và **snapshot fact** lúc bác sĩ chốt. **Tri thức (Neo4j nền, Qdrant):** sách và PrimeKG, chỉ đọc.
- Một câu: dữ liệu sống nằm ở graph, dữ liệu đã chốt nằm ở Postgres dưới dạng snapshot.
- Clinical đọc fact qua `PatientFactClient` → knowledge (không cache, không lưu). Knowledge lỗi thì màn bác sĩ và chốt trả **502** thay vì hiện hồ sơ thiếu dị ứng một cách âm thầm; agent thì chạy tiếp không có fact (log cảnh báo).
- `PatientFact.id` là id cạnh trong graph (`PatientFactOutput.id`); `source_fact_id` của form chốt trỏ tới nó. Fact `resolved` (hết, hoặc bị form hồ sơ bỏ) không còn hiện.
- Màn bác sĩ không tách fact theo đợt-vùng nữa (graph không có đợt): mọi đợt của một hồ sơ hiển thị cùng bộ fact theo tổn thương của hồ sơ đó, mỗi fact kèm vị trí (`site_text`), khởi phát và `present`.

## Còn lại / đơn giản hoá có chủ ý
- Bảng `clinical_facts` / `clinical_provenances` còn trong DB nhưng không còn code dùng; chưa có migration drop (cần người dùng đồng ý trước khi xoá bảng).
- Đợt vẫn theo vùng (`clinical_episodes.body_site`) cho giả thuyết, ảnh và đặt lịch: việc "một đợt mở mỗi hồ sơ, đặt lịch theo hồ sơ" thuộc todo `tmp/plan/todo/2026-11-12-chuan-hoa-state-hoi-thoai-va-dat-lich.md`, chưa làm.
- Thẻ "Tình trạng hiện tại" của bệnh nhân chưa làm: màn bệnh nhân vẫn liệt kê theo đợt (mỗi đợt kèm các dòng fact của hồ sơ).
- Gợi ý đồ thị cho bác sĩ (`suggestions` ở form chốt) vẫn dùng `knowledge_graph_query` theo tên triệu chứng (nay ưu tiên tên chuẩn của nút đã khớp); chưa dùng `/patient-facts/{id}/context`.
- Fact bác sĩ nhập lúc chốt không vào graph nên agent chat không biết điều bác sĩ khám thấy.
