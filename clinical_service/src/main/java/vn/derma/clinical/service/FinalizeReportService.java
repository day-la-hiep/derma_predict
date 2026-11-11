package vn.derma.clinical.service;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import vn.derma.clinical.client.ConsultationClient;
import vn.derma.clinical.client.IdentityClient;
import vn.derma.clinical.client.KnowledgeClient;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.config.DermaProperties;
import vn.derma.clinical.common.ClinicalCodes;
import vn.derma.clinical.dto.AppointmentDtos.FileDto;
import vn.derma.clinical.dto.AppointmentDtos.ImagePredictionOutput;
import vn.derma.clinical.dto.AppointmentDtos.PatientProfileDto;
import vn.derma.clinical.dto.FinalizeDtos.Assessment;
import vn.derma.clinical.dto.FinalizeDtos.CaseImage;
import vn.derma.clinical.dto.FinalizeDtos.CaseInput;
import vn.derma.clinical.dto.FinalizeDtos.DiagnosisOptionOutput;
import vn.derma.clinical.dto.FinalizeDtos.DraftFactOutput;
import vn.derma.clinical.dto.FinalizeDtos.EncounterDraftOutput;
import vn.derma.clinical.dto.FinalizeDtos.FactInput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeInput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeReportItemOutput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeReportOutput;
import vn.derma.clinical.dto.FinalizeDtos.GraphSuggestionOutput;
import vn.derma.clinical.dto.FinalizeDtos.PatientFinalizeReportOutput;
import vn.derma.clinical.dto.FinalizeDtos.PatientImageInput;
import vn.derma.clinical.dto.FinalizeDtos.PatientImageOutput;
import vn.derma.clinical.dto.FinalizeDtos.Snapshot;
import vn.derma.clinical.dto.FinalizeDtos.SnapshotFact;
import vn.derma.clinical.dto.FinalizeDtos.SnapshotMessage;
import vn.derma.clinical.dto.FinalizeDtos.SnapshotProfile;
import vn.derma.clinical.dto.FinalizeDtos.SnapshotProvenance;
import vn.derma.clinical.entity.Appointment;
import vn.derma.clinical.entity.ClinicalEpisode;
import vn.derma.clinical.entity.ClinicalFact;
import vn.derma.clinical.entity.ClinicalProvenance;
import vn.derma.clinical.entity.Encounter;
import vn.derma.clinical.entity.FinalizeReport;
import vn.derma.clinical.entity.PatientImage;
import vn.derma.clinical.mapper.FinalizeMapper;
import vn.derma.clinical.repository.AppointmentRepository;
import vn.derma.clinical.repository.ClinicalEpisodeRepository;
import vn.derma.clinical.repository.ClinicalFactRepository;
import vn.derma.clinical.repository.ClinicalProvenanceRepository;
import vn.derma.clinical.repository.EncounterRepository;
import vn.derma.clinical.repository.FinalizeReportRepository;
import vn.derma.clinical.repository.PatientImageRepository;

/** Bác sĩ chốt báo cáo kết luận (từ ca tư vấn hoặc lần khám) rồi nạp ca vào knowledge. Snapshot lưu bất biến để phiếu không đổi theo hồ sơ sống. */
@Service
@Slf4j
@AllArgsConstructor
public class FinalizeReportService {


    private final FinalizeReportRepository reports;
    private final PatientImageRepository images;
    private final ClinicalFactRepository facts;
    private final ClinicalProvenanceRepository provenances;
    private final ClinicalEpisodeRepository episodes;
    private final AppointmentRepository appointments;
    private final EncounterRepository encounters;
    private final AppointmentService appointmentService;
    private final IdentityClient identity;
    private final ConsultationClient consultation;
    private final DermaProperties properties;
    private final KnowledgeClient knowledge;
    private final TransactionTemplate tx;
    private final ObjectMapper json;
    private final FinalizeMapper mapper;

    // ---------------------------------------------------------------- đọc

