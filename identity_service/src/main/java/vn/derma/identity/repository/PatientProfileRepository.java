package vn.derma.identity.repository;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.identity.entity.PatientProfile;

public interface PatientProfileRepository extends JpaRepository<PatientProfile, String> {

    List<PatientProfile> findByUserIdOrderByCreatedAtAsc(String userId);

    Optional<PatientProfile> findByIdAndUserId(String id, String userId);

    long countByUserId(String userId);
}
