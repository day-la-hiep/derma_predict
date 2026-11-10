package vn.derma.clinical.repository;

import java.time.Instant;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import vn.derma.clinical.entity.Appointment;

public interface AppointmentRepository extends JpaRepository<Appointment, String> {

    /** Lịch hẹn còn hiệu lực của đợt (requested/confirmed/in_progress). */
    List<Appointment> findByEpisodeIdInAndStatusIn(java.util.Collection<String> episodeIds, java.util.Collection<String> statuses);

    List<Appointment> findByPatientProfileIdInOrderByScheduledAtDesc(java.util.Collection<String> profileIds);

    /**
     * Lịch của bác sĩ + lịch `requested` chưa ai nhận (mọi bác sĩ đều thấy để xác nhận). `start`/`end` không nhận null (Postgres không suy được
     * kiểu của tham số timestamp null): người gọi truyền mốc rất xa thay cho "không giới hạn".
     */
    @Query("select a from Appointment a where (a.doctorId = :doctorId or (a.doctorId is null and a.status = 'requested')) and a.scheduledAt >= :start "
            + "and a.scheduledAt < :end and (:status is null or a.status = :status) order by a.scheduledAt asc")
    List<Appointment> findForDoctor(@Param("doctorId") String doctorId, @Param("start") Instant start, @Param("end") Instant end, @Param("status") String status);

    boolean existsByEpisodeIdAndStatusIn(String episodeId, java.util.Collection<String> statuses);
}