    public List<FinalizeReportItemOutput> listMine(String doctorId, String q) {
        List<FinalizeReport> mine = reports.findByDoctorIdOrderByCreatedAtDesc(doctorId);
        Map<String, IdentityClient.ProfileDetail> profiles = identity.getProfiles(mine.stream().map(r -> r.patientProfileId).collect(Collectors.toSet()));
        Map<String, List<ClinicalFact>> longTerm = appointmentService.longTermOf(profiles.keySet());
        Map<String, List<PatientImage>> imagesByReport = imagesOf(mine);
        String needle = q == null ? "" : q.trim().toLowerCase();
        List<FinalizeReportItemOutput> out = new ArrayList<>();
        for (FinalizeReport r : mine) {
            IdentityClient.ProfileDetail profile = profiles.get(r.patientProfileId);
            String name = profile == null ? "" : profile.fullName();
            if (!needle.isEmpty() && !r.diagnosis.toLowerCase().contains(needle) && !name.toLowerCase().contains(needle)) {
                continue;
            }
            FinalizeReportOutput o = output(r, imagesByReport.getOrDefault(r.id, List.of()));
            out.add(mapper.toItem(o, appointmentService.patientDto(r.patientProfileId, profile, longTerm.getOrDefault(r.patientProfileId, List.of()))));
        }
        return out;
    }

    public List<FinalizeReportOutput> listForProfile(String profileId) {
        return history(profileId);
    }

    public List<PatientFinalizeReportOutput> listForPatient(String userId, String profileId) {
        identity.resolveProfile(userId, profileId).orElseThrow(() -> AppException.notFound("hồ sơ bệnh nhân"));
        return reports.findByPatientProfileIdOrderByCreatedAtDesc(profileId).stream()
                .map(mapper::toPatientOutput).toList();
    }

    public JsonNode getJourneyGraph(String profileId) {
        return knowledge.getJourneyGraph(profileId);
    }

    public EncounterDraftOutput draftForEncounter(String encounterId, String doctorId) {
        Encounter encounter = ownedEncounter(encounterId, doctorId);
        Appointment appointment = appointments.findById(encounter.appointmentId).orElseThrow(() -> AppException.notFound("lịch hẹn của lần khám"));
        var detail = appointmentService.detail(doctorId, appointment.id);
        List<ClinicalFact> rows = facts.findForExam(appointment.patientProfileId, appointment.episodeId);
        List<DiagnosisOptionOutput> options = ClinicalCodes.DIAGNOSIS_CODE_LABELS.entrySet().stream().sorted(Map.Entry.comparingByKey())
                .map(e -> new DiagnosisOptionOutput(e.getKey(), e.getValue())).toList();
        return new EncounterDraftOutput(detail.patient(), draftFacts(rows), suggestions(appointment.patientProfileId, rows), encounterId, appointment.id,
                detail.episode(), detail.episode().imagePredictions(), options);
    }

    // ---------------------------------------------------------------- chốt

    /** Một transaction: ghi fact + nhật ký bác sĩ + kết luận, đóng lần khám/lịch hẹn/đợt; sau khi lưu mới nạp knowledge. */
    public FinalizeReportOutput finalizeEncounter(String encounterId, String doctorId, String doctorName, FinalizeInput body) {
        if (body.diagnosisCode() == null || !ClinicalCodes.DIAGNOSIS_CODE_LABELS.containsKey(body.diagnosisCode())) {
            throw AppException.invalid("Mã chẩn đoán không hợp lệ.");
        }
        validateInput(body);
        Encounter encounter = ownedEncounter(encounterId, doctorId);
        Appointment appointment = appointments.findById(encounter.appointmentId).orElseThrow(() -> AppException.notFound("lịch hẹn của lần khám"));
        IdentityClient.ProfileDetail profile = profileOf(appointment.patientProfileId);
        // nội dung tin nguồn lấy từ consultation trước transaction để không giữ kết nối DB trong lúc gọi mạng
        List<ClinicalFact> before = facts.findForExam(profile.id(), appointment.episodeId);
        Map<String, List<SnapshotProvenance>> sources = provenancesOf(before);
        FinalizeReport report = tx.execute(status -> closeEncounter(encounter.id, appointment.id, profile, doctorId, doctorName, body, sources));
        publish(report);
        consultation.openFollowupUntil(encounterId, profile.id(), doctorId, Instant.now().plus(Duration.ofDays(properties.followupDays())));
        return output(report, imagesOf(List.of(report)).getOrDefault(report.id, List.of()));
    }

