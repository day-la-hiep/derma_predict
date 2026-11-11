package vn.derma.identity.entity;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

@Entity
@Table(name = "patient_profiles")
public class PatientProfile {

    @Id
    public String id;
    @Column(name = "user_id", nullable = false)
    public String userId;
    @Column(name = "full_name", nullable = false)
    public String fullName;
    @Column(nullable = false)
    public LocalDate dob;
    @Column(nullable = false)
    public String gender;
    @Column(nullable = false)
    public String relationship = "self";
    public String phone;
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
