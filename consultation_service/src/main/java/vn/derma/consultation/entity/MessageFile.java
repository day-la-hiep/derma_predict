package vn.derma.consultation.entity;

import java.io.Serializable;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;

@Entity
@Table(name = "message_files")
@IdClass(MessageFile.Key.class)
public class MessageFile {

    public record Key(String messageId, String fileId) implements Serializable {
    }

    @Id
    @Column(name = "message_id")
    public String messageId;
    @Id
    @Column(name = "file_id")
    public String fileId;
}