    private FinalizeReport closeEncounter(String encounterId, String appointmentId, IdentityClient.ProfileDetail profile, String doctorId, String doctorName,
            FinalizeInput body, Map<String, List<SnapshotProvenance>> sources) {
        Encounter encounter = encounters.findById(encounterId).orElseThrow(() -> AppException.notFound("lần khám"));
        Appointment appointment = appointments.findById(appointmentId).orElseThrow(() -> AppException.notFound("lịch hẹn của lần khám"));
        ClinicalEpisode episode = episodes.findById(appointment.episodeId).orElseThrow(() -> AppException.notFound("đợt bệnh của lần khám"));
        if (!"open".equals(encounter.status) || !"in_exam".equals(episode.status)) {
            throw AppException.conflict("Lần khám này đã được chốt.");
        }
        if (reports.existsByEncounterId(encounterId)) {
            throw AppException.conflict("Lần khám này đã có kết luận.");
        }
        List<ClinicalFact> rows = facts.findForExam(profile.id(), episode.id);
        Map<String, ClinicalFact> byId = rows.stream().collect(Collectors.toMap(f -> f.id, Function.identity()));
        Set<String> keys = new HashSet<>();
        for (FactInput f : body.facts()) {
            if (!keys.add(f.factType() + "|" + normalize(f.label()).toLowerCase())) {
                throw AppException.invalid("Có hai dữ kiện trùng loại và nhãn, hãy gộp lại thành một.");
            }
            ClinicalFact source = f.sourceFactId() == null ? null : byId.get(f.sourceFactId());
            if (f.sourceFactId() != null && source == null) {
                throw AppException.invalid("Dữ kiện nguồn không còn hiệu lực hoặc không thuộc lần khám này, hãy tải lại form.");
            }
            if (source != null && (source.episodeId == null) != ClinicalCodes.LONG_TERM_FACT_TYPES.contains(f.factType())) {
                throw AppException.invalid("Không đổi dữ kiện giữa nhóm dài hạn (dị ứng, tiền sử, thuốc) và nhóm theo đợt.");
            }
        }
        Set<String> kept = body.facts().stream().map(FactInput::sourceFactId).filter(java.util.Objects::nonNull).collect(Collectors.toSet());
        List<ClinicalFact> removed = rows.stream().filter(f -> !kept.contains(f.id)).toList();

        // snapshot dựng từ trạng thái TRƯỚC khi sửa để so ra fact bác sĩ đã đổi
        Snapshot snapshot = buildSnapshot(profile, body, byId, sources, removed.stream().map(f -> removedFact(f, sources)).toList());
        Set<String> allowedImages = allowedImageKeys(profile.id(), sources);
        allowedImages.addAll(appointmentService.imagePredictions(episode).stream().map(ImagePredictionOutput::fileId).toList());

        Instant now = Instant.now();
        facts.deleteAll(removed);
        List<ClinicalProvenance> logs = new ArrayList<>();
        for (FactInput f : body.facts()) {
            String label = normalize(f.label()), detail = f.detail().trim();
            ClinicalFact fact = f.sourceFactId() == null ? null : byId.get(f.sourceFactId());
            if (fact != null) {
                fact.factType = f.factType();
                fact.label = label;
                fact.detail = detail;
            } else {
                fact = new ClinicalFact();
                fact.patientProfileId = profile.id();
                fact.episodeId = ClinicalCodes.LONG_TERM_FACT_TYPES.contains(f.factType()) ? null : episode.id;
                fact.factType = f.factType();
                fact.label = label;
                fact.detail = detail;
                fact.createdAt = now;
            }
            fact.updatedAt = now;
            fact.verifiedAt = now;
            fact.verifiedById = doctorId;
            facts.save(fact);
            ClinicalProvenance log = new ClinicalProvenance();
            log.factId = fact.id;
            log.kind = "doctor";
            log.doctorId = doctorId;
            log.encounterId = encounterId;
            log.quote = label;
            log.detail = detail;
            log.createdAt = now;
            logs.add(log);
        }
        provenances.saveAll(logs);

        FinalizeReport report = store(profile.id(), doctorId, doctorName, body, snapshot, encounterId, body.diagnosisCode(), allowedImages);
        encounter.status = "closed";
        encounter.closedAt = now;
        appointment.status = "done";
        episode.status = "closed";
        episode.closedAt = now;
        encounters.save(encounter);
        appointments.save(appointment);
        episodes.save(episode);
        return report;
    }

