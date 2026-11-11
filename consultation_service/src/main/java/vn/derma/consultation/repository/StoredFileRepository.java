package vn.derma.consultation.repository;

import java.util.Collection;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import vn.derma.consultation.entity.StoredFile;

public interface StoredFileRepository extends JpaRepository<StoredFile, String> {

    List<StoredFile> findByStorageKeyIn(Collection<String> storageKeys);
}
