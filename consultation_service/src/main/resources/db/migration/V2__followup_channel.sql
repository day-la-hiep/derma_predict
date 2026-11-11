-- Kênh theo dõi sau khám: hội thoại bác sĩ ↔ bệnh nhân gắn lần khám (encounter nằm ở clinical, id mềm).
-- Chỉ thêm cột nullable/default và nới NOT NULL; không drop gì để giữ phiên tư vấn cũ.
ALTER TABLE conversations ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'ai_chat';
ALTER TABLE conversations ADD COLUMN encounter_id VARCHAR(64);
ALTER TABLE conversations ADD COLUMN doctor_id VARCHAR(64);
ALTER TABLE conversations ADD COLUMN followup_until TIMESTAMP WITH TIME ZONE;
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_kind_valid CHECK (kind IN ('ai_chat', 'doctor_followup'));
ALTER TABLE conversations ADD CONSTRAINT ck_conversations_followup_has_encounter CHECK (
    (kind = 'doctor_followup' AND encounter_id IS NOT NULL) OR (kind <> 'doctor_followup' AND encounter_id IS NULL));
-- encounter_id chỉ khác NULL ở kênh theo dõi (check trên) nên UNIQUE thường đã đủ, không cần partial index
ALTER TABLE conversations ADD CONSTRAINT uq_conversations_encounter_id UNIQUE (encounter_id);
CREATE INDEX ix_conversations_doctor_id ON conversations (doctor_id);

-- Cuộc gọi gắn kênh thay vì phiên; cuộc gọi cũ giữ nguyên cột phiên và được điền conversation_id.
ALTER TABLE video_calls ADD COLUMN conversation_id VARCHAR(64);
ALTER TABLE video_calls ALTER COLUMN consultation_session_id DROP NOT NULL;
UPDATE video_calls SET conversation_id = (SELECT s.conversation_id FROM consultation_sessions s WHERE s.id = video_calls.consultation_session_id);
ALTER TABLE video_calls ADD CONSTRAINT fk_video_calls_conversation_id_conversations FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE;
CREATE INDEX ix_video_calls_conversation_id ON video_calls (conversation_id);