    private FinalizeReport store(String profileId, String doctorId, String doctorName, FinalizeInput body, Snapshot snapshot,
            String encounterId, String diagnosisCode, Set<String> allowedImages) {
        FinalizeReport report = new FinalizeReport();
        report.patientProfileId = profileId;
        report.doctorId = doctorId;
        report.doctorName = doctorName;
        report.diagnosis = body.diagnosis().trim();
        report.notes = body.notes().trim();
        report.referenceCase = body.isReferenceCase();
        report.encounterId = encounterId;
        report.diagnosisCode = diagnosisCode;
        report.snapshot = json.writeValueAsString(snapshot);
        report.createdAt = Instant.now();
        reports.save(report);
        for (PatientImageInput input : body.images()) {
            if (!allowedImages.contains(input.fileId())) {
                log.warn("[finalize] bỏ ảnh {}: không thuộc hội thoại/đợt bệnh của bệnh nhân này", input.fileId());
                continue;
            }
            FileDto file = appointmentService.fileDto(input.fileId());
            PatientImage image = new PatientImage();
            image.finalizeReportId = report.id;
            image.storageKey = input.fileId();
            image.fileName = file.fileName();
            image.contentType = file.contentType();
            image.bodySite = input.bodySite();
            image.description = input.description();
            image.confirmedLabel = input.confirmedLabel();
            image.capturedAt = Instant.now();
            images.save(image);
        }
        return report;
    }

    /** Lỗi gọi knowledge chỉ ghi log vì báo cáo đã lưu; ca thiếu được bù bằng reindex. */
    private void publish(FinalizeReport report) {
        knowledge.postCase(toCase(report, imagesOf(List.of(report)).getOrDefault(report.id, List.of())), report.id);
    }

    // ---------------------------------------------------------------- cho knowledge reindex

    public List<CaseInput> listCases(int page, int pageSize) {
        List<FinalizeReport> found = reports.findAllByOrderByCreatedAtAsc(PageRequest.of(Math.max(page - 1, 0), pageSize));
        Map<String, List<PatientImage>> imagesByReport = imagesOf(found);
        return found.stream().map(r -> toCase(r, imagesByReport.getOrDefault(r.id, List.of()))).toList();
    }

    private CaseInput toCase(FinalizeReport r, List<PatientImage> attached) {
        Snapshot snapshot = r.snapshot == null ? null : json.readValue(r.snapshot, Snapshot.class);
        return mapper.toCase(r, snapshot, attached.stream().map(mapper::toCaseImage).toList());
    }

    // ---------------------------------------------------------------- snapshot

    private Snapshot buildSnapshot(IdentityClient.ProfileDetail profile, FinalizeInput body, Map<String, ClinicalFact> sourceFacts,
            Map<String, List<SnapshotProvenance>> sources, List<SnapshotFact> removed) {
        List<SnapshotFact> out = new ArrayList<>();
        for (FactInput f : body.facts()) {
            ClinicalFact source = f.sourceFactId() == null ? null : sourceFacts.get(f.sourceFactId());
            if (f.sourceFactId() != null && source == null) {
                throw AppException.invalid("Dữ kiện nguồn không còn hiệu lực hoặc không thuộc bệnh nhân này, hãy tải lại form.");
            }
            String label = f.label().trim(), detail = f.detail().trim();
            String origin = "doctor_observed";
            List<SnapshotProvenance> provenanceList = List.of();
            if (source != null) {
                boolean unchanged = label.equals(source.label) && detail.equals(source.detail) && f.factType().equals(source.factType);
                origin = unchanged ? defaultOrigin(source.factType) : "doctor_corrected";
                provenanceList = sources.getOrDefault(source.id, List.of());
            }
            out.add(new SnapshotFact(f.factType(), label, detail, origin, provenanceList));
        }
        SnapshotProfile snapshotProfile = mapper.toSnapshotProfile(profile, joinLines(out, "allergy"), joinLines(out, "history"));
        Assessment assessment = new Assessment(body.reasoning().trim(), body.urgency(), body.instructions().stream().map(String::trim).filter(i -> !i.isEmpty()).toList());
        return new Snapshot(snapshotProfile, assessment, out, removed);
    }

