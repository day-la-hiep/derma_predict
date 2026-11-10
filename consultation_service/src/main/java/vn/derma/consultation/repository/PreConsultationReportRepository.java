package vn.derma.consultation.repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import vn.derma.consultation.entity.PreConsultationReport;

public interface PreConsultationReportRepository extends JpaRepository<PreConsultationReport, String> {

    Optional<PreConsultationReport> findByConsultationSessionId(String sessionId);

    List<PreConsultationReport> findByConsultationSessionIdIn(Collection<String> sessionIds);

    /** Báo cáo gần nhất của một hồ sơ bệnh nhân, trừ phiên `excludeSessionId` (phiên đang sinh báo cáo). */
    @Query("select r from PreConsultationReport r, ConsultationSession s, Conversation c where r.consultationSessionId = s.id and s.conversationId = c.id "
            + "and c.patientProfileId = :profileId and s.id <> :excludeSessionId order by r.createdAt desc limit 1")
    Optional<PreConsultationReport> findLatestOfProfile(@Param("profileId") String profileId, @Param("excludeSessionId") String excludeSessionId);
}
