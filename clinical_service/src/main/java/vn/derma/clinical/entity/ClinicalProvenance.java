package vn.derma.clinical.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

/** Nhật ký chỉ thêm: mỗi dòng là một lần một nguồn ghi nhận giá trị của fact. */
@Entity
@Table(name = "clinical_provenances")
public class ClinicalProvenance extends BaseEntity {

    @Column(name = "fact_id", nullable = false)
    public String factId;
    /** chat | doctor | profile */
    @Column(nullable = false)
    public String kind = "chat";
    /** Id tin ở consultation (id mềm); tin bị xoá thì `quote` vẫn đọc được. */
    @Column(name = "message_id")
    public String messageId;
    @Column(nullable = false)
    public String quote = "";
    @Column(name = "doctor_id")
    public String doctorId;
    @Column(name = "encounter_id")
    public String encounterId;
    @Column(nullable = false)
    public String detail = "";
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;
}
