-- Dữ liệu mẫu database consultation (không phải migration Flyway nên sửa tự do). Nạp bởi scripts/reseed-user-data.sh sau khi đã TRUNCATE.
-- Id cố định tiền tố `seed-` để clinical.sql tham chiếu chéo (tin nhắn nguồn của dữ kiện, kênh theo dõi theo lần khám).
-- Mốc thời gian tính theo now() nên dữ liệu luôn "mới" khi demo.

-- Hội thoại AI của user-1 (ba hồ sơ: bản thân, vợ/chồng)
INSERT INTO conversations (id, user_id, patient_profile_id, title, model, created_at, updated_at, kind, encounter_id, doctor_id, followup_until) VALUES
    ('seed-conv-self-face', 'user-1', 'pp-user-1-self', 'Đỏ da hai bên má', 'gemma-4-26b', now() - interval '47 days', now() - interval '47 days', 'ai_chat', NULL, NULL, NULL),
    ('seed-conv-self-tay',  'user-1', 'pp-user-1-self', 'Ngứa mảng da ở khuỷu tay', 'gemma-4-26b', now() - interval '22 days', now() - interval '22 days', 'ai_chat', NULL, NULL, NULL),
    ('seed-conv-self-chan', 'user-1', 'pp-user-1-self', 'Ngứa rát ở cẳng chân', 'gemma-4-26b', now() - interval '2 days', now() - interval '2 days', 'ai_chat', NULL, NULL, NULL),
    ('seed-conv-spouse-mat', 'user-1', 'pp-user-1-spouse', 'Mụn ở vùng cằm và hai má', 'gemma-4-26b', now() - interval '12 days', now() - interval '12 days', 'ai_chat', NULL, NULL, NULL),
    ('seed-conv-spouse-chan', 'user-1', 'pp-user-1-spouse', 'Da cẳng chân khô nứt', 'gemma-4-26b', now() - interval '1 day', now() - interval '1 day', 'ai_chat', NULL, NULL, NULL),
    ('seed-conv-child-tay', 'user-1', 'pp-user-1-child', 'Con bị nổi mẩn ở cánh tay', 'gemma-4-26b', now() - interval '3 days', now() - interval '3 days', 'ai_chat', NULL, NULL, NULL),
    ('seed-conv-parent-face', 'user-1', 'pp-user-1-parent', 'Mẹ bị đỏ rát ở mặt', 'gemma-4-26b', now() - interval '4 days', now() - interval '4 days', 'ai_chat', NULL, NULL, NULL);

