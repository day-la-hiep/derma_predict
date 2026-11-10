package vn.derma.clinical.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "clinical_episodes")
public class ClinicalEpisode extends BaseEntity {

    @Column(name = "patient_profile_id", nullable = false)
    public String patientProfileId;
    /** Mã vùng (`BodySite`). */
    @Column(name = "body_site", nullable = false)
    public String bodySite;
    /** open | in_exam | closed | expired */
    @Column(nullable = false)
    public String status = "open";
    @Column(name = "last_conversation_id")
    public String lastConversationId;
    /** Báo cáo trước khám, ghép tất định từ dữ liệu đã lưu. */
    @Column(nullable = false)
    public String summary = "";
    @Column(name = "summary_at")
    public Instant summaryAt;
    public String urgency;
    /** JSON list. */
    @Column(name = "red_flags", nullable = false)
    public String redFlags = "[]";
    /** JSON list `[{storage_key, top_k: [{label, score}]}]`: kết quả CNN theo ảnh. */
    @Column(name = "image_predictions", nullable = false)
    public String imagePredictions = "[]";
    @Column(name = "model_version", nullable = false)
    public String modelVersion = "";
    @Column(name = "opened_at", nullable = false)
    public Instant openedAt;
    @Column(name = "updated_at", nullable = false)
    public Instant updatedAt;
    @Column(name = "closed_at")
    public Instant closedAt;
}
