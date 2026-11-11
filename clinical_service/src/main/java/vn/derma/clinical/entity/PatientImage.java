package vn.derma.clinical.entity;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

/** Ảnh bệnh bác sĩ gắn vào báo cáo kết luận; file nằm ở bucket ảnh đính kèm, chỉ lưu khoá và tên. */
@Entity
@Table(name = "patient_images")
public class PatientImage extends BaseEntity {

    @Column(name = "finalize_report_id", nullable = false)
    public String finalizeReportId;
    @Column(name = "storage_key", nullable = false)
    public String storageKey;
    @Column(name = "file_name", nullable = false)
    public String fileName = "";
    @Column(name = "content_type")
    public String contentType;
    @Column(name = "body_site", nullable = false)
    public String bodySite = "";
    @Column(nullable = false)
    public String description = "";
    @Column(name = "confirmed_label")
    public String confirmedLabel;
    @Column(name = "captured_at")
    public Instant capturedAt;
}