INSERT INTO messages (id, conversation_id, sender, message_type, content, status, created_at) VALUES
    -- đỏ mặt (bản thân, đã khám cách đây 45 ngày)
    ('seed-msg-face-1', 'seed-conv-self-face', 'patient', 'text', 'Mấy tuần nay hai bên má tôi hay đỏ, nhất là khi ra nắng hoặc ăn đồ cay.', 'done', now() - interval '47 days'),
    ('seed-msg-face-2', 'seed-conv-self-face', 'ai', 'text', 'Bạn có thấy rát, nóng hoặc có mụn nhỏ kèm theo không? Triệu chứng kéo dài bao lâu rồi?', 'done', now() - interval '47 days' + interval '1 minute'),
    ('seed-msg-face-3', 'seed-conv-self-face', 'patient', 'text', 'Có cảm giác nóng rát nhẹ, khoảng 3 tuần rồi, không có mụn mủ.', 'done', now() - interval '47 days' + interval '3 minutes'),
    ('seed-msg-face-4', 'seed-conv-self-face', 'ai', 'text', 'Mình ghi nhận da đỏ hai má tăng khi gặp nắng và đồ cay. Đây chỉ là gợi ý hỗ trợ, không phải chẩn đoán y khoa; bạn nên đặt lịch để bác sĩ khám trực tiếp.', 'done', now() - interval '47 days' + interval '4 minutes'),
    -- khuỷu tay (bản thân, đã khám cách đây 20 ngày)
    ('seed-msg-tay-1', 'seed-conv-self-tay', 'patient', 'text', 'Khuỷu tay tôi nổi mảng da khô, ngứa nhiều về đêm, đã khoảng hai tuần.', 'done', now() - interval '22 days'),
    ('seed-msg-tay-2', 'seed-conv-self-tay', 'ai', 'text', 'Bạn có tiền sử chàm hay dị ứng thuốc nào không?', 'done', now() - interval '22 days' + interval '1 minute'),
    ('seed-msg-tay-3', 'seed-conv-self-tay', 'patient', 'text', 'Tôi bị viêm da cơ địa từ nhỏ và dị ứng Penicillin.', 'done', now() - interval '22 days' + interval '3 minutes'),
    ('seed-msg-tay-4', 'seed-conv-self-tay', 'ai', 'text', 'Mình đã ghi nhận: mảng da khô ở khuỷu tay, ngứa về đêm, tiền sử viêm da cơ địa, dị ứng Penicillin. Gợi ý của AI (không phải chẩn đoán y khoa): chàm thể tạng. Bạn nên đặt lịch khám.', 'done', now() - interval '22 days' + interval '4 minutes'),
    -- cẳng chân (bản thân, đang mở, chưa đặt lịch)
    ('seed-msg-chan-1', 'seed-conv-self-chan', 'patient', 'text', 'Cẳng chân tôi ngứa rát, có vài mảng đỏ, đã 4 ngày.', 'done', now() - interval '2 days'),
    ('seed-msg-chan-2', 'seed-conv-self-chan', 'ai', 'text', 'Bạn có mới đổi xà phòng, sữa tắm hay mặc loại quần áo mới không?', 'done', now() - interval '2 days' + interval '1 minute'),
    ('seed-msg-chan-3', 'seed-conv-self-chan', 'patient', 'text', 'Tuần trước tôi có đổi sữa tắm mới.', 'done', now() - interval '2 days' + interval '3 minutes'),
    ('seed-msg-chan-4', 'seed-conv-self-chan', 'ai', 'text', 'Gợi ý của AI (không phải chẩn đoán y khoa): có thể là viêm da tiếp xúc. Bạn nên ngừng sản phẩm mới và đặt lịch để bác sĩ đánh giá.', 'done', now() - interval '2 days' + interval '4 minutes'),
    -- mụn (vợ/chồng, đã khám cách đây 10 ngày)
    ('seed-msg-mat-1', 'seed-conv-spouse-mat', 'patient', 'text', 'Cằm và hai má tôi nổi nhiều mụn viêm, có mụn đầu đen, đau khi chạm vào.', 'done', now() - interval '12 days'),
    ('seed-msg-mat-2', 'seed-conv-spouse-mat', 'ai', 'text', 'Tình trạng này kéo dài bao lâu và có liên quan đến chu kỳ kinh nguyệt không?', 'done', now() - interval '12 days' + interval '1 minute'),
    ('seed-msg-mat-3', 'seed-conv-spouse-mat', 'patient', 'text', 'Khoảng 2 tháng, nặng hơn trước kỳ kinh.', 'done', now() - interval '12 days' + interval '3 minutes'),
    ('seed-msg-mat-4', 'seed-conv-spouse-mat', 'ai', 'text', 'Gợi ý của AI (không phải chẩn đoán y khoa): mụn trứng cá. Bạn nên đặt lịch để bác sĩ đánh giá mức độ và hướng điều trị.', 'done', now() - interval '12 days' + interval '4 minutes'),
    -- cẳng chân khô nứt (vợ/chồng, chờ bác sĩ xác nhận lịch)
    ('seed-msg-spchan-1', 'seed-conv-spouse-chan', 'patient', 'text', 'Da cẳng chân tôi khô, nứt nẻ và ngứa, nhất là sau khi tắm.', 'done', now() - interval '1 day'),
    ('seed-msg-spchan-2', 'seed-conv-spouse-chan', 'ai', 'text', 'Gợi ý của AI (không phải chẩn đoán y khoa): da khô hoặc chàm thể khô. Bạn nên dưỡng ẩm và đặt lịch khám nếu ngứa tăng.', 'done', now() - interval '1 day' + interval '2 minutes'),
    -- con: nổi mẩn cánh tay (đã đặt lịch, bác sĩ đã xác nhận)
    ('seed-msg-child-1', 'seed-conv-child-tay', 'patient', 'text', 'Con tôi 7 tuổi, nổi mẩn đỏ ở cánh tay, gãi nhiều, bắt đầu từ 5 ngày trước.', 'done', now() - interval '3 days'),
    ('seed-msg-child-2', 'seed-conv-child-tay', 'ai', 'text', 'Gợi ý của AI (không phải chẩn đoán y khoa): có thể là chàm hoặc côn trùng đốt. Bạn nên đặt lịch để bác sĩ khám trực tiếp.', 'done', now() - interval '3 days' + interval '2 minutes'),
    -- mẹ: đỏ rát mặt (đang được khám)
    ('seed-msg-parent-1', 'seed-conv-parent-face', 'patient', 'text', 'Mẹ tôi bị đỏ và rát ở mặt, nhất là hai bên mũi, có vảy mỏng, đã hơn một tháng.', 'done', now() - interval '4 days'),
    ('seed-msg-parent-2', 'seed-conv-parent-face', 'ai', 'text', 'Gợi ý của AI (không phải chẩn đoán y khoa): viêm da tiết bã hoặc trứng cá đỏ. Bạn nên đặt lịch để bác sĩ khám.', 'done', now() - interval '4 days' + interval '2 minutes');

