package vn.derma.consultation.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

@Entity
@Table(name = "messages")
public class Message {

    @Id
    public String id;
    @Column(name = "conversation_id", nullable = false)
    public String conversationId;
    /** patient | ai | doctor */
    @Column(nullable = false)
    public String sender;
    @Column(name = "message_type", nullable = false)
    public String messageType = "text";
    @Column(name = "video_call_id")
    public String videoCallId;
    @Column(name = "consultation_session_id")
    public String consultationSessionId;
    @Column(nullable = false)
    public String content = "";
    /** pending | queued | streaming | done | question */
    @Column(nullable = false)
    public String status;
    /** JSON dạng chuỗi (`reasoning`, `choice`...), không truy vấn bên trong. */
    @Column(name = "metadata")
    public String metadata;
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
