-- Dữ liệu mẫu database clinical (không phải migration Flyway nên sửa tự do). Nạp bởi scripts/reseed-user-data.sh sau consultation.sql.
-- Mã hồ sơ/bác sĩ khớp seed identity (V2__seed_demo.sql); mã tin nhắn nguồn và lần khám khớp consultation.sql.
-- Các tình huống: ca đã khám (3 báo cáo, kênh theo dõi mở/hết hạn), đang khám, đã hẹn, chờ xác nhận, chưa đặt lịch, lịch bị huỷ.

-- ---------------------------------------------------------------- đợt bệnh
INSERT INTO clinical_episodes (id, patient_profile_id, body_site, status, last_conversation_id, summary, summary_at, urgency, red_flags, image_predictions, model_version, opened_at, updated_at, closed_at) VALUES
    ('seed-ep-self-face', 'pp-user-1-self', 'dau_mat', 'closed', 'seed-conv-self-face', 'Vùng Đầu, mặt: da đỏ hai bên má, tăng khi gặp nắng và đồ cay, nóng rát nhẹ, kéo dài khoảng 3 tuần. Gợi ý AI: trứng cá đỏ. Chưa có chẩn đoán của bác sĩ.', now() - interval '47 days', 'monitor', '[]', '[]', 'seed', now() - interval '47 days', now() - interval '45 days', now() - interval '45 days'),
    ('seed-ep-self-tay', 'pp-user-1-self', 'tay', 'closed', 'seed-conv-self-tay', 'Vùng Tay: mảng da khô ở khuỷu tay, ngứa nhiều về đêm khoảng hai tuần, tiền sử viêm da cơ địa, dị ứng Penicillin. Gợi ý AI: chàm thể tạng.', now() - interval '22 days', 'monitor', '[]', '[]', 'seed', now() - interval '22 days', now() - interval '20 days', now() - interval '20 days'),
    ('seed-ep-self-chan', 'pp-user-1-self', 'chan', 'open', 'seed-conv-self-chan', 'Vùng Chân: ngứa rát kèm vài mảng đỏ ở cẳng chân 4 ngày, mới đổi sữa tắm. Gợi ý AI: viêm da tiếp xúc.', now() - interval '2 days', 'monitor', '[]', '[]', 'seed', now() - interval '2 days', now() - interval '2 days', NULL),
    ('seed-ep-spouse-mat', 'pp-user-1-spouse', 'dau_mat', 'closed', 'seed-conv-spouse-mat', 'Vùng Đầu, mặt: nhiều mụn viêm ở cằm và hai má, có mụn đầu đen, đau khi chạm, nặng hơn trước kỳ kinh, kéo dài 2 tháng. Gợi ý AI: mụn trứng cá.', now() - interval '12 days', 'monitor', '[]', '[]', 'seed', now() - interval '12 days', now() - interval '10 days', now() - interval '10 days'),
    ('seed-ep-spouse-chan', 'pp-user-1-spouse', 'chan', 'open', 'seed-conv-spouse-chan', 'Vùng Chân: da cẳng chân khô, nứt nẻ, ngứa sau khi tắm. Gợi ý AI: chàm thể khô.', now() - interval '1 day', 'monitor', '[]', '[]', 'seed', now() - interval '1 day', now() - interval '1 day', NULL),
    ('seed-ep-child-tay', 'pp-user-1-child', 'tay', 'open', 'seed-conv-child-tay', 'Vùng Tay: mẩn đỏ ở cánh tay trẻ 7 tuổi, gãi nhiều, 5 ngày. Gợi ý AI: chàm hoặc côn trùng đốt.', now() - interval '3 days', 'monitor', '[]', '[]', 'seed', now() - interval '3 days', now() - interval '3 days', NULL),
    ('seed-ep-parent-face', 'pp-user-1-parent', 'dau_mat', 'in_exam', 'seed-conv-parent-face', 'Vùng Đầu, mặt: đỏ rát hai bên mũi, có vảy mỏng, hơn một tháng. Gợi ý AI: viêm da tiết bã hoặc trứng cá đỏ.', now() - interval '4 days', 'few_days', '[]', '[]', 'seed', now() - interval '4 days', now() - interval '1 hour', NULL),
    ('seed-ep-child-old', 'pp-user-1-child', 'ban_tay', 'expired', NULL, 'Vùng Bàn tay: nổi mụn nước nhỏ ở lòng bàn tay, ngứa, trẻ 7 tuổi. Đợt đã hết hạn, lịch hẹn bị huỷ.', now() - interval '60 days', 'monitor', '[]', '[]', 'seed', now() - interval '60 days', now() - interval '30 days', now() - interval '30 days');

