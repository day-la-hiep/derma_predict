package vn.derma.consultation.repository;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.consultation.entity.VideoCall;

public interface VideoCallRepository extends JpaRepository<VideoCall, String> {

    /** Cuộc gọi chưa kết thúc (đang đổ chuông hoặc đang nói) của kênh. */
    Optional<VideoCall> findFirstByConversationIdAndStatusNot(String conversationId, String status);
}
