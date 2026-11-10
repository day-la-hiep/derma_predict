package vn.derma.clinical.mapper;

import java.time.Instant;
import java.util.List;

import org.mapstruct.Mapper;
import org.mapstruct.Mapping;

import vn.derma.clinical.dto.AppointmentDtos.AppointmentOutput;
import vn.derma.clinical.dto.AppointmentDtos.ClinicalFactOutput;
import vn.derma.clinical.dto.AppointmentDtos.DoctorAppointmentDetailOutput;
import vn.derma.clinical.dto.AppointmentDtos.DoctorAppointmentItemOutput;
import vn.derma.clinical.dto.AppointmentDtos.DoctorEpisodeOutput;
import vn.derma.clinical.dto.AppointmentDtos.PatientEpisodeOutput;
import vn.derma.clinical.client.ConsultationClient.MessageInfo;
import vn.derma.clinical.dto.AppointmentDtos.HypothesisEvidenceOutput;
import vn.derma.clinical.dto.AppointmentDtos.HypothesisOutput;
import vn.derma.clinical.dto.AppointmentDtos.PatientProfileDto;
import vn.derma.clinical.dto.AppointmentDtos.SourceMessageOutput;
import vn.derma.clinical.client.IdentityClient.ProfileDetail;
import vn.derma.clinical.dto.AppointmentDtos.ImagePredictionOutput;
import vn.derma.clinical.entity.AiHypothesis;
import vn.derma.clinical.entity.ClinicalFact;
import vn.derma.clinical.entity.ClinicalProvenance;
import vn.derma.clinical.entity.Appointment;
import vn.derma.clinical.entity.ClinicalEpisode;
import vn.derma.clinical.entity.Encounter;

/** Ghép entity thành DTO lịch hẹn; các trường dẫn xuất (nhãn vùng, JSON) vẫn do service tính rồi truyền vào. */
@Mapper
public interface AppointmentMapper {

    @Mapping(target = "id", source = "appointment.id")
    @Mapping(target = "episodeId", source = "appointment.episodeId")
    @Mapping(target = "patientProfileId", source = "appointment.patientProfileId")
    @Mapping(target = "bodySite", source = "episode.bodySite")
    @Mapping(target = "bodySiteLabel", expression = "java(vn.derma.clinical.common.ClinicalCodes.BODY_SITE_LABELS.getOrDefault(episode.bodySite, episode.bodySite))")
    @Mapping(target = "doctorId", source = "appointment.doctorId")
    @Mapping(target = "doctorName", source = "appointment.doctorName")
    @Mapping(target = "scheduledAt", source = "appointment.scheduledAt")
    @Mapping(target = "status", source = "appointment.status")
    @Mapping(target = "reason", source = "appointment.reason")
    @Mapping(target = "cancelReason", source = "appointment.cancelReason")
    @Mapping(target = "createdAt", source = "appointment.createdAt")
    @Mapping(target = "encounterId", source = "encounter.id")
    AppointmentOutput toOutput(Appointment appointment, ClinicalEpisode episode, Encounter encounter);

    @Mapping(target = ".", source = "appointment")
    @Mapping(target = "id", source = "appointment.id")
    DoctorAppointmentItemOutput toItem(AppointmentOutput appointment, PatientProfileDto patient, String topHypothesis);

    @Mapping(target = ".", source = "item")
    // các tên trùng giữa lịch hẹn và đợt bệnh phải chỉ rõ nguồn là lịch hẹn
    @Mapping(target = "id", source = "item.id")
    @Mapping(target = "bodySite", source = "item.bodySite")
    @Mapping(target = "bodySiteLabel", source = "item.bodySiteLabel")
    @Mapping(target = "status", source = "item.status")
    @Mapping(target = "episode", source = "episode")
    DoctorAppointmentDetailOutput toDetail(DoctorAppointmentItemOutput item, DoctorEpisodeOutput episode, List<ClinicalFactOutput> longTermFacts,
            List<PatientEpisodeOutput> otherEpisodes);

