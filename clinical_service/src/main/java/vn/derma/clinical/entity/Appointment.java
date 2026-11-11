package vn.derma.clinical.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(name = "appointments")
public class Appointment extends BaseEntity {

    @Column(name = "patient_profile_id", nullable = false)
    public String patientProfileId;
    @Column(name = "episode_id", nullable = false)
    public String episodeId;
    @Column(name = "doctor_id")
    public String doctorId;
    /** Tên hiển thị lưu sẵn lúc bác sĩ nhận lịch. */
    @Column(name = "doctor_name")
    public String doctorName;
    @Column(name = "scheduled_at", nullable = false)
    public Instant scheduledAt;
    /** requested | confirmed | in_progress | done | cancelled | no_show */
    @Column(nullable = false)
    public String status = "requested";
    @Column(nullable = false)
    public String reason = "";
    @Column(name = "cancel_reason")
    public String cancelReason;
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;
}
