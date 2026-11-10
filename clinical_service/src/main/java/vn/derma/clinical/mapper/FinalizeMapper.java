package vn.derma.clinical.mapper;

import java.time.Instant;
import java.util.List;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

import vn.derma.clinical.dto.AppointmentDtos.PatientProfileDto;
import vn.derma.clinical.client.ConsultationClient.FileInfo;
import vn.derma.clinical.client.ConsultationClient.MessageInfo;
import vn.derma.clinical.client.IdentityClient.ProfileDetail;
import vn.derma.clinical.dto.AppointmentDtos.FileDto;
import vn.derma.clinical.dto.FinalizeDtos.CaseImage;
import vn.derma.clinical.dto.FinalizeDtos.DraftFactOutput;
import vn.derma.clinical.dto.FinalizeDtos.SnapshotFact;
import vn.derma.clinical.dto.FinalizeDtos.SnapshotMessage;
import vn.derma.clinical.dto.FinalizeDtos.SnapshotProfile;
import vn.derma.clinical.dto.FinalizeDtos.SnapshotProvenance;
import vn.derma.clinical.entity.ClinicalFact;
import vn.derma.clinical.entity.ClinicalProvenance;
import vn.derma.clinical.dto.FinalizeDtos.CaseInput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeReportItemOutput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeReportOutput;
import vn.derma.clinical.dto.FinalizeDtos.PatientFinalizeReportOutput;
import vn.derma.clinical.dto.FinalizeDtos.PatientImageOutput;
import vn.derma.clinical.dto.FinalizeDtos.Snapshot;
import vn.derma.clinical.entity.FinalizeReport;
import vn.derma.clinical.entity.PatientImage;

/** Báo cáo kết luận → DTO; snapshot (JSON, URL ảnh) và ảnh đã ký link do service dựng rồi truyền vào. */
@Mapper
public interface FinalizeMapper {

    @Mapping(target = "id", source = "report.id")
    @Mapping(target = "diagnosis", source = "report.diagnosis")
    @Mapping(target = "notes", source = "report.notes")
    @Mapping(target = "isReferenceCase", source = "report.referenceCase")
    @Mapping(target = "doctorName", source = "report.doctorName")
    @Mapping(target = "createdAt", source = "report.createdAt")
    @Mapping(target = "consultationSessionId", source = "report.consultationSessionId")
    @Mapping(target = "conversationId", source = "report.conversationId")
    @Mapping(target = "encounterId", source = "report.encounterId")
    @Mapping(target = "diagnosisCode", source = "report.diagnosisCode")
    @Mapping(target = "snapshot", source = "snapshot")
    @Mapping(target = "images", source = "images")
    FinalizeReportOutput toOutput(FinalizeReport report, Snapshot snapshot, List<PatientImageOutput> images);

    @Mapping(target = ".", source = "report")
    @Mapping(target = "id", source = "report.id")
    @Mapping(target = "patient", source = "patient")
    FinalizeReportItemOutput toItem(FinalizeReportOutput report, PatientProfileDto patient);

    PatientFinalizeReportOutput toPatientOutput(FinalizeReport report);

    @Mapping(target = "fileId", source = "storageKey")
    CaseImage toCaseImage(PatientImage image);

    @Mapping(target = "reportId", source = "report.id")
    @Mapping(target = "patientProfileId", source = "report.patientProfileId")
    @Mapping(target = "doctorId", source = "report.doctorId")
    @Mapping(target = "encounterId", source = "report.encounterId")
    @Mapping(target = "consultationSessionId", source = "report.consultationSessionId")
    @Mapping(target = "diagnosis", source = "report.diagnosis")
    @Mapping(target = "notes", source = "report.notes")
    @Mapping(target = "isReferenceCase", source = "report.referenceCase")
    @Mapping(target = "createdAt", source = "report.createdAt")
    @Mapping(target = "snapshot", source = "snapshot")
    @Mapping(target = "images", source = "images")
    CaseInput toCase(FinalizeReport report, Snapshot snapshot, List<CaseImage> images);

    @Mapping(target = "allergies", source = "allergies")
    @Mapping(target = "medicalHistory", source = "medicalHistory")
    SnapshotProfile toSnapshotProfile(ProfileDetail profile, String allergies, String medicalHistory);

    @Mapping(target = "factType", source = "fact.factType")
    @Mapping(target = "label", source = "fact.label")
    @Mapping(target = "detail", source = "fact.detail")
    @Mapping(target = "origin", source = "origin")
    @Mapping(target = "provenances", source = "provenances")
    SnapshotFact toSnapshotFact(ClinicalFact fact, String origin, List<SnapshotProvenance> provenances);

    @Mapping(target = "sourceFactId", source = "fact.id")
    @Mapping(target = "factType", source = "fact.factType")
    @Mapping(target = "label", source = "fact.label")
    @Mapping(target = "detail", source = "fact.detail")
    @Mapping(target = "origin", source = "origin")
    @Mapping(target = "provenances", source = "provenances")
    DraftFactOutput toDraftFact(ClinicalFact fact, String origin, List<SnapshotProvenance> provenances);

    @Mapping(target = "id", source = "image.id")
    @Mapping(target = "bodySite", source = "image.bodySite")
    @Mapping(target = "description", source = "image.description")
    @Mapping(target = "confirmedLabel", source = "image.confirmedLabel")
    @Mapping(target = "capturedAt", source = "image.capturedAt")
    @Mapping(target = "file", source = "file")
    PatientImageOutput toPatientImage(PatientImage image, FileDto file);

    @Mapping(target = "createdAt", ignore = true)
    @Mapping(target = "url", ignore = true)
    FileDto toFile(FileInfo file);

    SnapshotMessage toSnapshotMessage(MessageInfo message);

    /** Tin không lấy được từ consultation thì dùng đoạn trích đã chép cùng fact. */
    @Mapping(target = "id", source = "messageId")
    @Mapping(target = "sender", constant = "patient")
    @Mapping(target = "content", source = "quote")
    @Mapping(target = "files", expression = "java(java.util.List.of())")
    SnapshotMessage toSnapshotMessage(ClinicalProvenance provenance);

    default SnapshotProvenance toSnapshotProvenance(SnapshotMessage message) {
        return new SnapshotProvenance(message);
    }

    default String toText(Instant value) {
        return value == null ? null : value.toString();
    }
}
