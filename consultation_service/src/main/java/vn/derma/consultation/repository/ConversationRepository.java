package vn.derma.consultation.repository;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.consultation.entity.Conversation;

public interface ConversationRepository extends JpaRepository<Conversation, String> {

    List<Conversation> findByUserIdAndKindOrderByCreatedAtDesc(String userId, String kind);

    Optional<Conversation> findByEncounterId(String encounterId);

    List<Conversation> findByDoctorIdAndKindOrderByUpdatedAtDesc(String doctorId, String kind);

    Optional<Conversation> findByIdAndUserId(String id, String userId);

    boolean existsByPatientProfileId(String patientProfileId);
}
