package vn.derma.consultation.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

@Entity
@Table(name = "pre_consultation_reports")
public class PreConsultationReport {

    @Id
    public String id;
    @Column(name = "consultation_session_id", nullable = false, unique = true)
    public String consultationSessionId;
    @Column(nullable = false)
    public String summary;
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;

    @PrePersist
    void onCreate() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }
}
