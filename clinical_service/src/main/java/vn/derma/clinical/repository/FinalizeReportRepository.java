package vn.derma.clinical.repository;

import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.clinical.entity.FinalizeReport;

public interface FinalizeReportRepository extends JpaRepository<FinalizeReport, String> {

    boolean existsByPatientProfileId(String patientProfileId);

    boolean existsByEncounterId(String encounterId);


    List<FinalizeReport> findByDoctorIdOrderByCreatedAtDesc(String doctorId);

    List<FinalizeReport> findByPatientProfileIdOrderByCreatedAtDesc(String patientProfileId);

    /** Cũ trước để knowledge reindex theo trang ổn định. */
    List<FinalizeReport> findAllByOrderByCreatedAtAsc(Pageable pageable);
}
