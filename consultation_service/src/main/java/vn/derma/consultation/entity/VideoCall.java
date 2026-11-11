package vn.derma.consultation.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

@Entity
@Table(name = "video_calls")
public class VideoCall {

    @Id
    public String id;
    /** Chỉ còn ở cuộc gọi của phiên tư vấn cũ; cuộc gọi mới null. */
    @Column(name = "consultation_session_id")
    public String consultationSessionId;
    @Column(name = "conversation_id")
    public String conversationId;
    @Column(name = "room_id", nullable = false, unique = true)
    public String roomId;
    /** pending | ongoing | ended */
    @Column(nullable = false)
    public String status = "pending";
    @Column(name = "started_at")
    public Instant startedAt;
    @Column(name = "ended_at")
    public Instant endedAt;
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;

    @PrePersist
    void onCreate() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
        if (roomId == null) {
            roomId = "room-" + UUID.randomUUID();
        }
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }
}
