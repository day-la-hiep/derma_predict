package vn.derma.consultation.service;

import java.io.ByteArrayInputStream;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;

import io.minio.GetPresignedObjectUrlArgs;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import io.minio.http.Method;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.config.DermaProperties;

/** Kho ảnh đính kèm tin nhắn trên MinIO. Bucket phải có sẵn: service không tự tạo bucket. */
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

    public void put(String key, byte[] data, String contentType) {
        try {
            minio.putObject(PutObjectArgs.builder().bucket(bucket).object(key)
                    .stream(new ByteArrayInputStream(data), data.length, -1).contentType(contentType).build());
        } catch (Exception e) {
            throw AppException.badGateway("Không lưu được tệp (kho tệp không phản hồi hoặc chưa có bucket): " + e.getMessage());
        }
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
