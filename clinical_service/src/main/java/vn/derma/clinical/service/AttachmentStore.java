package vn.derma.clinical.service;

import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

import io.minio.GetPresignedObjectUrlArgs;
import io.minio.MinioClient;
import io.minio.http.Method;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.config.DermaProperties;

/** Chỉ tạo link tạm để xem ảnh đính kèm (bucket của consultation); chỉ đọc, không ghi, không tạo bucket. */
@Component
public class AttachmentStore {

    private static final int PRESIGNED_DAYS = 7;

    private final MinioClient minio;
    private final String bucket;

    public AttachmentStore(DermaProperties properties) {
        DermaProperties.Minio config = properties.minio();
        this.bucket = config.bucket();
        this.minio = MinioClient.builder()
                .endpoint((config.secure() ? "https://" : "http://") + config.endpoint())
                .credentials(config.accessKey(), config.secretKey())
                .build();
    }

    public String presignedUrl(String key) {
        try {
            return minio.getPresignedObjectUrl(GetPresignedObjectUrlArgs.builder().method(Method.GET).bucket(bucket).object(key)
                    .expiry(PRESIGNED_DAYS, TimeUnit.DAYS).build());
        } catch (Exception e) {
            throw AppException.badGateway("Không tạo được liên kết tệp: " + e.getMessage());
        }
    }
}
