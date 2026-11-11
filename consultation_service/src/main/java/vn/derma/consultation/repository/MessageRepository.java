package vn.derma.consultation.repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.consultation.entity.Message;

public interface MessageRepository extends JpaRepository<Message, String> {

    List<Message> findByConversationIdOrderByCreatedAtAsc(String conversationId);

    /** Lượt AI đang chạy hoặc đang chờ người dùng trả lời `ask_user`: thay cho khoá Redis `active_turn` của core. */
    boolean existsByConversationIdAndSenderAndStatusIn(String conversationId, String sender, Collection<String> statuses);

    Optional<Message> findFirstByConversationIdOrderByCreatedAtDesc(String conversationId);

    List<Message> findBySenderAndStatusInAndCreatedAtBefore(String sender, Collection<String> statuses, java.time.Instant before);

    Optional<Message> findFirstByConversationIdAndSenderAndStatusOrderByCreatedAtDesc(String conversationId, String sender, String status);

    Optional<Message> findFirstByConversationIdAndSenderAndStatusInOrderByCreatedAtDesc(String conversationId, String sender, Collection<String> statuses);
}
