package vn.derma.clinical.service;

import lombok.AllArgsConstructor;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import vn.derma.clinical.client.ConsultationClient;
import vn.derma.clinical.client.IdentityClient;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.common.ClinicalCodes;
import vn.derma.clinical.dto.AppointmentDtos.AppointmentOutput;
import vn.derma.clinical.dto.AppointmentDtos.BookAppointmentInput;
import vn.derma.clinical.dto.AppointmentDtos.ClinicalFactOutput;
import vn.derma.clinical.dto.AppointmentDtos.DoctorAppointmentDetailOutput;
import vn.derma.clinical.dto.AppointmentDtos.DoctorAppointmentItemOutput;
import vn.derma.clinical.dto.AppointmentDtos.DoctorEpisodeOutput;
import vn.derma.clinical.dto.AppointmentDtos.FileDto;
import vn.derma.clinical.dto.AppointmentDtos.HypothesisEvidenceOutput;
import vn.derma.clinical.dto.AppointmentDtos.HypothesisOutput;
import vn.derma.clinical.dto.AppointmentDtos.ImagePredictionOutput;
import vn.derma.clinical.dto.AppointmentDtos.LabelScoreOutput;
import vn.derma.clinical.dto.AppointmentDtos.PatientEpisodeOutput;
import vn.derma.clinical.dto.AppointmentDtos.PatientProfileDto;
import vn.derma.clinical.dto.AppointmentDtos.SourceMessageOutput;
import vn.derma.clinical.entity.AiHypothesis;
import vn.derma.clinical.entity.Appointment;
import vn.derma.clinical.entity.ClinicalEpisode;
import vn.derma.clinical.entity.ClinicalFact;
import vn.derma.clinical.entity.ClinicalProvenance;
import vn.derma.clinical.entity.Encounter;
import vn.derma.clinical.mapper.AppointmentMapper;
import vn.derma.clinical.repository.AiHypothesisRepository;
import vn.derma.clinical.repository.AppointmentRepository;
import vn.derma.clinical.repository.ClinicalEpisodeRepository;
import vn.derma.clinical.repository.ClinicalFactRepository;
import vn.derma.clinical.repository.ClinicalProvenanceRepository;
import vn.derma.clinical.repository.EncounterRepository;

/** Đặt lịch khám cho một đợt bệnh đã đủ thông tin, và bác sĩ bắt đầu khám từ lịch hẹn. */
@Service
@AllArgsConstructor
public class AppointmentService {

    private static final Set<String> ACTIVE = Set.of("requested", "confirmed", "in_progress");
    private static final Instant FAR_PAST = Instant.EPOCH;
    private static final Instant FAR_FUTURE = Instant.parse("9999-12-31T00:00:00Z");
    private static final TypeReference<List<Map<String, Object>>> LIST_OF_MAPS = new TypeReference<>() {
    };
    private static final TypeReference<List<String>> LIST_OF_STRINGS = new TypeReference<>() {
    };

    private final AppointmentRepository appointments;
    private final EncounterRepository encounters;
    private final ClinicalEpisodeRepository episodes;
    private final AiHypothesisRepository hypotheses;
    private final ClinicalFactRepository facts;
    private final ClinicalProvenanceRepository provenances;
    private final ClinicalRecordService records;
    private final IdentityClient identity;
    private final ConsultationClient consultation;
    private final AttachmentStore store;
    private final ObjectMapper json;
    private final AppointmentMapper mapper;

    // ---------------------------------------------------------------- bệnh nhân

    public List<PatientEpisodeOutput> listEpisodes(String userId, String profileId) {
        ownProfile(userId, profileId);
        return patientEpisodes(episodes.findActiveOfProfile(profileId));
    }

