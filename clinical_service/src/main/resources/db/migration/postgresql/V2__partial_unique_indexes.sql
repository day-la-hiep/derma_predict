-- Ràng buộc mà H2 (test) không có: unique có điều kiện / theo biểu thức. Cùng ý nghĩa với core/app/models.
-- Bảng fact là hiện trạng: mỗi (phạm vi, loại, nhãn) một dòng, nhãn so không phân biệt hoa thường.
CREATE UNIQUE INDEX uq_clinical_facts_long_term ON clinical_facts (patient_profile_id, fact_type, lower(label)) WHERE episode_id IS NULL;
CREATE UNIQUE INDEX uq_clinical_facts_episode ON clinical_facts (episode_id, fact_type, lower(label)) WHERE episode_id IS NOT NULL;
-- mỗi vùng tối đa 1 đợt đang hoạt động: nhiều hội thoại cùng cập nhật một đợt
CREATE UNIQUE INDEX uq_clinical_episodes_active_site ON clinical_episodes (patient_profile_id, body_site) WHERE status IN ('open', 'in_exam');
-- mỗi đợt tối đa 1 lịch hẹn còn hiệu lực
CREATE UNIQUE INDEX uq_appointments_active_episode ON appointments (episode_id) WHERE status IN ('requested', 'confirmed', 'in_progress');
