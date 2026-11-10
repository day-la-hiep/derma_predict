package vn.derma.clinical.repository;

import java.util.Collection;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.clinical.entity.ClinicalProvenance;

public interface ClinicalProvenanceRepository extends JpaRepository<ClinicalProvenance, String> {

    List<ClinicalProvenance> findByFactIdInOrderByCreatedAtAsc(Collection<String> factIds);
}
