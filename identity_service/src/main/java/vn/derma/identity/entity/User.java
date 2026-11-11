package vn.derma.identity.entity;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

/** Entity JPA dùng field public để khỏi viết getter/setter; Hibernate truy cập trực tiếp theo field. */
@Entity
@Table(name = "users")
public class User {

    @Id
    public String id;
    @Column(unique = true, nullable = false)
    public String username;
    @Column(name = "full_name", nullable = false)
    public String fullName;
    @Column(nullable = false)
    public LocalDate dob;
    @Column(nullable = false)
    public String gender;
    /** Null: tài khoản mẫu chưa đặt mật khẩu, chưa đăng nhập được. */
    @Column(name = "password_hash")
    public String passwordHash;
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;

    @PrePersist
    void fillDefaults() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }
}
