package vn.derma.clinical.repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import vn.derma.clinical.entity.ClinicalEpisode;

public interface ClinicalEpisodeRepository extends JpaRepository<ClinicalEpisode, String> {

    /** Đợt đang hoạt động (open/in_exam) của vùng; tối đa một. */
    @Query("select e from ClinicalEpisode e where e.patientProfileId = :profileId and e.bodySite = :site and e.status in ('open', 'in_exam')")
    Optional<ClinicalEpisode> findActive(@Param("profileId") String profileId, @Param("site") String site);

    @Query("select e from ClinicalEpisode e where e.patientProfileId = :profileId and e.status in ('open', 'in_exam') order by e.updatedAt desc")
    List<ClinicalEpisode> findActiveOfProfile(@Param("profileId") String profileId);

    List<ClinicalEpisode> findByPatientProfileIdOrderByUpdatedAtDesc(String profileId);

    /** Đợt đang hoạt động mà hội thoại này cập nhật gần nhất. */
    @Query("select e from ClinicalEpisode e where e.lastConversationId = :conversationId and e.status in ('open', 'in_exam')")
    List<ClinicalEpisode> findActiveOfConversation(@Param("conversationId") String conversationId);

    boolean existsByPatientProfileId(String profileId);

    List<ClinicalEpisode> findAllByIdIn(Collection<String> ids);
}
