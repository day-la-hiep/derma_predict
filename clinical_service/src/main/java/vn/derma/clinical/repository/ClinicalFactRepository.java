package vn.derma.clinical.repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import vn.derma.clinical.entity.ClinicalFact;

public interface ClinicalFactRepository extends JpaRepository<ClinicalFact, String> {

    /** Fact dài hạn của các hồ sơ (allergy/history/medication), cũ trước. */
    @Query("select f from ClinicalFact f where f.episodeId is null and f.patientProfileId in :profileIds order by f.createdAt asc")
    List<ClinicalFact> findLongTerm(@Param("profileIds") Collection<String> profileIds);

    List<ClinicalFact> findByEpisodeIdInOrderByCreatedAtAsc(Collection<String> episodeIds);

    /** Tìm fact hiện trạng theo (phạm vi, loại, nhãn không phân biệt hoa thường); `episodeId` null là phạm vi hồ sơ. */
    @Query("select f from ClinicalFact f where f.patientProfileId = :profileId and ((:episodeId is null and f.episodeId is null) or f.episodeId = :episodeId) "
            + "and f.factType = :factType and lower(f.label) = lower(:label)")
    Optional<ClinicalFact> findByScope(@Param("profileId") String profileId, @Param("episodeId") String episodeId,
            @Param("factType") String factType, @Param("label") String label);

    /** Fact dài hạn + fact của các đợt đang hoạt động, kèm vùng của đợt (null với fact dài hạn): agent nạp mỗi lượt. */
    @Query("select f, e.bodySite from ClinicalFact f left join ClinicalEpisode e on e.id = f.episodeId "
            + "where f.patientProfileId = :profileId and (f.episodeId is null or e.status in ('open', 'in_exam')) order by f.updatedAt asc")
    List<Object[]> findCurrentWithSite(@Param("profileId") String profileId);

    /** Fact dài hạn của hồ sơ + fact của một đợt: dữ liệu điền sẵn form chốt của lần khám. */
    @Query("select f from ClinicalFact f where f.patientProfileId = :profileId and (f.episodeId is null or f.episodeId = :episodeId) order by f.createdAt asc")
    List<ClinicalFact> findForExam(@Param("profileId") String profileId, @Param("episodeId") String episodeId);

    boolean existsByPatientProfileId(String profileId);
}
