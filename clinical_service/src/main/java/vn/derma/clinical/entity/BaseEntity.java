package vn.derma.clinical.entity;

import java.util.UUID;

import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PrePersist;

/** Entity JPA dùng field public (như các service Spring khác) để khỏi viết getter/setter; id sinh UUID khi lưu nếu chưa có. */
@MappedSuperclass
public abstract class BaseEntity {

    @Id
    public String id;

    @PrePersist
    void ensureId() {
        if (id == null) {
            id = UUID.randomUUID().toString();
        }
    }
}
