package vn.derma.clinical.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "encounters")
public class Encounter extends BaseEntity {

    /** Lần khám luôn bắt đầu từ lịch hẹn. */
    @Column(name = "appointment_id", nullable = false)
    public String appointmentId;
    @Column(name = "patient_profile_id", nullable = false)
    public String patientProfileId;
    @Column(name = "doctor_id")
    public String doctorId;
    /** open | closed */
    @Column(nullable = false)
    public String status = "open";
    @Column(name = "opened_at", nullable = false)
    public Instant openedAt;
    @Column(name = "closed_at")
    public Instant closedAt;
}
