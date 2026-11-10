package vn.derma.consultation.controller;

import lombok.AllArgsConstructor;
import java.io.IOException;
import java.net.URI;
import java.util.Set;
import java.util.UUID;

import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import vn.derma.consultation.common.AppException;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.common.CurrentUser;
import vn.derma.consultation.dto.MessageDtos.FileDto;
import vn.derma.consultation.entity.StoredFile;
import vn.derma.consultation.repository.StoredFileRepository;
import vn.derma.consultation.service.AttachmentStore;
import vn.derma.consultation.service.MessageService;

/** Upload ảnh đính kèm tin nhắn (chỉ nhận ảnh: là đầu vào của CNN phân loại da). Trả thẳng `FileDto`, không bọc `data` như core. */
@RestController
@RequestMapping("/api/v1")
@AllArgsConstructor
public class UploadController {

    private static final Set<String> ALLOWED_IMAGE_TYPES = Set.of("image/jpeg", "image/png", "image/webp");
    private static final long MAX_BYTES = 10L * 1024 * 1024;

    private final AttachmentStore store;
    private final StoredFileRepository files;
    private final MessageService messages;

    @PostMapping("/uploads")
    FileDto upload(@CurrentUser AuthenticatedUser user, @RequestParam("file") MultipartFile file) throws IOException {
        String type = file.getContentType();
        if (type == null || !ALLOWED_IMAGE_TYPES.contains(type)) {
            throw AppException.badRequest("Định dạng không hỗ trợ: " + type);
        }
        if (file.getSize() > MAX_BYTES) {
            throw AppException.badRequest("File vượt quá " + MAX_BYTES / (1024 * 1024) + "MB.");
        }
        String original = file.getOriginalFilename();
        String suffix = original != null && original.contains(".") ? original.substring(original.lastIndexOf('.') + 1) : "jpg";
        String key = UUID.randomUUID().toString().replace("-", "") + "." + suffix;
        store.put(key, file.getBytes(), type);
        StoredFile saved = new StoredFile();
        saved.fileName = original == null || original.isBlank() ? key : original;
        saved.storageKey = key;
        saved.contentType = type;
        saved.size = file.getSize();
        return messages.toFileDto(files.save(saved));
    }

    // FE hiển thị ảnh bằng <img src=/api/v1/files/{id}/view>; chuyển hướng sang URL ký sẵn của MinIO
    @GetMapping("/files/{id}/view")
    ResponseEntity<Void> view(@PathVariable String id) {
        StoredFile file = files.findById(id).orElseThrow(() -> AppException.notFound("tệp"));
        return ResponseEntity.status(302).header(HttpHeaders.LOCATION, URI.create(store.presignedUrl(file.storageKey)).toString()).build();
    }
}
