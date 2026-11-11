package vn.derma.clinical.repository;

import java.util.Collection;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.clinical.entity.PatientImage;

public interface PatientImageRepository extends JpaRepository<PatientImage, String> {

    List<PatientImage> findByFinalizeReportIdIn(Collection<String> reportIds);
}