    @Mapping(target = "diagnosisLabel", expression = "java(vn.derma.clinical.common.ClinicalCodes.DIAGNOSIS_CODE_LABELS.getOrDefault(hypothesis.diagnosisCode, hypothesis.diagnosisCode))")
    @Mapping(target = "evidence", source = "evidence")
    @Mapping(target = "missing", source = "missing")
    HypothesisOutput toHypothesis(AiHypothesis hypothesis, List<HypothesisEvidenceOutput> evidence, List<String> missing);

    @Mapping(target = "id", source = "fact.id")
    @Mapping(target = "templateLabel", source = "fact.label")
    @Mapping(target = "factType", source = "fact.factType")
    @Mapping(target = "detail", source = "fact.detail")
    @Mapping(target = "verifiedAt", source = "fact.verifiedAt")
    @Mapping(target = "createdAt", source = "fact.createdAt")
    @Mapping(target = "updatedAt", source = "fact.updatedAt")
    @Mapping(target = "sourceMessageIds", source = "sourceMessageIds")
    @Mapping(target = "sourceMessages", source = "sourceMessages")
    ClinicalFactOutput toFact(ClinicalFact fact, List<String> sourceMessageIds, List<SourceMessageOutput> sourceMessages);

    SourceMessageOutput toSourceMessage(MessageInfo message);

    /** Tin không lấy được từ consultation thì dùng đoạn trích đã chép cùng fact. */
    @Mapping(target = "id", source = "messageId")
    @Mapping(target = "sender", constant = "patient")
    @Mapping(target = "content", source = "quote")
    SourceMessageOutput toSourceMessage(ClinicalProvenance provenance);

    @Mapping(target = "allergies", source = "allergies")
    @Mapping(target = "medicalHistory", source = "medicalHistory")
    PatientProfileDto toPatient(ProfileDetail profile, String allergies, String medicalHistory);

    @Mapping(target = "bodySiteLabel", expression = "java(vn.derma.clinical.common.ClinicalCodes.BODY_SITE_LABELS.getOrDefault(episode.bodySite, episode.bodySite))")
    @Mapping(target = "hypothesesLocked", expression = "java(!\"open\".equals(episode.status))")
    @Mapping(target = "disclaimer", expression = "java(vn.derma.clinical.dto.AppointmentDtos.AI_DISCLAIMER)")
    @Mapping(target = "redFlags", source = "redFlags")
    @Mapping(target = "hypotheses", source = "hypotheses")
    @Mapping(target = "facts", source = "facts")
    @Mapping(target = "imagePredictions", source = "imagePredictions")
    DoctorEpisodeOutput toDoctorEpisode(ClinicalEpisode episode, List<String> redFlags, List<HypothesisOutput> hypotheses, List<ClinicalFactOutput> facts,
            List<ImagePredictionOutput> imagePredictions);

    @Mapping(target = "bodySiteLabel", expression = "java(vn.derma.clinical.common.ClinicalCodes.BODY_SITE_LABELS.getOrDefault(episode.bodySite, episode.bodySite))")
    @Mapping(target = "id", source = "episode.id")
    @Mapping(target = "bodySite", source = "episode.bodySite")
    @Mapping(target = "status", source = "episode.status")
    @Mapping(target = "updatedAt", source = "episode.updatedAt")
    @Mapping(target = "facts", source = "facts")
    @Mapping(target = "bookable", source = "bookable")
    @Mapping(target = "notBookableReason", source = "notBookableReason")
    @Mapping(target = "appointment", source = "appointment")
    PatientEpisodeOutput toPatientEpisode(ClinicalEpisode episode, List<String> facts, boolean bookable, String notBookableReason, AppointmentOutput appointment);

    default String toText(Instant value) {
        return value == null ? null : value.toString();
    }
}
