package vn.derma.clinical.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "clinical_facts")
public class ClinicalFact extends BaseEntity {

    @Column(name = "patient_profile_id", nullable = false)
    public String patientProfileId;
    /** Null = fact dài hạn (allergy/history/medication) của hồ sơ; còn lại thuộc một đợt bệnh. */
    @Column(name = "episode_id")
    public String episodeId;
    @Column(name = "fact_type", nullable = false)
    public String factType;
    @Column(nullable = false)
    public String label;
    @Column(name = "ontology_id")
    public String ontologyId;
    /** Giá trị hiện tại, sửa tại chỗ; lịch sử nằm ở `clinical_provenances`. */
    @Column(nullable = false)
    public String detail = "";
    @Column(name = "verified_at")
    public Instant verifiedAt;
    @Column(name = "verified_by_id")
    public String verifiedById;
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;
    @Column(name = "updated_at", nullable = false)
    public Instant updatedAt;
}
