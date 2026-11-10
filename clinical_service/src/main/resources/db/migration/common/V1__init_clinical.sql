-- DB clinical: đợt bệnh, giả thuyết AI, fact lâm sàng + nguồn, lịch hẹn, lần khám, báo cáo kết luận, ảnh bệnh.
-- Không FK sang service khác: patient_profile_id, doctor_id, conversation_id, consultation_session_id, message_id là id mềm.
-- Chỉ mục unique có điều kiện/biểu thức nằm ở `db/migration/postgresql` (H2 của test không hỗ trợ).
CREATE TABLE clinical_episodes (
    id                   VARCHAR(64) NOT NULL,
    patient_profile_id   VARCHAR(64) NOT NULL,
    body_site            VARCHAR(16) NOT NULL,
    status               VARCHAR(16) NOT NULL DEFAULT 'open',
    last_conversation_id VARCHAR(64),
    summary              TEXT        NOT NULL DEFAULT '',
    summary_at           TIMESTAMP WITH TIME ZONE,
    urgency              VARCHAR(16),
    red_flags            TEXT        NOT NULL DEFAULT '[]',
    image_predictions    TEXT        NOT NULL DEFAULT '[]',
    model_version        VARCHAR(64) NOT NULL DEFAULT '',
    opened_at            TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at           TIMESTAMP WITH TIME ZONE NOT NULL,
    closed_at            TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_clinical_episodes PRIMARY KEY (id),
    CONSTRAINT ck_clinical_episodes_status_valid CHECK (status IN ('open', 'in_exam', 'closed', 'expired')),
    CONSTRAINT ck_clinical_episodes_closed_at_when_closed CHECK (status IN ('open', 'in_exam') OR closed_at IS NOT NULL)
);
CREATE INDEX ix_clinical_episodes_patient_profile_id ON clinical_episodes (patient_profile_id);
CREATE INDEX ix_clinical_episodes_last_conversation_id ON clinical_episodes (last_conversation_id);

CREATE TABLE ai_hypotheses (
    id             VARCHAR(64)  NOT NULL,
    episode_id     VARCHAR(64)  NOT NULL,
    rank           INTEGER      NOT NULL,
    diagnosis_code VARCHAR(64)  NOT NULL,
    disease        VARCHAR(255) NOT NULL,
    confidence     VARCHAR(8)   NOT NULL,
    evidence       TEXT         NOT NULL DEFAULT '[]',
    missing        TEXT         NOT NULL DEFAULT '[]',
    CONSTRAINT pk_ai_hypotheses PRIMARY KEY (id),
    CONSTRAINT fk_ai_hypotheses_episode_id_clinical_episodes FOREIGN KEY (episode_id) REFERENCES clinical_episodes (id) ON DELETE CASCADE,
    CONSTRAINT ck_ai_hypotheses_rank_positive CHECK (rank >= 1),
    CONSTRAINT uq_ai_hypotheses_episode_rank UNIQUE (episode_id, rank)
);

CREATE TABLE clinical_facts (
    id                 VARCHAR(64)  NOT NULL,
    patient_profile_id VARCHAR(64)  NOT NULL,
    episode_id         VARCHAR(64),
    fact_type          VARCHAR(32)  NOT NULL,
    label              VARCHAR(255) NOT NULL,
    ontology_id        VARCHAR(128),
    detail             TEXT         NOT NULL DEFAULT '',
    verified_at        TIMESTAMP WITH TIME ZONE,
    verified_by_id     VARCHAR(64),
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_clinical_facts PRIMARY KEY (id),
    CONSTRAINT fk_clinical_facts_episode_id_clinical_episodes FOREIGN KEY (episode_id) REFERENCES clinical_episodes (id) ON DELETE CASCADE,
    CONSTRAINT ck_clinical_facts_fact_type_valid CHECK (fact_type IN ('symptom', 'lesion', 'history', 'medication', 'allergy', 'other')),
    CONSTRAINT ck_clinical_facts_long_term_no_episode CHECK ((fact_type IN ('allergy', 'history', 'medication')) = (episode_id IS NULL))
);
CREATE INDEX ix_clinical_facts_patient_profile_id ON clinical_facts (patient_profile_id);
CREATE INDEX ix_clinical_facts_episode_id ON clinical_facts (episode_id);

CREATE TABLE appointments (
    id                 VARCHAR(64) NOT NULL,
    patient_profile_id VARCHAR(64) NOT NULL,
    episode_id         VARCHAR(64) NOT NULL,
    doctor_id          VARCHAR(64),
    doctor_name        VARCHAR(255),
    scheduled_at       TIMESTAMP WITH TIME ZONE NOT NULL,
    status             VARCHAR(16) NOT NULL DEFAULT 'requested',
    reason             TEXT        NOT NULL DEFAULT '',
    cancel_reason      TEXT,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_appointments PRIMARY KEY (id),
    CONSTRAINT fk_appointments_episode_id_clinical_episodes FOREIGN KEY (episode_id) REFERENCES clinical_episodes (id) ON DELETE CASCADE,
    CONSTRAINT ck_appointments_status_valid CHECK (status IN ('requested', 'confirmed', 'in_progress', 'done', 'cancelled', 'no_show')),
    CONSTRAINT ck_appointments_cancel_reason_when_cancelled CHECK (status <> 'cancelled' OR cancel_reason IS NOT NULL),
    CONSTRAINT ck_appointments_doctor_when_confirmed CHECK (status IN ('requested', 'cancelled') OR doctor_id IS NOT NULL)
);
CREATE INDEX ix_appointments_patient_profile_id ON appointments (patient_profile_id);
CREATE INDEX ix_appointments_episode_id ON appointments (episode_id);
CREATE INDEX ix_appointments_scheduled_at ON appointments (scheduled_at);