-- ---------------------------------------------------------------- giả thuyết AI (độ tin cậy: cao | vừa | thấp)
INSERT INTO ai_hypotheses (id, episode_id, rank, diagnosis_code, disease, confidence, evidence, missing) VALUES
    ('seed-hyp-self-face-1', 'seed-ep-self-face', 1, 'Rosacea', 'Trứng cá đỏ (rosacea)', 'vừa', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Trứng cá đỏ","text":"Ban đỏ ở vùng má và mũi, tăng khi gặp nắng, nóng, đồ cay; cảm giác nóng rát."}]', '["Có mụn mủ hoặc giãn mạch hay không"]'),
    ('seed-hyp-self-face-2', 'seed-ep-self-face', 2, 'Eczema', 'Viêm da tiết bã', 'thấp', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Viêm da tiết bã","text":"Ban đỏ, vảy da dầu ở vùng mặt, hai bên cánh mũi."}]', '["Có vảy dầu ở cánh mũi hay không"]'),
    ('seed-hyp-self-tay-1', 'seed-ep-self-tay', 1, 'Eczema', 'Viêm da cơ địa (chàm thể tạng)', 'cao', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Viêm da cơ địa","text":"Ngứa nhiều về đêm, mảng da khô, lichen hoá ở nếp gấp; tiền sử cá nhân hoặc gia đình có bệnh cơ địa."}]', '[]'),
    ('seed-hyp-self-tay-2', 'seed-ep-self-tay', 2, 'Psoriasis', 'Vảy nến thể mảng', 'thấp', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Vảy nến","text":"Mảng đỏ ranh giới rõ phủ vảy trắng ở khuỷu tay, đầu gối."}]', '["Vảy trắng dày hay không","Tổn thương ở da đầu hoặc móng"]'),
    ('seed-hyp-self-chan-1', 'seed-ep-self-chan', 1, 'Eczema', 'Viêm da tiếp xúc', 'vừa', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Viêm da tiếp xúc","text":"Ngứa rát, ban đỏ xuất hiện sau tiếp xúc chất lạ như xà phòng, sữa tắm mới."}]', '["Mảng đỏ có ranh giới theo vùng tiếp xúc không"]'),
    ('seed-hyp-self-chan-2', 'seed-ep-self-chan', 2, 'Infestations_Bites', 'Côn trùng cắn', 'thấp', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Sẩn ngứa","text":"Sẩn ngứa rải rác ở vùng da hở sau côn trùng đốt."}]', '["Có bị côn trùng đốt gần đây không"]'),
    ('seed-hyp-spouse-mat-1', 'seed-ep-spouse-mat', 1, 'Acne', 'Mụn trứng cá', 'cao', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Trứng cá","text":"Mụn đầu đen, mụn viêm ở mặt, nặng thêm theo chu kỳ kinh nguyệt."}]', '[]'),
    ('seed-hyp-spouse-chan-1', 'seed-ep-spouse-chan', 1, 'Eczema', 'Chàm thể khô', 'vừa', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Chàm thể khô","text":"Da khô, nứt nẻ, ngứa tăng sau khi tắm nước nóng."}]', '["Tiền sử bệnh da"]'),
    ('seed-hyp-child-tay-1', 'seed-ep-child-tay', 1, 'Eczema', 'Chàm', 'vừa', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Viêm da cơ địa ở trẻ em","text":"Mẩn đỏ ngứa ở mặt gập cánh tay, trẻ gãi nhiều."}]', '["Tiền sử dị ứng trong gia đình"]'),
    ('seed-hyp-child-tay-2', 'seed-ep-child-tay', 2, 'Infestations_Bites', 'Côn trùng đốt', 'thấp', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Sẩn ngứa","text":"Sẩn đỏ ngứa rải rác ở vùng da hở."}]', '["Có tiếp xúc côn trùng hoặc vật nuôi không"]'),
    ('seed-hyp-parent-face-1', 'seed-ep-parent-face', 1, 'Eczema', 'Viêm da tiết bã', 'vừa', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Viêm da tiết bã","text":"Ban đỏ, vảy mỏng ở nếp mũi má, đỏ rát kéo dài."}]', '["Vảy dầu ở da đầu"]'),
    ('seed-hyp-parent-face-2', 'seed-ep-parent-face', 2, 'Rosacea', 'Trứng cá đỏ (rosacea)', 'thấp', '[{"source":"Hướng dẫn chẩn đoán và điều trị Da liễu, Trứng cá đỏ","text":"Đỏ rát vùng giữa mặt, giãn mạch."}]', '["Giãn mạch hay mụn mủ"]');

-- ---------------------------------------------------------------- dữ kiện lâm sàng
-- dài hạn (episode_id NULL): dị ứng, tiền sử, thuốc
INSERT INTO clinical_facts (id, patient_profile_id, episode_id, fact_type, label, detail, verified_at, verified_by_id, created_at, updated_at) VALUES
    ('seed-fact-self-allergy', 'pp-user-1-self', NULL, 'allergy', 'Penicillin', 'Dị ứng thuốc Penicillin', now() - interval '20 days', 'doctor-1', now() - interval '22 days', now() - interval '20 days'),
    ('seed-fact-self-history', 'pp-user-1-self', NULL, 'history', 'Viêm da cơ địa', 'Viêm da cơ địa mạn tính từ nhỏ', now() - interval '20 days', 'doctor-1', now() - interval '22 days', now() - interval '20 days'),
    ('seed-fact-parent-med', 'pp-user-1-parent', NULL, 'medication', 'Thuốc hạ huyết áp', 'Đang dùng thuốc hạ huyết áp mỗi sáng', NULL, NULL, now() - interval '4 days', now() - interval '4 days'),
    -- theo đợt
    ('seed-fact-face-1', 'pp-user-1-self', 'seed-ep-self-face', 'lesion', 'Da đỏ hai bên má', 'Ban đỏ lan hai bên má, tăng khi gặp nắng', now() - interval '45 days', 'doctor-1', now() - interval '47 days', now() - interval '45 days'),
    ('seed-fact-face-2', 'pp-user-1-self', 'seed-ep-self-face', 'symptom', 'Nóng rát', 'Nóng rát nhẹ khoảng 3 tuần, tăng khi ăn đồ cay', now() - interval '45 days', 'doctor-1', now() - interval '47 days', now() - interval '45 days'),
    ('seed-fact-tay-1', 'pp-user-1-self', 'seed-ep-self-tay', 'lesion', 'Mảng da khô ở khuỷu tay', 'Mảng da khô, bong vảy ở nếp gấp khuỷu', now() - interval '20 days', 'doctor-1', now() - interval '22 days', now() - interval '20 days'),
    ('seed-fact-tay-2', 'pp-user-1-self', 'seed-ep-self-tay', 'symptom', 'Ngứa', 'Ngứa nhiều về đêm, khoảng hai tuần', now() - interval '20 days', 'doctor-1', now() - interval '22 days', now() - interval '20 days'),
    ('seed-fact-chan-1', 'pp-user-1-self', 'seed-ep-self-chan', 'symptom', 'Ngứa rát', 'Ngứa rát ở cẳng chân 4 ngày', NULL, NULL, now() - interval '2 days', now() - interval '2 days'),
    ('seed-fact-chan-2', 'pp-user-1-self', 'seed-ep-self-chan', 'lesion', 'Mảng đỏ ở cẳng chân', 'Vài mảng đỏ, mới đổi sữa tắm tuần trước', NULL, NULL, now() - interval '2 days', now() - interval '2 days'),
    ('seed-fact-mat-1', 'pp-user-1-spouse', 'seed-ep-spouse-mat', 'lesion', 'Mụn viêm ở cằm và má', 'Nhiều mụn viêm, có mụn đầu đen, đau khi chạm', now() - interval '10 days', 'doctor-1', now() - interval '12 days', now() - interval '10 days'),
    ('seed-fact-mat-2', 'pp-user-1-spouse', 'seed-ep-spouse-mat', 'symptom', 'Nặng hơn trước kỳ kinh', 'Kéo dài khoảng 2 tháng, nặng lên trước kỳ kinh', now() - interval '10 days', 'doctor-1', now() - interval '12 days', now() - interval '10 days'),
    ('seed-fact-spchan-1', 'pp-user-1-spouse', 'seed-ep-spouse-chan', 'symptom', 'Ngứa sau khi tắm', 'Da cẳng chân ngứa tăng sau khi tắm', NULL, NULL, now() - interval '1 day', now() - interval '1 day'),
    ('seed-fact-spchan-2', 'pp-user-1-spouse', 'seed-ep-spouse-chan', 'lesion', 'Da khô nứt', 'Da cẳng chân khô, nứt nẻ', NULL, NULL, now() - interval '1 day', now() - interval '1 day'),
    ('seed-fact-child-1', 'pp-user-1-child', 'seed-ep-child-tay', 'lesion', 'Mẩn đỏ ở cánh tay', 'Mẩn đỏ ở mặt gập cánh tay, trẻ gãi nhiều', NULL, NULL, now() - interval '3 days', now() - interval '3 days'),
    ('seed-fact-child-2', 'pp-user-1-child', 'seed-ep-child-tay', 'symptom', 'Ngứa', 'Khởi phát khoảng 5 ngày trước', NULL, NULL, now() - interval '3 days', now() - interval '3 days'),
    ('seed-fact-parent-1', 'pp-user-1-parent', 'seed-ep-parent-face', 'lesion', 'Đỏ ở nếp mũi má', 'Ban đỏ kèm vảy mỏng hai bên mũi', NULL, NULL, now() - interval '4 days', now() - interval '4 days'),
    ('seed-fact-parent-2', 'pp-user-1-parent', 'seed-ep-parent-face', 'symptom', 'Đỏ rát', 'Đỏ rát kéo dài hơn một tháng', NULL, NULL, now() - interval '4 days', now() - interval '4 days');

-- nguồn của dữ kiện: trích tin nhắn trong hội thoại AI (consultation.sql)
INSERT INTO clinical_provenances (id, fact_id, kind, message_id, quote, doctor_id, encounter_id, detail, created_at) VALUES
    ('seed-prov-face-1', 'seed-fact-face-1', 'chat', 'seed-msg-face-1', 'hai bên má tôi hay đỏ, nhất là khi ra nắng', NULL, NULL, '', now() - interval '47 days'),
    ('seed-prov-face-2', 'seed-fact-face-2', 'chat', 'seed-msg-face-3', 'cảm giác nóng rát nhẹ, khoảng 3 tuần rồi', NULL, NULL, '', now() - interval '47 days'),
    ('seed-prov-tay-1', 'seed-fact-tay-1', 'chat', 'seed-msg-tay-1', 'Khuỷu tay tôi nổi mảng da khô', NULL, NULL, '', now() - interval '22 days'),
    ('seed-prov-tay-2', 'seed-fact-tay-2', 'chat', 'seed-msg-tay-1', 'ngứa nhiều về đêm, đã khoảng hai tuần', NULL, NULL, '', now() - interval '22 days'),
    ('seed-prov-allergy', 'seed-fact-self-allergy', 'chat', 'seed-msg-tay-3', 'dị ứng Penicillin', NULL, NULL, '', now() - interval '22 days'),
    ('seed-prov-history', 'seed-fact-self-history', 'chat', 'seed-msg-tay-3', 'Tôi bị viêm da cơ địa từ nhỏ', NULL, NULL, '', now() - interval '22 days'),
    ('seed-prov-chan-1', 'seed-fact-chan-1', 'chat', 'seed-msg-chan-1', 'Cẳng chân tôi ngứa rát', NULL, NULL, '', now() - interval '2 days'),
    ('seed-prov-chan-2', 'seed-fact-chan-2', 'chat', 'seed-msg-chan-3', 'Tuần trước tôi có đổi sữa tắm mới', NULL, NULL, '', now() - interval '2 days'),
    ('seed-prov-mat-1', 'seed-fact-mat-1', 'chat', 'seed-msg-mat-1', 'nổi nhiều mụn viêm, có mụn đầu đen', NULL, NULL, '', now() - interval '12 days'),
    ('seed-prov-mat-2', 'seed-fact-mat-2', 'chat', 'seed-msg-mat-3', 'nặng hơn trước kỳ kinh', NULL, NULL, '', now() - interval '12 days');

-- ---------------------------------------------------------------- lịch hẹn (requested | confirmed | in_progress | done | cancelled | no_show)
INSERT INTO appointments (id, patient_profile_id, episode_id, doctor_id, doctor_name, scheduled_at, status, reason, cancel_reason, created_at) VALUES
    ('seed-appt-self-face', 'pp-user-1-self', 'seed-ep-self-face', 'doctor-1', 'BS. Trần Thị Bình', now() - interval '45 days', 'done', 'Đỏ da hai bên má kéo dài', NULL, now() - interval '46 days'),
    ('seed-appt-self-tay', 'pp-user-1-self', 'seed-ep-self-tay', 'doctor-1', 'BS. Trần Thị Bình', now() - interval '20 days', 'done', 'Ngứa mảng da ở khuỷu tay', NULL, now() - interval '21 days'),
    ('seed-appt-spouse-mat', 'pp-user-1-spouse', 'seed-ep-spouse-mat', 'doctor-1', 'BS. Trần Thị Bình', now() - interval '10 days', 'done', 'Mụn viêm ở cằm và má', NULL, now() - interval '11 days'),
    ('seed-appt-spouse-chan', 'pp-user-1-spouse', 'seed-ep-spouse-chan', NULL, NULL, now() + interval '3 days', 'requested', 'Da cẳng chân khô nứt, ngứa', NULL, now() - interval '12 hours'),
    ('seed-appt-child-tay', 'pp-user-1-child', 'seed-ep-child-tay', 'doctor-1', 'BS. Trần Thị Bình', now() + interval '1 day', 'confirmed', 'Con nổi mẩn đỏ ở cánh tay', NULL, now() - interval '2 days'),
    ('seed-appt-parent-face', 'pp-user-1-parent', 'seed-ep-parent-face', 'doctor-1', 'BS. Trần Thị Bình', now() - interval '30 minutes', 'in_progress', 'Mẹ bị đỏ rát ở mặt hơn một tháng', NULL, now() - interval '3 days'),
    ('seed-appt-child-old', 'pp-user-1-child', 'seed-ep-child-old', NULL, NULL, now() - interval '35 days', 'cancelled', 'Mụn nước ở lòng bàn tay', 'Bệnh nhân báo bận, đổi sang dịp khác', now() - interval '40 days');

-- ---------------------------------------------------------------- lần khám (id khớp kênh theo dõi trong consultation.sql)
INSERT INTO encounters (id, appointment_id, patient_profile_id, doctor_id, status, opened_at, closed_at) VALUES
    ('seed-enc-self-face', 'seed-appt-self-face', 'pp-user-1-self', 'doctor-1', 'closed', now() - interval '45 days', now() - interval '45 days' + interval '40 minutes'),
    ('seed-enc-self-tay', 'seed-appt-self-tay', 'pp-user-1-self', 'doctor-1', 'closed', now() - interval '20 days', now() - interval '20 days' + interval '40 minutes'),
    ('seed-enc-spouse-mat', 'seed-appt-spouse-mat', 'pp-user-1-spouse', 'doctor-1', 'closed', now() - interval '10 days', now() - interval '10 days' + interval '40 minutes'),
    ('seed-enc-parent-face', 'seed-appt-parent-face', 'pp-user-1-parent', 'doctor-1', 'open', now() - interval '30 minutes', NULL);

-- ---------------------------------------------------------------- báo cáo kết luận (snapshot bất biến, khoá JSON snake_case như API)
-- mã chẩn đoán thuộc danh mục lớp CNN/DermO; urgency: emergency | few_days | monitor
INSERT INTO finalize_reports (id, patient_profile_id, doctor_id, doctor_name, diagnosis, notes, is_reference_case, consultation_session_id, conversation_id, encounter_id, diagnosis_code, snapshot, created_at) VALUES
    ('seed-fr-self-face', 'pp-user-1-self', 'doctor-1', 'BS. Trần Thị Bình', 'Trứng cá đỏ (rosacea) giai đoạn đỏ mặt', 'Theo dõi sau hai tuần, tránh yếu tố kích thích.', FALSE, NULL, NULL, 'seed-enc-self-face', 'Rosacea',
        format($j${"patient_profile":{"full_name":"Nguyễn Văn An","dob":"1995-05-20","gender":"male","relationship":"self","phone":null,"allergies":"Penicillin","medical_history":"Viêm da cơ địa mạn tính"},
        "assessment":{"reasoning":"Ban đỏ hai bên má, tăng khi gặp nắng và đồ cay, nóng rát nhẹ, không có mụn mủ: phù hợp trứng cá đỏ giai đoạn đỏ mặt.","urgency":"monitor","instructions":["Dùng kem chống nắng mỗi ngày.","Hạn chế đồ cay nóng và rượu bia.","Rửa mặt dịu nhẹ, tránh chà xát."]},
        "clinical_facts":[
          {"fact_type":"lesion","label":"Da đỏ hai bên má","detail":"Ban đỏ lan hai bên má, tăng khi gặp nắng","origin":"patient_reported","provenances":[{"message":{"id":"seed-msg-face-1","sender":"patient","content":"Mấy tuần nay hai bên má tôi hay đỏ, nhất là khi ra nắng hoặc ăn đồ cay.","created_at":"%s","files":[]}}]},
          {"fact_type":"symptom","label":"Nóng rát","detail":"Nóng rát nhẹ khoảng 3 tuần, tăng khi ăn đồ cay","origin":"patient_reported","provenances":[{"message":{"id":"seed-msg-face-3","sender":"patient","content":"Có cảm giác nóng rát nhẹ, khoảng 3 tuần rồi, không có mụn mủ.","created_at":"%s","files":[]}}]}],
        "removed_facts":[]}$j$, to_char(now() - interval '47 days', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), to_char(now() - interval '47 days' + interval '3 minutes', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
        now() - interval '45 days' + interval '40 minutes'),
    ('seed-fr-self-tay', 'pp-user-1-self', 'doctor-1', 'BS. Trần Thị Bình', 'Viêm da cơ địa (chàm thể tạng) mức độ nhẹ', 'Ngứa nhiều về đêm, mảng da khô ở khuỷu tay. Dưỡng ẩm hai lần mỗi ngày.', TRUE, NULL, NULL, 'seed-enc-self-tay', 'Eczema',
        format($j${"patient_profile":{"full_name":"Nguyễn Văn An","dob":"1995-05-20","gender":"male","relationship":"self","phone":null,"allergies":"Penicillin","medical_history":"Viêm da cơ địa mạn tính"},
        "assessment":{"reasoning":"Mảng da khô, ngứa nhiều về đêm ở nếp gấp khuỷu, tiền sử cơ địa: phù hợp viêm da cơ địa mức độ nhẹ.","urgency":"monitor","instructions":["Dưỡng ẩm hai lần mỗi ngày.","Tránh xà phòng mạnh, tắm nước ấm.","Bôi thuốc theo đơn bảy ngày rồi chỉ dùng kem dưỡng ẩm."]},
        "clinical_facts":[
          {"fact_type":"lesion","label":"Mảng da khô ở khuỷu tay","detail":"Mảng da khô, bong vảy ở nếp gấp khuỷu","origin":"doctor_observed","provenances":[{"message":{"id":"seed-msg-tay-1","sender":"patient","content":"Khuỷu tay tôi nổi mảng da khô, ngứa nhiều về đêm, đã khoảng hai tuần.","created_at":"%s","files":[]}}]},
          {"fact_type":"symptom","label":"Ngứa","detail":"Ngứa nhiều về đêm, khoảng hai tuần","origin":"patient_reported","provenances":[{"message":{"id":"seed-msg-tay-1","sender":"patient","content":"Khuỷu tay tôi nổi mảng da khô, ngứa nhiều về đêm, đã khoảng hai tuần.","created_at":"%s","files":[]}}]},
          {"fact_type":"allergy","label":"Penicillin","detail":"Dị ứng thuốc Penicillin","origin":"patient_reported","provenances":[{"message":{"id":"seed-msg-tay-3","sender":"patient","content":"Tôi bị viêm da cơ địa từ nhỏ và dị ứng Penicillin.","created_at":"%s","files":[]}}]}],
        "removed_facts":[]}$j$, to_char(now() - interval '22 days', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), to_char(now() - interval '22 days', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), to_char(now() - interval '22 days' + interval '3 minutes', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
        now() - interval '20 days' + interval '40 minutes'),
    ('seed-fr-spouse-mat', 'pp-user-1-spouse', 'doctor-1', 'BS. Trần Thị Bình', 'Mụn trứng cá mức độ vừa', 'Hướng dẫn rửa mặt dịu nhẹ, không tự nặn mụn. Tái khám sau bốn tuần.', TRUE, NULL, NULL, 'seed-enc-spouse-mat', 'Acne',
        format($j${"patient_profile":{"full_name":"Phạm Thu Hà","dob":"1981-06-02","gender":"female","relationship":"spouse","phone":null,"allergies":"","medical_history":""},
        "assessment":{"reasoning":"Nhiều mụn viêm, mụn đầu đen ở cằm và hai má, nặng hơn theo chu kỳ kinh: phù hợp mụn trứng cá mức độ vừa.","urgency":"monitor","instructions":["Rửa mặt hai lần mỗi ngày bằng sữa rửa mặt dịu nhẹ.","Không tự nặn mụn.","Tái khám sau bốn tuần dùng thuốc."]},
        "clinical_facts":[
          {"fact_type":"lesion","label":"Mụn viêm ở cằm và má","detail":"Nhiều mụn viêm, có mụn đầu đen, đau khi chạm","origin":"patient_reported","provenances":[{"message":{"id":"seed-msg-mat-1","sender":"patient","content":"Cằm và hai má tôi nổi nhiều mụn viêm, có mụn đầu đen, đau khi chạm vào.","created_at":"%s","files":[]}}]},
          {"fact_type":"symptom","label":"Nặng hơn trước kỳ kinh","detail":"Kéo dài khoảng 2 tháng, nặng lên trước kỳ kinh","origin":"patient_reported","provenances":[{"message":{"id":"seed-msg-mat-3","sender":"patient","content":"Khoảng 2 tháng, nặng hơn trước kỳ kinh.","created_at":"%s","files":[]}}]}],
        "removed_facts":[]}$j$, to_char(now() - interval '12 days', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), to_char(now() - interval '12 days' + interval '3 minutes', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')),
        now() - interval '10 days' + interval '40 minutes');
