package vn.derma.clinical.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "ai_hypotheses")
public class AiHypothesis extends BaseEntity {

    @Column(name = "episode_id", nullable = false)
    public String episodeId;
    @Column(nullable = false)
    public int rank;
    @Column(name = "diagnosis_code", nullable = false)
    public String diagnosisCode;
    @Column(nullable = false)
    public String disease;
    /** cao | vừa | thấp */
    @Column(nullable = false)
    public String confidence;
    /** JSON list `[{source, text}]`. */
    @Column(nullable = false)
    public String evidence = "[]";
    /** JSON list các điều còn thiếu để xác nhận/loại trừ. */
    @Column(nullable = false)
    public String missing = "[]";
}