    private SnapshotFact removedFact(ClinicalFact f, Map<String, List<SnapshotProvenance>> sources) {
        return mapper.toSnapshotFact(f, defaultOrigin(f.factType), sources.getOrDefault(f.id, List.of()));
    }

    private static String joinLines(List<SnapshotFact> list, String type) {
        return list.stream().filter(f -> f.factType().equals(type)).map(f -> f.detail().isEmpty() ? f.label() : f.label() + " (" + f.detail() + ")")
                .collect(Collectors.joining("; "));
    }

    private static String defaultOrigin(String factType) {
        return "image_finding".equals(factType) ? "ai_inferred" : "patient_reported";
    }

    private static String normalize(String text) {
        return String.join(" ", text.trim().split("\\s+"));
    }

    /** Bằng chứng của từng fact: tin gốc chép nguyên lúc chốt; không lấy được tin thì dùng đoạn trích đã lưu cùng fact. */
    private Map<String, List<SnapshotProvenance>> provenancesOf(List<ClinicalFact> list) {
        if (list.isEmpty()) {
            return Map.of();
        }
        List<ClinicalProvenance> rows = provenances.findByFactIdInOrderByCreatedAtAsc(list.stream().map(f -> f.id).toList()).stream().filter(p -> p.messageId != null)
                .toList();
        Map<String, ConsultationClient.MessageInfo> messages = consultation.getMessages(rows.stream().map(p -> p.messageId).collect(Collectors.toCollection(LinkedHashSet::new)));
        Map<String, Map<String, SnapshotProvenance>> byFact = new LinkedHashMap<>();
        for (ClinicalProvenance p : rows) {
            ConsultationClient.MessageInfo m = messages.get(p.messageId);
            SnapshotMessage message = m != null ? mapper.toSnapshotMessage(m) : mapper.toSnapshotMessage(p);
            byFact.computeIfAbsent(p.factId, k -> new LinkedHashMap<>()).putIfAbsent(p.messageId, new SnapshotProvenance(message));
        }
        Map<String, List<SnapshotProvenance>> out = new HashMap<>();
        byFact.forEach((factId, map) -> out.put(factId, List.copyOf(map.values())));
        return out;
    }

    /** Ảnh được phép gắn vào kết luận: ảnh trong tin nguồn của fact và ảnh đã phân loại của các đợt đang hoạt động của bệnh nhân. */
    private Set<String> allowedImageKeys(String profileId, Map<String, List<SnapshotProvenance>> sources) {
        Set<String> keys = new HashSet<>();
        sources.values().forEach(l -> l.forEach(p -> p.message().files().forEach(f -> keys.add(f.storageKey()))));
        episodes.findActiveOfProfile(profileId).forEach(e -> appointmentService.imagePredictions(e).forEach(p -> keys.add(p.fileId())));
        return keys;
    }

    // ---------------------------------------------------------------- tiện ích

    private void validateInput(FinalizeInput body) {
        if (!ClinicalCodes.URGENCIES.contains(body.urgency())) {
            throw AppException.invalid("Mức khẩn cấp không hợp lệ.");
        }
        for (FactInput f : body.facts()) {
            if (!ClinicalCodes.FACT_TYPES.contains(f.factType()) && !"image_finding".equals(f.factType())) {
                throw AppException.invalid("Loại dữ kiện không hợp lệ: " + f.factType());
            }
        }
    }

    private Encounter ownedEncounter(String encounterId, String doctorId) {
        Encounter encounter = encounters.findById(encounterId).orElseThrow(() -> AppException.notFound("lần khám"));
        if (!doctorId.equals(encounter.doctorId)) {
            throw AppException.forbidden("Lần khám này do bác sĩ khác phụ trách.");
        }
        return encounter;
    }

    private IdentityClient.ProfileDetail profileOf(String profileId) {
        IdentityClient.ProfileDetail profile = identity.getProfiles(List.of(profileId)).get(profileId);
        if (profile == null) {
            throw AppException.notFound("hồ sơ bệnh nhân " + profileId);
        }
        return profile;
    }

