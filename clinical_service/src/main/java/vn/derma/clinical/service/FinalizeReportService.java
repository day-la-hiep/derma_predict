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
import vn.derma.clinical.client.AiClient;
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
import vn.derma.clinical.entity.Encounter;
import vn.derma.clinical.model.PatientFact;
import vn.derma.clinical.entity.FinalizeReport;
import vn.derma.clinical.entity.PatientImage;
import vn.derma.clinical.mapper.FinalizeMapper;
import vn.derma.clinical.repository.AppointmentRepository;
import vn.derma.clinical.repository.ClinicalEpisodeRepository;
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
    private final PatientFactService patientFacts;
    private final ClinicalEpisodeRepository episodes;
    private final AppointmentRepository appointments;
    private final EncounterRepository encounters;
    private final AppointmentService appointmentService;
    private final IdentityClient identity;
    private final ConsultationClient consultation;
    private final DermaProperties properties;
    private final KnowledgeClient knowledge;
    private final AiClient ai;
    private final TransactionTemplate tx;
    private final ObjectMapper json;
    private final FinalizeMapper mapper;

    // ---------------------------------------------------------------- đọc

    public List<FinalizeReportItemOutput> listMine(String doctorId, String q) {
        List<FinalizeReport> mine = reports.findByDoctorIdOrderByCreatedAtDesc(doctorId);
        Map<String, IdentityClient.ProfileDetail> profiles = identity.getProfiles(mine.stream().map(r -> r.patientProfileId).collect(Collectors.toSet()));
        Map<String, List<PatientFact>> longTerm = appointmentService.longTermOf(profiles.keySet());
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
        List<PatientFact> rows = patientFacts.current(appointment.patientProfileId);
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
        // fact hiện hành đọc từ graph và nội dung tin nguồn lấy từ consultation trước transaction để không giữ kết nối DB trong lúc gọi mạng;
        // graph không đọc được thì ném 502 và không chốt gì (không lưu snapshot thiếu dữ kiện)
        List<PatientFact> before = patientFacts.current(profile.id());
        Map<String, List<SnapshotProvenance>> sources = provenancesOf(before);
        // mô tả của bác sĩ → dữ kiện: gọi ai trước transaction; ai lỗi thì ném 502 và không chốt gì
        List<AiClient.DescribedFact> known = body.facts().stream().map(f -> new AiClient.DescribedFact(f.factType(), f.label().trim(), f.detail().trim(), f.siteText(), f.onsetText())).toList();
        List<AiClient.DescribedFact> described = ai.extractFactsFromDescription(body.description().trim(), known);
        FinalizeInput effective = withDescribedFacts(body, described);
        FinalizeReport report = tx.execute(status -> closeEncounter(encounter.id, appointment.id, profile, doctorId, doctorName, effective, sources, before));
        publish(report);
        consultation.openFollowupUntil(encounterId, profile.id(), doctorId, Instant.now().plus(Duration.ofDays(properties.followupDays())));
        return output(report, imagesOf(List.of(report)).getOrDefault(report.id, List.of()));
    }

    private static String factKey(String factType, String label) {
        return factType + "|" + normalize(label).toLowerCase();
    }

    /**
     * Gộp dữ kiện từ mô tả vào danh sách bác sĩ giữ lại: trùng khoá (loại + nhãn) với một dữ kiện đã giữ thì thay `detail` bằng lời bác sĩ
     * (origin thành doctor_corrected), chưa có thì thêm mới (doctor_observed); vị trí và khởi phát chỉ ghi khi bác sĩ viết rõ.
     */
    private FinalizeInput withDescribedFacts(FinalizeInput body, List<AiClient.DescribedFact> described) {
        List<FactInput> merged = new ArrayList<>(body.facts());
        for (AiClient.DescribedFact d : described) {
            if (d.label() == null || d.label().isBlank() || !ClinicalCodes.FACT_TYPES.contains(d.factType())) {
                log.warn("[finalize] bỏ dữ kiện từ mô tả không hợp lệ: loại={} nhãn={}", d.factType(), d.label());
                continue;
            }
            String key = factKey(d.factType(), d.label());
            String detail = d.detail() == null ? "" : d.detail().trim();
            int at = -1;
            for (int i = 0; i < merged.size(); i++) {
                if (factKey(merged.get(i).factType(), merged.get(i).label()).equals(key)) {
                    at = i;
                }
            }
            if (at >= 0) {
                FactInput old = merged.get(at);
                merged.set(at, new FactInput(old.sourceFactId(), old.factType(), old.label(), detail, firstText(d.siteText(), old.siteText()), firstText(d.onsetText(), old.onsetText())));
            } else {
                merged.add(new FactInput(null, d.factType(), normalize(d.label()), detail, blankToNull(d.siteText()), blankToNull(d.onsetText())));
            }
        }
        return new FinalizeInput(body.diagnosis(), body.notes(), body.isReferenceCase(), body.reasoning(), body.urgency(), body.instructions(), merged, body.images(),
                body.diagnosisCode(), body.description());
    }

    private static String blankToNull(String text) {
        return text == null || text.isBlank() ? null : text.trim();
    }

    private static String firstText(String preferred, String fallback) {
        String first = blankToNull(preferred);
        return first != null ? first : blankToNull(fallback);
    }

    private FinalizeReport closeEncounter(String encounterId, String appointmentId, IdentityClient.ProfileDetail profile, String doctorId, String doctorName,
            FinalizeInput body, Map<String, List<SnapshotProvenance>> sources, List<PatientFact> rows) {
        Encounter encounter = encounters.findById(encounterId).orElseThrow(() -> AppException.notFound("lần khám"));
        Appointment appointment = appointments.findById(appointmentId).orElseThrow(() -> AppException.notFound("lịch hẹn của lần khám"));
        ClinicalEpisode episode = episodes.findById(appointment.episodeId).orElseThrow(() -> AppException.notFound("đợt bệnh của lần khám"));
        if (!"open".equals(encounter.status) || !"in_exam".equals(episode.status)) {
            throw AppException.conflict("Lần khám này đã được chốt.");
        }
        if (reports.existsByEncounterId(encounterId)) {
            throw AppException.conflict("Lần khám này đã có kết luận.");
        }
        Map<String, PatientFact> byId = rows.stream().collect(Collectors.toMap(f -> f.id, Function.identity()));
        Set<String> keys = new HashSet<>();
        for (FactInput f : body.facts()) {
            if (!keys.add(f.factType() + "|" + normalize(f.label()).toLowerCase())) {
                throw AppException.invalid("Có hai dữ kiện trùng loại và nhãn, hãy gộp lại thành một.");
            }
            PatientFact source = f.sourceFactId() == null ? null : byId.get(f.sourceFactId());
            if (f.sourceFactId() != null && source == null) {
                throw AppException.invalid("Dữ kiện nguồn không còn hiệu lực hoặc không thuộc lần khám này, hãy tải lại form.");
            }
            if (source != null && source.isLongTerm() != ClinicalCodes.LONG_TERM_FACT_TYPES.contains(f.factType())) {
                throw AppException.invalid("Không đổi dữ kiện giữa nhóm dài hạn (dị ứng, tiền sử, thuốc) và nhóm theo đợt.");
            }
        }
        Set<String> kept = body.facts().stream().map(FactInput::sourceFactId).filter(java.util.Objects::nonNull).collect(Collectors.toSet());
        List<PatientFact> removed = rows.stream().filter(f -> !kept.contains(f.id)).toList();

        // snapshot dựng từ trạng thái TRƯỚC khi sửa để so ra fact bác sĩ đã đổi
        Snapshot snapshot = buildSnapshot(profile, body, byId, sources, removed.stream().map(f -> removedFact(f, sources)).toList());
        Set<String> allowedImages = allowedImageKeys(profile.id(), sources);
        allowedImages.addAll(appointmentService.imagePredictions(episode).stream().map(ImagePredictionOutput::fileId).toList());

        // chốt không ghi ngược vào graph: fact bị bỏ, fact từ mô tả và dấu xác nhận của bác sĩ chỉ nằm trong snapshot (graph chỉ phản ánh điều người bệnh nói)
        Instant now = Instant.now();

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

    private Snapshot buildSnapshot(IdentityClient.ProfileDetail profile, FinalizeInput body, Map<String, PatientFact> sourceFacts,
            Map<String, List<SnapshotProvenance>> sources, List<SnapshotFact> removed) {
        List<SnapshotFact> out = new ArrayList<>();
        for (FactInput f : body.facts()) {
            PatientFact source = f.sourceFactId() == null ? null : sourceFacts.get(f.sourceFactId());
            if (f.sourceFactId() != null && source == null) {
                throw AppException.invalid("Dữ kiện nguồn không còn hiệu lực hoặc không thuộc bệnh nhân này, hãy tải lại form.");
            }
            String label = f.label().trim(), detail = f.detail().trim();
            String origin = "doctor_observed";
            List<SnapshotProvenance> provenanceList = List.of();
            String siteText = blankToNull(f.siteText()), onsetText = blankToNull(f.onsetText()), onsetAt = null, kgNodeId = null;
            boolean present = true;
            if (source != null) {
                boolean unchanged = label.equals(source.label) && detail.equals(source.detail) && f.factType().equals(source.factType);
                origin = unchanged ? defaultOrigin(source.factType) : "doctor_corrected";
                provenanceList = sources.getOrDefault(source.id, List.of());
                siteText = firstText(siteText, source.siteText);
                onsetText = firstText(onsetText, source.onsetText);
                onsetAt = source.onsetAt;
                kgNodeId = source.kgNodeId;
                present = source.present;
            }
            out.add(new SnapshotFact(f.factType(), label, detail, origin, provenanceList, siteText, onsetText, onsetAt, kgNodeId, present));
        }
        SnapshotProfile snapshotProfile = mapper.toSnapshotProfile(profile, joinLines(out, "allergy"), joinLines(out, "history"));
        Assessment assessment = new Assessment(body.reasoning().trim(), body.urgency(), body.instructions().stream().map(String::trim).filter(i -> !i.isEmpty()).toList(),
                body.description().trim());
        return new Snapshot(snapshotProfile, assessment, out, removed);
    }

    private SnapshotFact removedFact(PatientFact f, Map<String, List<SnapshotProvenance>> sources) {
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

    /** Bằng chứng của từng fact: tin gốc (theo `sourceMessageId` trên cạnh graph) chép nguyên lúc chốt; không lấy được tin thì fact không có bằng chứng. */
    private Map<String, List<SnapshotProvenance>> provenancesOf(List<PatientFact> list) {
        Set<String> messageIds = list.stream().map(f -> f.sourceMessageId).filter(java.util.Objects::nonNull).collect(Collectors.toCollection(LinkedHashSet::new));
        if (messageIds.isEmpty()) {
            return Map.of();
        }
        Map<String, ConsultationClient.MessageInfo> messages = consultation.getMessages(messageIds);
        Map<String, List<SnapshotProvenance>> out = new HashMap<>();
        for (PatientFact f : list) {
            ConsultationClient.MessageInfo m = f.sourceMessageId == null ? null : messages.get(f.sourceMessageId);
            if (m != null) {
                out.put(f.id, List.of(new SnapshotProvenance(mapper.toSnapshotMessage(m))));
            }
        }
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

    private List<DraftFactOutput> draftFacts(List<PatientFact> list) {
        Map<String, List<SnapshotProvenance>> sources = provenancesOf(list);
        return list.stream().map(f -> mapper.toDraftFact(f, defaultOrigin(f.factType), presign(sources.getOrDefault(f.id, List.of())))).toList();
    }

    private List<SnapshotProvenance> presign(List<SnapshotProvenance> list) {
        return list.stream().map(p -> new SnapshotProvenance(new SnapshotMessage(p.message().id(), p.message().sender(), p.message().content(),
                p.message().createdAt(), p.message().files().stream().map(f -> appointmentService.fileDto(f.storageKey())).toList()))).toList();
    }

    /** Lỗi knowledge chỉ làm mất gợi ý, không chặn đóng ca. */
    private GraphSuggestionOutput suggestions(String profileId, List<PatientFact> list) {
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
        // chỉ triệu chứng và hình thái (nhóm 1, 2) còn hiện diện; ưu tiên tên chuẩn tiếng Anh của nút đã khớp vì `translate=false` ở đây
        List<String> symptoms = list.stream().filter(f -> f.present && f.category != null && Set.of(1, 2).contains(f.category))
                .map(f -> f.kgName != null ? f.kgName : f.label).distinct().toList();
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
        return list.stream().map(f -> new SnapshotFact(f.factType(), f.label(), f.detail(), f.origin(), presign(f.provenances() == null ? List.of() : f.provenances()),
                f.siteText(), f.onsetText(), f.onsetAt(), f.kgNodeId(), f.present())).toList();
    }
}