    @Transactional
    public AppointmentOutput book(String userId, BookAppointmentInput input) {
        ownProfile(userId, input.patientProfileId());
        ClinicalEpisode episode = episodes.findById(input.episodeId()).filter(e -> e.patientProfileId.equals(input.patientProfileId()))
                .orElseThrow(() -> AppException.notFound("đợt bệnh của hồ sơ này"));
        String reason = notBookableReason(episode);
        if (reason != null) {
            throw AppException.invalid(reason);
        }
        if (!input.scheduledAt().isAfter(Instant.now())) {
            throw AppException.invalid("Thời gian hẹn phải ở tương lai.");
        }
        Appointment appointment = new Appointment();
        appointment.patientProfileId = episode.patientProfileId;
        appointment.episodeId = episode.id;
        appointment.scheduledAt = input.scheduledAt();
        appointment.reason = input.reason() == null ? "" : input.reason().trim();
        appointment.createdAt = Instant.now();
        appointments.save(appointment);
        refreshSummary(episode, true);
        return output(appointment, episode, null);
    }

    public List<AppointmentOutput> listMine(String userId) {
        List<String> profileIds = identity.listProfilesOfUser(userId).stream().map(IdentityClient.ProfileDetail::id).toList();
        if (profileIds.isEmpty()) {
            return List.of();
        }
        List<Appointment> mine = appointments.findByPatientProfileIdInOrderByScheduledAtDesc(profileIds);
        Map<String, ClinicalEpisode> byId = episodesById(mine.stream().map(a -> a.episodeId).toList());
        Map<String, Encounter> encounterByAppointment = encountersOf(mine);
        return mine.stream().map(a -> output(a, byId.get(a.episodeId), encounterByAppointment.get(a.id))).toList();
    }

    @Transactional
    public AppointmentOutput cancelMine(String userId, String appointmentId, String reason) {
        Appointment appointment = get(appointmentId);
        ownProfile(userId, appointment.patientProfileId);
        return cancel(appointment, reason);
    }

    // ---------------------------------------------------------------- bác sĩ

    public List<DoctorAppointmentItemOutput> listForDoctor(String doctorId, Instant start, Instant end, String status) {
        List<Appointment> found = appointments.findForDoctor(doctorId, start == null ? FAR_PAST : start, end == null ? FAR_FUTURE : end, status);
        Map<String, ClinicalEpisode> episodeById = episodesById(found.stream().map(a -> a.episodeId).toList());
        Map<String, List<AiHypothesis>> hypothesesByEpisode = hypothesesOf(episodeById.keySet());
        Map<String, IdentityClient.ProfileDetail> profiles = identity.getProfiles(found.stream().map(a -> a.patientProfileId).collect(Collectors.toSet()));
        Map<String, List<ClinicalFact>> longTerm = longTermOf(profiles.keySet());
        Map<String, Encounter> encounterByAppointment = encountersOf(found);
        return found.stream().map(a -> item(a, episodeById.get(a.episodeId), encounterByAppointment.get(a.id), profiles.get(a.patientProfileId),
                longTerm.getOrDefault(a.patientProfileId, List.of()), hypothesesByEpisode.getOrDefault(a.episodeId, List.of()))).toList();
    }

    public DoctorAppointmentDetailOutput detail(String doctorId, String appointmentId) {
        return detailOf(doctorAppointment(doctorId, appointmentId));
    }

    @Transactional
    public DoctorAppointmentDetailOutput confirm(String doctorId, String appointmentId) {
        Appointment appointment = doctorAppointment(doctorId, appointmentId);
        if (!"requested".equals(appointment.status)) {
            throw AppException.conflict("Chỉ xác nhận được lịch hẹn đang chờ.");
        }
        appointment.status = "confirmed";
        appointment.doctorId = doctorId;
        appointment.doctorName = identity.getUser(doctorId).map(IdentityClient.UserRef::fullName).orElse(null);
        appointments.save(appointment);
        return detailOf(appointment);
    }

    @Transactional
    public DoctorAppointmentDetailOutput cancelByDoctor(String doctorId, String appointmentId, String reason) {
        Appointment appointment = doctorAppointment(doctorId, appointmentId);
        cancel(appointment, reason);
        return detailOf(appointment);
    }