    private List<DraftFactOutput> draftFacts(List<ClinicalFact> list) {
        Map<String, List<SnapshotProvenance>> sources = provenancesOf(list);
        return list.stream().map(f -> mapper.toDraftFact(f, defaultOrigin(f.factType), presign(sources.getOrDefault(f.id, List.of())))).toList();
    }

    private List<SnapshotProvenance> presign(List<SnapshotProvenance> list) {
        return list.stream().map(p -> new SnapshotProvenance(new SnapshotMessage(p.message().id(), p.message().sender(), p.message().content(),
                p.message().createdAt(), p.message().files().stream().map(f -> appointmentService.fileDto(f.storageKey())).toList()))).toList();
    }

    /** Lỗi knowledge chỉ làm mất gợi ý, không chặn đóng ca. */
    private GraphSuggestionOutput suggestions(String profileId, List<ClinicalFact> list) {
        List<String> previousConditions = new ArrayList<>(), previousAdvice = new ArrayList<>(), candidates = new ArrayList<>(), redFlags = new ArrayList<>(),
                notes = new ArrayList<>();
        try {
            KnowledgeClient.HistoryHints hints = knowledge.getHistoryHints(profileId);
            previousConditions.addAll(hints.conditions());
            previousAdvice.addAll(hints.advice());
        } catch (RuntimeException e) {
            log.warn("Không đọc được lịch sử từ đồ thị bệnh nhân {}", profileId, e);
            notes.add("Không đọc được lịch sử từ đồ thị bệnh nhân.");
        }
        List<String> symptoms = list.stream().filter(f -> f.factType.equals("symptom") || f.factType.equals("lesion")).map(f -> f.label).toList();
        if (!symptoms.isEmpty()) {
            try {
                KnowledgeClient.IntentResult found = knowledge.runIntent("diseases_with_symptom", symptoms, 5);
                found.facts().forEach(f -> candidates.add(f.get("text")));
                notes.addAll(found.notes());
                // tên bệnh nằm trong câu "Bệnh ứng viên theo đồ thị tri thức: <tên> (điểm ..."
                List<String> names = candidates.stream().map(t -> t.substring(t.indexOf(": ") + 2).split(" \\(điểm")[0]).limit(2).toList();
                knowledge.runIntent("red_flags_risk", names, 6).facts().forEach(f -> redFlags.add(f.get("text")));
            } catch (RuntimeException e) {
                log.warn("Không tra được đồ thị tri thức da liễu", e);
                notes.add("Không tra được đồ thị tri thức da liễu.");
            }
        }
        return new GraphSuggestionOutput(previousConditions, previousAdvice, candidates, redFlags, notes);
    }

    private List<FinalizeReportOutput> history(String profileId) {
        List<FinalizeReport> found = reports.findByPatientProfileIdOrderByCreatedAtDesc(profileId);
        Map<String, List<PatientImage>> imagesByReport = imagesOf(found);
        return found.stream().map(r -> output(r, imagesByReport.getOrDefault(r.id, List.of()))).toList();
    }

    private Map<String, List<PatientImage>> imagesOf(List<FinalizeReport> list) {
        if (list.isEmpty()) {
            return Map.of();
        }
        return images.findByFinalizeReportIdIn(list.stream().map(r -> r.id).toList()).stream().collect(Collectors.groupingBy(i -> i.finalizeReportId));
    }

    private FinalizeReportOutput output(FinalizeReport r, List<PatientImage> attached) {
        Snapshot snapshot = r.snapshot == null ? null : presign(json.readValue(r.snapshot, Snapshot.class));
        List<PatientImageOutput> imageOutputs = attached.stream().map(i -> mapper.toPatientImage(i, appointmentService.fileDto(i.storageKey))).toList();
        return mapper.toOutput(r, snapshot, imageOutputs);
    }

    private Snapshot presign(Snapshot s) {
        return new Snapshot(s.patientProfile(), s.assessment(), presignFacts(s.clinicalFacts()), presignFacts(s.removedFacts()));
    }

    private List<SnapshotFact> presignFacts(List<SnapshotFact> list) {
        if (list == null) {
            return List.of();
        }
        return list.stream().map(f -> new SnapshotFact(f.factType(), f.label(), f.detail(), f.origin(), presign(f.provenances() == null ? List.of() : f.provenances()))).toList();
    }
}
