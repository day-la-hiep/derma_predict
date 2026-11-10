package vn.derma.consultation.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

@Entity
@Table(name = "consultation_sessions")
public class ConsultationSession {

    @Id
    public String id;
    @Column(name = "conversation_id", nullable = false)
    public String conversationId;
    @Column(name = "doctor_id")
    public String doctorId;
    /** Tên hiển thị lưu sẵn lúc ghi để khỏi gọi identity mỗi lần liệt kê. */
    @Column(name = "doctor_name")
    public String doctorName;
    @Column(name = "patient_name")
    public String patientName;
    /** pending | active | resolved */
    @Column(nullable = false)
    public String status = "pending";
    @Column(nullable = false)
    public String reason;
    @Column(name = "requested_at", nullable = false)
    public Instant requestedAt;
    @Column(name = "started_at")
    public Instant startedAt;
    @Column(name = "resolved_at")
    public Instant resolvedAt;

    @PrePersist
    void onCreate() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
        if (requestedAt == null) {
            requestedAt = Instant.now();
        }
    }
}