CREATE TABLE encounters (
    id                 VARCHAR(64) NOT NULL,
    appointment_id     VARCHAR(64) NOT NULL,
    patient_profile_id VARCHAR(64) NOT NULL,
    doctor_id          VARCHAR(64),
    status             VARCHAR(8)  NOT NULL DEFAULT 'open',
    opened_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    closed_at          TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_encounters PRIMARY KEY (id),
    CONSTRAINT uq_encounters_appointment_id UNIQUE (appointment_id),
    CONSTRAINT fk_encounters_appointment_id_appointments FOREIGN KEY (appointment_id) REFERENCES appointments (id) ON DELETE CASCADE,
    CONSTRAINT ck_encounters_status_valid CHECK (status IN ('open', 'closed')),
    CONSTRAINT ck_encounters_closed_at_when_closed CHECK (status <> 'closed' OR closed_at IS NOT NULL)
);
CREATE INDEX ix_encounters_patient_profile_id ON encounters (patient_profile_id);

CREATE TABLE clinical_provenances (
    id           VARCHAR(64) NOT NULL,
    fact_id      VARCHAR(64) NOT NULL,
    kind         VARCHAR(16) NOT NULL DEFAULT 'chat',
    message_id   VARCHAR(64),
    quote        TEXT        NOT NULL DEFAULT '',
    doctor_id    VARCHAR(64),
    encounter_id VARCHAR(64),
    detail       TEXT        NOT NULL DEFAULT '',
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_clinical_provenances PRIMARY KEY (id),
    CONSTRAINT fk_clinical_provenances_fact_id_clinical_facts FOREIGN KEY (fact_id) REFERENCES clinical_facts (id) ON DELETE CASCADE,
    CONSTRAINT fk_clinical_provenances_encounter_id_encounters FOREIGN KEY (encounter_id) REFERENCES encounters (id) ON DELETE SET NULL,
    CONSTRAINT ck_clinical_provenances_kind_valid CHECK (kind IN ('chat', 'doctor', 'profile'))
);
CREATE INDEX ix_clinical_provenances_fact_id ON clinical_provenances (fact_id);
CREATE INDEX ix_clinical_provenances_message_id ON clinical_provenances (message_id);

CREATE TABLE finalize_reports (
    id                      VARCHAR(64) NOT NULL,
    patient_profile_id      VARCHAR(64) NOT NULL,
    doctor_id               VARCHAR(64),
    doctor_name             VARCHAR(255),
    diagnosis               TEXT        NOT NULL,
    notes                   TEXT        NOT NULL DEFAULT '',
    is_reference_case       BOOLEAN     NOT NULL DEFAULT FALSE,
    consultation_session_id VARCHAR(64),
    conversation_id         VARCHAR(64),
    encounter_id            VARCHAR(64),
    diagnosis_code          VARCHAR(64),
    snapshot                TEXT,
    created_at              TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_finalize_reports PRIMARY KEY (id),
    CONSTRAINT uq_finalize_reports_consultation_session_id UNIQUE (consultation_session_id),
    CONSTRAINT uq_finalize_reports_encounter_id UNIQUE (encounter_id),
    CONSTRAINT fk_finalize_reports_encounter_id_encounters FOREIGN KEY (encounter_id) REFERENCES encounters (id) ON DELETE SET NULL,
    CONSTRAINT ck_finalize_reports_code_when_encounter CHECK (encounter_id IS NULL OR diagnosis_code IS NOT NULL)
);
CREATE INDEX ix_finalize_reports_patient_profile_id ON finalize_reports (patient_profile_id);

CREATE TABLE patient_images (
    id                 VARCHAR(64)  NOT NULL,
    finalize_report_id VARCHAR(64)  NOT NULL,
    storage_key        VARCHAR(512) NOT NULL,
    file_name          VARCHAR(255) NOT NULL DEFAULT '',
    content_type       VARCHAR(128),
    body_site          VARCHAR(128) NOT NULL DEFAULT '',
    description        TEXT         NOT NULL DEFAULT '',
    confirmed_label    VARCHAR(128),
    captured_at        TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_patient_images PRIMARY KEY (id),
    CONSTRAINT fk_patient_images_finalize_report_id_finalize_reports FOREIGN KEY (finalize_report_id) REFERENCES finalize_reports (id) ON DELETE CASCADE
);
CREATE INDEX ix_patient_images_finalize_report_id ON patient_images (finalize_report_id);
