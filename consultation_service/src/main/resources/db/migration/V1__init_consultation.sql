-- DB consultation: hội thoại, tin nhắn, phiên tư vấn, cuộc gọi video, báo cáo tiền tư vấn.
-- Không FK sang service khác: patient_profile_id, user_id, doctor_id là id mềm (identity). `metadata` là TEXT JSON vì không truy vấn bên trong.
CREATE TABLE files (
    id           VARCHAR(64)  NOT NULL,
    file_name    VARCHAR(255) NOT NULL,
    storage_key  VARCHAR(512) NOT NULL,
    content_type VARCHAR(128),
    size         BIGINT,
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_files PRIMARY KEY (id),
    CONSTRAINT uq_files_storage_key UNIQUE (storage_key)
);

CREATE TABLE conversations (
    id                 VARCHAR(64)  NOT NULL,
    user_id            VARCHAR(64)  NOT NULL,
    patient_profile_id VARCHAR(64)  NOT NULL,
    title              VARCHAR(255) NOT NULL DEFAULT '',
    model              VARCHAR(32)  NOT NULL,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_conversations PRIMARY KEY (id)
);
CREATE INDEX ix_conversations_user_id ON conversations (user_id);
CREATE INDEX ix_conversations_patient_profile_id ON conversations (patient_profile_id);

CREATE TABLE consultation_sessions (
    id              VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    doctor_id       VARCHAR(64),
    doctor_name     VARCHAR(255),
    patient_name    VARCHAR(255),
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    reason          TEXT        NOT NULL,
    requested_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at      TIMESTAMP WITH TIME ZONE,
    resolved_at     TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_consultation_sessions PRIMARY KEY (id),
    CONSTRAINT fk_consultation_sessions_conversation_id_conversations FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
    CONSTRAINT ck_consultation_sessions_doctor_when_not_pending CHECK (status = 'pending' OR doctor_id IS NOT NULL),
    CONSTRAINT ck_consultation_sessions_resolved_at_when_resolved CHECK (status <> 'resolved' OR resolved_at IS NOT NULL)
);
CREATE INDEX ix_consultation_sessions_conversation_id ON consultation_sessions (conversation_id);

CREATE TABLE video_calls (
    id                      VARCHAR(64)  NOT NULL,
    consultation_session_id VARCHAR(64)  NOT NULL,
    room_id                 VARCHAR(128) NOT NULL,
    status                  VARCHAR(16)  NOT NULL DEFAULT 'pending',
    started_at              TIMESTAMP WITH TIME ZONE,
    ended_at                TIMESTAMP WITH TIME ZONE,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_video_calls PRIMARY KEY (id),
    CONSTRAINT uq_video_calls_room_id UNIQUE (room_id),
    CONSTRAINT fk_video_calls_consultation_session_id_consultation_sessions FOREIGN KEY (consultation_session_id) REFERENCES consultation_sessions (id) ON DELETE CASCADE
);
CREATE INDEX ix_video_calls_consultation_session_id ON video_calls (consultation_session_id);

CREATE TABLE messages (
    id                      VARCHAR(64) NOT NULL,
    conversation_id         VARCHAR(64) NOT NULL,
    sender                  VARCHAR(20) NOT NULL,
    message_type            VARCHAR(32) NOT NULL DEFAULT 'text',
    video_call_id           VARCHAR(64),
    consultation_session_id VARCHAR(64),
    content                 TEXT        NOT NULL,
    status                  VARCHAR(20) NOT NULL,
    metadata                TEXT,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_messages PRIMARY KEY (id),
    CONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY (conversation_id) REFERENCES conversations (id),
    CONSTRAINT fk_messages_video_call_id_video_calls FOREIGN KEY (video_call_id) REFERENCES video_calls (id) ON DELETE SET NULL,
    CONSTRAINT fk_messages_consultation_session_id_consultation_sessions FOREIGN KEY (consultation_session_id) REFERENCES consultation_sessions (id) ON DELETE SET NULL
);
CREATE INDEX ix_messages_conversation_id ON messages (conversation_id);
CREATE INDEX ix_messages_consultation_session_id ON messages (consultation_session_id);

CREATE TABLE message_files (
    message_id VARCHAR(64) NOT NULL,
    file_id    VARCHAR(64) NOT NULL,
    CONSTRAINT pk_message_files PRIMARY KEY (message_id, file_id),
    CONSTRAINT fk_message_files_message_id_messages FOREIGN KEY (message_id) REFERENCES messages (id) ON DELETE CASCADE,
    CONSTRAINT fk_message_files_file_id_files FOREIGN KEY (file_id) REFERENCES files (id) ON DELETE CASCADE
);

CREATE TABLE pre_consultation_reports (
    id                      VARCHAR(64) NOT NULL,
    consultation_session_id VARCHAR(64) NOT NULL,
    summary                 TEXT        NOT NULL,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_pre_consultation_reports PRIMARY KEY (id),
    CONSTRAINT uq_pre_consultation_reports_consultation_session_id UNIQUE (consultation_session_id),
    CONSTRAINT fk_pre_consultation_reports_session FOREIGN KEY (consultation_session_id) REFERENCES consultation_sessions (id) ON DELETE CASCADE
);
