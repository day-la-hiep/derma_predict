-- Dữ liệu mẫu cho demo (khớp core/scripts/init_db.py): FE hard-code user-1; mật khẩu mọi tài khoản mẫu là 123456.
-- Triển khai thật: bỏ `classpath:db/seed` khỏi spring.flyway.locations trong application.yml.
INSERT INTO users (id, username, full_name, dob, gender, password_hash, created_at) VALUES
    ('user-1', 'user-1', 'Nguyễn Văn An', DATE '1995-05-20', 'male', '$2b$12$ymkigmKPYbNaXHsE8szb1.VWGKi0HJ3UzauJBnFCpv.vt7zXHM6ou', CURRENT_TIMESTAMP),
    ('doctor-1', 'doctor-1', 'BS. Trần Thị Bình', DATE '1982-03-14', 'female', '$2b$12$ymkigmKPYbNaXHsE8szb1.VWGKi0HJ3UzauJBnFCpv.vt7zXHM6ou', CURRENT_TIMESTAMP),
    ('admin-1', 'admin-1', 'Quản trị viên', DATE '1990-01-01', 'male', '$2b$12$ymkigmKPYbNaXHsE8szb1.VWGKi0HJ3UzauJBnFCpv.vt7zXHM6ou', CURRENT_TIMESTAMP);

INSERT INTO doctors (user_id, description) VALUES ('doctor-1', 'Bác sĩ chuyên khoa Da liễu (dữ liệu mẫu).');
INSERT INTO admins (user_id) VALUES ('admin-1');

-- Hồ sơ "chính mình" của user-1 và 3 hồ sơ người nhà để màn Lịch sử khám của bác sĩ có nhiều bệnh nhân khi demo
INSERT INTO patient_profiles (id, user_id, full_name, dob, gender, relationship, phone, created_at) VALUES
    ('pp-user-1-self', 'user-1', 'Nguyễn Văn An', DATE '1995-05-20', 'male', 'self', NULL, CURRENT_TIMESTAMP),
    ('pp-user-1-spouse', 'user-1', 'Phạm Thu Hà', DATE '1981-06-02', 'female', 'spouse', NULL, CURRENT_TIMESTAMP),
    ('pp-user-1-child', 'user-1', 'Nguyễn Minh Khôi', DATE '2018-04-11', 'male', 'child', NULL, CURRENT_TIMESTAMP),
    ('pp-user-1-parent', 'user-1', 'Đỗ Lan Anh', DATE '1974-09-09', 'female', 'parent', NULL, CURRENT_TIMESTAMP);