-- Kênh theo dõi sau khám, mỗi lần khám một kênh (id lần khám khớp clinical.sql)
-- Hạn = lúc chốt + 30 ngày: kênh khám cách đây 45 ngày đã quá hạn nên chỉ đọc; lần khám đang diễn ra chưa có hạn.
INSERT INTO conversations (id, user_id, patient_profile_id, title, model, created_at, updated_at, kind, encounter_id, doctor_id, followup_until) VALUES
    ('seed-fu-self-face', 'user-1', 'pp-user-1-self', '', 'doctor', now() - interval '45 days', now() - interval '44 days', 'doctor_followup', 'seed-enc-self-face', 'doctor-1',
        now() - interval '45 days' + interval '40 minutes' + interval '30 days'),
    ('seed-fu-self-tay', 'user-1', 'pp-user-1-self', '', 'doctor', now() - interval '20 days', now() - interval '18 days', 'doctor_followup', 'seed-enc-self-tay', 'doctor-1',
        now() - interval '20 days' + interval '40 minutes' + interval '30 days'),
    ('seed-fu-spouse-mat', 'user-1', 'pp-user-1-spouse', '', 'doctor', now() - interval '10 days', now() - interval '9 days', 'doctor_followup', 'seed-enc-spouse-mat', 'doctor-1',
        now() - interval '10 days' + interval '40 minutes' + interval '30 days'),
    ('seed-fu-parent-face', 'user-1', 'pp-user-1-parent', '', 'doctor', now() - interval '30 minutes', now() - interval '10 minutes', 'doctor_followup', 'seed-enc-parent-face', 'doctor-1', NULL);

INSERT INTO messages (id, conversation_id, sender, message_type, content, status, created_at) VALUES
    ('seed-fumsg-face-1', 'seed-fu-self-face', 'doctor', 'text', 'Chào bạn, nhớ dùng kem chống nắng mỗi ngày và hạn chế đồ cay nóng. Nếu da đỏ nhiều hơn, nhắn cho tôi nhé.', 'done', now() - interval '45 days' + interval '1 hour'),
    ('seed-fumsg-face-2', 'seed-fu-self-face', 'patient', 'text', 'Dạ cảm ơn bác sĩ, sau hai tuần da đã đỡ đỏ nhiều rồi ạ.', 'done', now() - interval '31 days'),
    ('seed-fumsg-tay-1', 'seed-fu-self-tay', 'doctor', 'text', 'Bạn nhớ bôi kem dưỡng ẩm hai lần mỗi ngày và tránh xà phòng mạnh. Có vấn đề gì cứ nhắn cho tôi.', 'done', now() - interval '20 days' + interval '1 hour'),
    ('seed-fumsg-tay-2', 'seed-fu-self-tay', 'patient', 'text', 'Dạ, sau ba ngày dùng thuốc em thấy đỡ ngứa hơn ạ. Em có nên tiếp tục bôi thuốc không?', 'done', now() - interval '18 days'),
    ('seed-fumsg-tay-3', 'seed-fu-self-tay', 'doctor', 'text', 'Bạn tiếp tục bôi thuốc thêm bảy ngày rồi chỉ dùng kem dưỡng ẩm. Nếu ngứa tái phát, hãy báo lại.', 'done', now() - interval '18 days' + interval '30 minutes'),
    ('seed-fumsg-mat-1', 'seed-fu-spouse-mat', 'doctor', 'text', 'Chị rửa mặt hai lần mỗi ngày bằng sữa rửa mặt dịu nhẹ và không tự nặn mụn nhé.', 'done', now() - interval '10 days' + interval '1 hour'),
    ('seed-fumsg-mat-2', 'seed-fu-spouse-mat', 'patient', 'text', 'Dạ em cảm ơn bác sĩ. Khi nào em nên tái khám ạ?', 'done', now() - interval '9 days'),
    ('seed-fumsg-mat-3', 'seed-fu-spouse-mat', 'doctor', 'text', 'Sau bốn tuần dùng thuốc, chị đặt lịch tái khám để tôi đánh giá lại nhé.', 'done', now() - interval '9 days' + interval '20 minutes'),
    ('seed-fumsg-parent-1', 'seed-fu-parent-face', 'doctor', 'text', 'Chào chị, tôi đang khám cho mẹ chị. Chị có thể gửi thêm ảnh vùng da bị đỏ vào đây nhé.', 'done', now() - interval '10 minutes');
