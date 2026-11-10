package vn.derma.consultation.repository;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import vn.derma.consultation.entity.ConsultationSession;

public interface ConsultationSessionRepository extends JpaRepository<ConsultationSession, String> {

    /** Phiên chưa đóng của hội thoại (tối đa một). */
    Optional<ConsultationSession> findFirstByConversationIdAndStatusNot(String conversationId, String status);

    /** Bác sĩ chỉ thấy ca chờ nhận và ca của chính mình; `status` null hoặc `all` là mọi trạng thái. */
    @Query("select s from ConsultationSession s where (s.status = 'pending' or s.doctorId = :doctorId) and (:status is null or s.status = :status) order by s.requestedAt desc")
    List<ConsultationSession> findVisibleToDoctor(@Param("doctorId") String doctorId, @Param("status") String status);

    /** Phiên gần nhất của hội thoại mà bác sĩ được xem: đang chờ nhận hoặc do chính bác sĩ phụ trách. */
    @Query("select s from ConsultationSession s where s.conversationId = :conversationId and (s.status = 'pending' or s.doctorId = :doctorId) order by s.requestedAt desc limit 1")
    Optional<ConsultationSession> findLatestVisibleToDoctor(@Param("conversationId") String conversationId, @Param("doctorId") String doctorId);
}
