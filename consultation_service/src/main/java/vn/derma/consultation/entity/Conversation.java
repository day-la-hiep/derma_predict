package vn.derma.consultation.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

/** Entity JPA dùng field public (như identity) để khỏi viết getter/setter. */
@Entity
@Table(name = "conversations")
public class Conversation {

    @Id
    public String id;
    @Column(name = "user_id", nullable = false)
    public String userId;
    @Column(name = "patient_profile_id", nullable = false)
    public String patientProfileId;
    @Column(nullable = false)
    public String title = "";
    @Column(nullable = false)
    public String model;
    @Column(name = "image_model", nullable = false)
    public String imageModel = "efficientnet-b0";    /** ai_chat | doctor_followup */
    @Column(nullable = false)
    public String kind = "ai_chat";
    @Column(name = "encounter_id")
    public String encounterId;
    @Column(name = "doctor_id")
    public String doctorId;
    /** null = lần khám chưa chốt (kênh đang mở); quá mốc này thì chỉ đọc. */
    @Column(name = "followup_until")
    public Instant followupUntil;
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;
    @Column(name = "updated_at", nullable = false)
    public Instant updatedAt;

    @PrePersist
    void onCreate() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
        createdAt = createdAt == null ? Instant.now() : createdAt;
        updatedAt = createdAt;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = Instant.now();
    }
}