    @Transactional
    public DoctorAppointmentDetailOutput markNoShow(String doctorId, String appointmentId) {
        Appointment appointment = doctorAppointment(doctorId, appointmentId);
        if (!"confirmed".equals(appointment.status)) {
            throw AppException.conflict("Chỉ đánh dấu \"không đến\" cho lịch đã xác nhận.");
        }
        appointment.status = "no_show";
        appointments.save(appointment);
        return detailOf(appointment);
    }

    @Transactional
    public DoctorAppointmentDetailOutput changeEpisode(String doctorId, String appointmentId, String episodeId) {
        Appointment appointment = doctorAppointment(doctorId, appointmentId);
        if (!"requested".equals(appointment.status) && !"confirmed".equals(appointment.status)) {
            throw AppException.conflict("Chỉ đổi được đợt bệnh trước khi bắt đầu khám.");
        }
        ClinicalEpisode episode = episodes.findById(episodeId).filter(e -> e.patientProfileId.equals(appointment.patientProfileId))
                .orElseThrow(() -> AppException.notFound("đợt bệnh của bệnh nhân này"));
        if (!episode.id.equals(appointment.episodeId)) {
            String reason = notBookableReason(episode);
            if (reason != null) {
                throw AppException.invalid(reason);
            }
            appointment.episodeId = episode.id;
            appointments.save(appointment);
            refreshSummary(episode, true);
        }
        return detailOf(appointment);
    }

