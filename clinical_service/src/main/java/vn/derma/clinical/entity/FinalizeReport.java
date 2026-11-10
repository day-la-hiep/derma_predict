package vn.derma.clinical.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

/** Báo cáo kết luận do bác sĩ chốt; không sửa sau khi chốt (snapshot bất biến). */
@Entity
@Table(name = "finalize_reports")
public class FinalizeReport extends BaseEntity {

    @Column(name = "patient_profile_id", nullable = false)
    public String patientProfileId;
    @Column(name = "doctor_id")
    public String doctorId;
    @Column(name = "doctor_name")
    public String doctorName;
    @Column(nullable = false)
    public String diagnosis;
    @Column(nullable = false)
    public String notes = "";
    @Column(name = "is_reference_case", nullable = false)
    public boolean referenceCase;
    @Column(name = "consultation_session_id")
    public String consultationSessionId;
    @Column(name = "conversation_id")
    public String conversationId;
    @Column(name = "encounter_id")
    public String encounterId;
    @Column(name = "diagnosis_code")
    public String diagnosisCode;
    /** JSON `FinalizeReportSnapshot` (hồ sơ, nhận định, fact kèm nguồn); null với báo cáo cũ. */
    public String snapshot;
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;
}
