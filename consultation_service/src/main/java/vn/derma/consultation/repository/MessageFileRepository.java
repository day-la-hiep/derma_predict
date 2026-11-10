package vn.derma.consultation.repository;

import java.util.Collection;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.consultation.entity.MessageFile;

public interface MessageFileRepository extends JpaRepository<MessageFile, MessageFile.Key> {

    List<MessageFile> findByMessageIdIn(Collection<String> messageIds);
}