    /** Một transaction: lịch thành in_progress, đợt thành in_exam (khoá giả thuyết), tạo lần khám. */
    @Transactional
    public DoctorAppointmentDetailOutput startEncounter(String doctorId, String appointmentId) {
        Appointment appointment = doctorAppointment(doctorId, appointmentId);
        if (!"confirmed".equals(appointment.status) || !doctorId.equals(appointment.doctorId)) {
            throw AppException.conflict("Chỉ bắt đầu khám được lịch bạn đã xác nhận.");
        }
        ClinicalEpisode episode = episode(appointment.episodeId);
        if (!"open".equals(episode.status)) {
            throw AppException.conflict("Đợt bệnh không còn mở, hãy đổi sang đợt khác hoặc huỷ lịch.");
        }
        refreshSummary(episode, true);
        episode.status = "in_exam";
        episodes.save(episode);
        appointment.status = "in_progress";
        appointments.save(appointment);
        Encounter encounter = new Encounter();
        encounter.appointmentId = appointment.id;
        encounter.patientProfileId = appointment.patientProfileId;
        encounter.doctorId = doctorId;
        encounter.openedAt = Instant.now();
        encounters.save(encounter);
        // gọi mạng sau khi commit để không giữ kết nối DB; lỗi thì kênh được tạo bù lúc chốt kết luận
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                consultation.openFollowupChannel(encounter.id, appointment.patientProfileId, doctorId);
            }
        });
        return detailOf(appointment);
    }

    // ---------------------------------------------------------------- dùng chung với báo cáo kết luận

    public ClinicalEpisode episode(String episodeId) {
        return episodes.findById(episodeId).orElseThrow(() -> AppException.notFound("đợt bệnh"));
    }

    public List<HypothesisOutput> hypothesisOutputs(String episodeId) {
        return hypotheses.findByEpisodeIdOrderByRankAsc(episodeId).stream().map(this::hypothesisOutput).toList();
    }

    public DoctorEpisodeOutput doctorEpisode(ClinicalEpisode episode, List<ClinicalFact> episodeFacts) {
        return mapper.toDoctorEpisode(episode, readStrings(episode.redFlags), hypothesisOutputs(episode.id), factOutputs(episodeFacts), imagePredictions(episode));
    }

    public List<ImagePredictionOutput> imagePredictions(ClinicalEpisode episode) {
        List<ImagePredictionOutput> out = new ArrayList<>();
        for (Map<String, Object> p : readMaps(episode.imagePredictions)) {
            String key = String.valueOf(p.get("storage_key"));
            List<LabelScoreOutput> topK = new ArrayList<>();
            if (p.get("top_k") instanceof List<?> items) {
                for (Object item : items) {
                    if (item instanceof Map<?, ?> t) {
                        String label = String.valueOf(t.get("label"));
                        topK.add(new LabelScoreOutput(label, codeLabel(label), t.get("score") instanceof Number n ? n.doubleValue() : 0));
                    }
                }
            }
            out.add(new ImagePredictionOutput(key, fileDto(key), topK));
        }
        return out;
    }

    public FileDto fileDto(String storageKey) {
        String name = storageKey.substring(storageKey.lastIndexOf('/') + 1);
        String ext = name.contains(".") ? name.substring(name.lastIndexOf('.') + 1).toLowerCase() : "";
        String type = switch (ext) {
            case "png" -> "image/png";
            case "webp" -> "image/webp";
            case "jpg", "jpeg" -> "image/jpeg";
            default -> "application/octet-stream";
        };
        return new FileDto(name, storageKey, type, null, null, store.presignedUrl(storageKey));
    }

    /** Fact kèm tin nguồn: nội dung tin lấy từ consultation, không lấy được thì dùng đoạn trích đã chép lúc ghi. */
    public List<ClinicalFactOutput> factOutputs(List<ClinicalFact> list) {
        if (list.isEmpty()) {
            return List.of();
        }
        Map<String, List<ClinicalProvenance>> byFact = provenances.findByFactIdInOrderByCreatedAtAsc(list.stream().map(f -> f.id).toList()).stream()
                .filter(p -> p.messageId != null).collect(Collectors.groupingBy(p -> p.factId, LinkedHashMap::new, Collectors.toList()));
        Map<String, ConsultationClient.MessageInfo> messages = consultation.getMessages(byFact.values().stream().flatMap(Collection::stream).map(p -> p.messageId)
                .collect(Collectors.toCollection(LinkedHashSet::new)));
        return list.stream().map(f -> {
            Map<String, SourceMessageOutput> sources = new LinkedHashMap<>();
            for (ClinicalProvenance p : byFact.getOrDefault(f.id, List.of())) {
                ConsultationClient.MessageInfo m = messages.get(p.messageId);
                sources.putIfAbsent(p.messageId, m != null ? mapper.toSourceMessage(m) : mapper.toSourceMessage(p));
            }
            return mapper.toFact(f, List.copyOf(sources.keySet()), List.copyOf(sources.values()));
        }).toList();
    }

    public PatientProfileDto patientDto(String profileId, IdentityClient.ProfileDetail profile, List<ClinicalFact> longTerm) {
        String allergies = ClinicalRecordService.longTermText(longTerm, "allergy"), history = ClinicalRecordService.longTermText(longTerm, "history");
        if (profile == null) {
            return new PatientProfileDto(profileId, "Bệnh nhân", "", "male", "self", null, allergies, history);
        }
        return mapper.toPatient(profile, allergies, history);
    }

    public Map<String, List<ClinicalFact>> longTermOf(Collection<String> profileIds) {
        Map<String, List<ClinicalFact>> out = new HashMap<>();
        if (!profileIds.isEmpty()) {
            facts.findLongTerm(profileIds).forEach(f -> out.computeIfAbsent(f.patientProfileId, k -> new ArrayList<>()).add(f));
        }
        return out;
    }

    public String siteLabel(String site) {
        return ClinicalCodes.BODY_SITE_LABELS.getOrDefault(site, site);
    }

    public String codeLabel(String code) {
        return ClinicalCodes.DIAGNOSIS_CODE_LABELS.getOrDefault(code, code);
    }

    // ---------------------------------------------------------------- nội bộ

    private void ownProfile(String userId, String profileId) {
        identity.resolveProfile(userId, profileId).orElseThrow(() -> AppException.notFound("hồ sơ bệnh nhân"));
    }

    private Appointment get(String appointmentId) {
        return appointments.findById(appointmentId).orElseThrow(() -> AppException.notFound("lịch hẹn"));
    }

    private Appointment doctorAppointment(String doctorId, String appointmentId) {
        Appointment appointment = get(appointmentId);
        if (appointment.doctorId != null && !appointment.doctorId.equals(doctorId)) {
            throw AppException.forbidden("Lịch hẹn này do bác sĩ khác phụ trách.");
        }
        return appointment;
    }

    private AppointmentOutput cancel(Appointment appointment, String reason) {
        if (!"requested".equals(appointment.status) && !"confirmed".equals(appointment.status)) {
            throw AppException.conflict("Chỉ huỷ được lịch hẹn chưa bắt đầu khám.");
        }
        appointment.status = "cancelled";
        appointment.cancelReason = reason.trim();
        appointments.save(appointment);
        // đợt vẫn open: bệnh nhân chat tiếp rồi đặt lại lịch khác
        return output(appointment, episode(appointment.episodeId), encounters.findByAppointmentId(appointment.id).orElse(null));
    }

    String notBookableReason(ClinicalEpisode episode) {
        if (!"open".equals(episode.status)) {
            return "Đợt bệnh này không còn mở.";
        }
        if (records.isExpired(episode, Instant.now())) {
            return "Đợt bệnh đã quá hạn không cập nhật, hãy mô tả lại triệu chứng trong chat.";
        }
        if (appointments.existsByEpisodeIdAndStatusIn(episode.id, ACTIVE)) {
            return "Đợt bệnh này đã có lịch hẹn.";
        }
        if (hypotheses.findByEpisodeIdOrderByRankAsc(episode.id).isEmpty()) {
            return "Chưa đủ thông tin: hãy mô tả triệu chứng trong chat để AI thu thập trước khi đặt lịch.";
        }
        return null;
    }

    private void refreshSummary(ClinicalEpisode episode, boolean force) {
        if (!force && episode.summaryAt != null && !episode.summaryAt.isBefore(episode.updatedAt)) {
            return;
        }
        List<ClinicalFact> episodeFacts = facts.findByEpisodeIdInOrderByCreatedAtAsc(List.of(episode.id));
        List<ClinicalFact> longTerm = longTermOf(List.of(episode.patientProfileId)).getOrDefault(episode.patientProfileId, List.of());
        episode.summary = ClinicalRecordService.buildEpisodeSummary(episode, episodeFacts, longTerm, hypotheses.findByEpisodeIdOrderByRankAsc(episode.id), readStrings(episode.redFlags));
        episode.summaryAt = Instant.now();
        episodes.save(episode);
    }

    private List<PatientEpisodeOutput> patientEpisodes(List<ClinicalEpisode> list) {
        List<String> ids = list.stream().map(e -> e.id).toList();
        Map<String, List<ClinicalFact>> episodeFacts = new HashMap<>();
        if (!ids.isEmpty()) {
            facts.findByEpisodeIdInOrderByCreatedAtAsc(ids).forEach(f -> episodeFacts.computeIfAbsent(f.episodeId, k -> new ArrayList<>()).add(f));
        }
        Map<String, Appointment> active = new HashMap<>();
        if (!ids.isEmpty()) {
            appointments.findByEpisodeIdInAndStatusIn(ids, ACTIVE).forEach(a -> active.put(a.episodeId, a));
        }
        Map<String, Encounter> encounterByAppointment = encountersOf(new ArrayList<>(active.values()));
        return list.stream().map(e -> {
            String reason = notBookableReason(e);
            Appointment appointment = active.get(e.id);
            return mapper.toPatientEpisode(e, episodeFacts.getOrDefault(e.id, List.of()).stream().map(f -> f.detail.isEmpty() ? f.label : f.label + ": " + f.detail).toList(),
                    reason == null, reason, appointment == null ? null : output(appointment, e, encounterByAppointment.get(appointment.id)));
        }).toList();
    }

    private AppointmentOutput output(Appointment a, ClinicalEpisode episode, Encounter encounter) {
        return mapper.toOutput(a, episode, encounter);
    }

    private DoctorAppointmentItemOutput item(Appointment a, ClinicalEpisode episode, Encounter encounter, IdentityClient.ProfileDetail profile,
            List<ClinicalFact> longTerm, List<AiHypothesis> hypothesisList) {
        return mapper.toItem(output(a, episode, encounter), patientDto(a.patientProfileId, profile, longTerm), hypothesisList.isEmpty() ? null : hypothesisList.get(0).disease);
    }

    private DoctorAppointmentDetailOutput detailOf(Appointment a) {
        ClinicalEpisode episode = episode(a.episodeId);
        refreshSummary(episode, false);
        IdentityClient.ProfileDetail profile = identity.getProfiles(List.of(a.patientProfileId)).get(a.patientProfileId);
        List<ClinicalFact> longTerm = longTermOf(List.of(a.patientProfileId)).getOrDefault(a.patientProfileId, List.of());
        List<AiHypothesis> hypothesisList = hypotheses.findByEpisodeIdOrderByRankAsc(episode.id);
        DoctorAppointmentItemOutput item = item(a, episode, encounters.findByAppointmentId(a.id).orElse(null), profile, longTerm, hypothesisList);
        List<ClinicalEpisode> others = episodes.findActiveOfProfile(a.patientProfileId).stream().filter(e -> !e.id.equals(episode.id)).toList();
        return mapper.toDetail(item, doctorEpisode(episode, facts.findByEpisodeIdInOrderByCreatedAtAsc(List.of(episode.id))), factOutputs(longTerm), patientEpisodes(others));
    }

    private HypothesisOutput hypothesisOutput(AiHypothesis h) {
        List<HypothesisEvidenceOutput> evidence = new ArrayList<>();
        for (Map<String, Object> e : readMaps(h.evidence)) {
            @SuppressWarnings("unchecked")
            Map<String, Object> ref = e.get("ref") instanceof Map<?, ?> m ? (Map<String, Object>) m : null;
            evidence.add(new HypothesisEvidenceOutput(String.valueOf(e.getOrDefault("source", "")), String.valueOf(e.getOrDefault("text", "")), ref));
        }
        return mapper.toHypothesis(h, evidence, readStrings(h.missing));
    }

    private Map<String, ClinicalEpisode> episodesById(Collection<String> ids) {
        return ids.isEmpty() ? Map.of() : episodes.findAllByIdIn(ids.stream().distinct().toList()).stream().collect(Collectors.toMap(e -> e.id, Function.identity()));
    }

    private Map<String, List<AiHypothesis>> hypothesesOf(Collection<String> episodeIds) {
        Map<String, List<AiHypothesis>> out = new HashMap<>();
        if (!episodeIds.isEmpty()) {
            hypotheses.findByEpisodeIdInOrderByRankAsc(episodeIds).forEach(h -> out.computeIfAbsent(h.episodeId, k -> new ArrayList<>()).add(h));
        }
        return out;
    }

    private Map<String, Encounter> encountersOf(Collection<Appointment> list) {
        return list.isEmpty() ? Map.of() : encounters.findByAppointmentIdIn(list.stream().map(a -> a.id).toList()).stream()
                .collect(Collectors.toMap(e -> e.appointmentId, Function.identity()));
    }

    private List<Map<String, Object>> readMaps(String text) {
        return text == null || text.isBlank() ? List.of() : json.readValue(text, LIST_OF_MAPS);
    }

    private List<String> readStrings(String text) {
        return text == null || text.isBlank() ? List.of() : json.readValue(text, LIST_OF_STRINGS);
    }
}
