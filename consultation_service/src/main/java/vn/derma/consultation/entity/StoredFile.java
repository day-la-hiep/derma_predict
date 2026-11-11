package vn.derma.consultation.entity;

import java.time.Instant;
import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.Table;

@Entity
@Table(name = "files")
public class StoredFile {

    @Id
    public String id;
    @Column(name = "file_name", nullable = false)
    public String fileName;
    @Column(name = "storage_key", nullable = false, unique = true)
    public String storageKey;
    @Column(name = "content_type")
    public String contentType;
    public Long size;
    @Column(name = "created_at", nullable = false)
    public Instant createdAt;

    @PrePersist
    void onCreate() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
        if (createdAt == null) {
            createdAt = Instant.now();
        }
    }
}
