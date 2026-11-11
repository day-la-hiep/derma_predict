-- DB identity: tài khoản và hồ sơ bệnh nhân. Id do ứng dụng sinh (UUID) hoặc cố định ở dữ liệu mẫu (user-1, doctor-1...).
CREATE TABLE users (
    id            VARCHAR(64)  NOT NULL,
    username      VARCHAR(64)  NOT NULL,
    full_name     VARCHAR(255) NOT NULL,
    dob           DATE         NOT NULL,
    gender        VARCHAR(16)  NOT NULL,
    password_hash VARCHAR(255),
    created_at    TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uq_users_username UNIQUE (username)
);

CREATE TABLE doctors (
    user_id     VARCHAR(64) NOT NULL,
    description TEXT        NOT NULL,
    CONSTRAINT pk_doctors PRIMARY KEY (user_id),
    CONSTRAINT fk_doctors_user_id_users FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE admins (
    user_id VARCHAR(64) NOT NULL,
    CONSTRAINT pk_admins PRIMARY KEY (user_id),
    CONSTRAINT fk_admins_user_id_users FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE patient_profiles (
    id           VARCHAR(64)  NOT NULL,
    user_id      VARCHAR(64)  NOT NULL,
    full_name    VARCHAR(255) NOT NULL,
    dob          DATE         NOT NULL,
    gender       VARCHAR(16)  NOT NULL,
    relationship VARCHAR(16)  NOT NULL DEFAULT 'self',
    phone        VARCHAR(32),
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT pk_patient_profiles PRIMARY KEY (id),
    CONSTRAINT fk_patient_profiles_user_id_users FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_patient_profiles_user_id ON patient_profiles (user_id);
