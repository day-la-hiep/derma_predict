package vn.derma.clinical.service;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;
import vn.derma.clinical.common.ClinicalCodes;
import vn.derma.clinical.config.DermaProperties;
import vn.derma.clinical.dto.ClinicalDtos.ApplyTurnInput;
import vn.derma.clinical.entity.AiHypothesis;
import vn.derma.clinical.entity.ClinicalEpisode;
import vn.derma.clinical.model.PatientFact;
import vn.derma.clinical.repository.AiHypothesisRepository;
import vn.derma.clinical.repository.AppointmentRepository;
import vn.derma.clinical.repository.ClinicalEpisodeRepository;
import vn.derma.clinical.repository.FinalizeReportRepository;

/** Ghi giả thuyết và dự đoán ảnh của một lượt chat vào đợt bệnh theo vùng; fact dài hạn của hồ sơ do form hồ sơ ghi vào graph qua knowledge. */
@Service
@Slf4j
@AllArgsConstructor
public class ClinicalRecordService {

    private static final Set<String> ACTIVE_APPOINTMENT = Set.of("requested", "confirmed", "in_progress");
    private static final TypeReference<List<Map<String, Object>>> LIST_OF_MAPS = new TypeReference<>() {
    };

    private final ClinicalEpisodeRepository episodes;
    private final AiHypothesisRepository hypotheses;
    private final AppointmentRepository appointments;
    private final FinalizeReportRepository reports;
    private final PatientFactService patientFacts;
    private final ObjectMapper json;
    private final DermaProperties properties;

    /** Đợt `open` quá hạn không cập nhật; đợt gắn lịch hẹn còn hiệu lực thì không hết hạn (đặt lịch trước vài tuần). */
    public boolean isExpired(ClinicalEpisode episode, Instant now) {
        return "open".equals(episode.status) && Duration.between(episode.updatedAt, now).compareTo(Duration.ofDays(properties.episodeExpireDays())) > 0
                && !appointments.existsByEpisodeIdAndStatusIn(episode.id, ACTIVE_APPOINTMENT);
    }

    /** Báo cáo trước khám ghép tất định từ dữ liệu đã lưu (không gọi LLM) nên sinh lại được bất cứ lúc nào. */
    public static String buildEpisodeSummary(ClinicalEpisode episode, List<PatientFact> lesionFacts, List<PatientFact> longTerm, List<AiHypothesis> hypotheses,
            List<String> redFlags) {
        List<String> parts = new ArrayList<>();
        parts.add("Vùng: " + ClinicalCodes.BODY_SITE_LABELS.getOrDefault(episode.bodySite, episode.bodySite) + ".");
        if (!lesionFacts.isEmpty()) {
            parts.add("Triệu chứng / tổn thương bệnh nhân khai:\n" + lesionFacts.stream().map(ClinicalRecordService::factLine).collect(Collectors.joining("\n")));
        }
        if (!longTerm.isEmpty()) {
            parts.add("Dị ứng / tiền sử / thuốc:\n" + longTerm.stream().map(f -> factLine(f) + " [" + f.factType + "]").collect(Collectors.joining("\n")));
        }
        if (!hypotheses.isEmpty()) {
            parts.add("Gợi ý của AI (không phải chẩn đoán y khoa):\n" + hypotheses.stream()
                    .map(h -> h.rank + ". " + h.disease + " [" + h.diagnosisCode + "] - độ tin cậy " + h.confidence).collect(Collectors.joining("\n")));
        }
        if (!redFlags.isEmpty()) {
            parts.add("Dấu hiệu cần lưu ý: " + String.join("; ", redFlags));
        }
        return String.join("\n\n", parts);
    }

    /** Gộp fact dài hạn cùng loại thành một dòng cho thẻ bệnh nhân của bác sĩ. */
    public static String longTermText(List<PatientFact> longTerm, String factType) {
        return longTerm.stream().filter(f -> f.factType.equals(factType)).map(f -> f.detail.isEmpty() ? f.label : f.label + " (" + f.detail + ")")
                .collect(Collectors.joining("; "));
    }

    /** Có vùng, mốc khởi phát và phủ định ("không có") để bác sĩ đọc đúng dữ kiện, vì graph không còn tách theo đợt-vùng. */
    private static String factLine(PatientFact f) {
        StringBuilder line = new StringBuilder("- ").append(f.present ? "" : "KHÔNG CÓ ").append(f.label);
        List<String> notes = new ArrayList<>();
        if (!f.detail.isEmpty()) {
            notes.add(f.detail);
        }
        if (f.siteText != null) {
            notes.add("vị trí: " + f.siteText);
        }
        if (f.onsetText != null) {
            notes.add("khởi phát: " + f.onsetText);
        }
        return notes.isEmpty() ? line.toString() : line.append(": ").append(String.join("; ", notes)).toString();
    }

    public boolean hasLinkedData(String profileId) {
        return reports.existsByPatientProfileId(profileId);
    }

    /** Ghi giả thuyết và ảnh của lượt (`facts` nếu có bị bỏ qua: fact nay ghi vào graph qua knowledge). Lỗi dữ liệu của một mục chỉ bỏ mục đó (kèm log). */
    @Transactional
    public void applyClinicalEpisodeByTurn(ApplyTurnInput input) {
        List<Map<String, Object>> hypothesisItems = orEmpty(input.hypotheses()), images = orEmpty(input.imagePredictions());
        if (hypothesisItems.isEmpty() && images.isEmpty()) {
            return;
        }
        Turn turn = new Turn(input.patientProfileId(), input.conversationId(), Instant.now());

        // giả thuyết đi trước: chúng mở đợt theo vùng, ảnh chưa rõ vùng mới có chỗ để gắn
        Map<String, List<Map<String, Object>>> bySite = new LinkedHashMap<>();
        for (Map<String, Object> h : hypothesisItems) {
            String site = siteOf(h.get("body_site"));
            if (site == null) {
                site = turn.fallbackSite();
            }
            if (site == null) {
                log.warn("[clinical] bỏ giả thuyết {}: chưa rõ vùng, hội thoại chưa có đợt nào", h.get("disease"));
                continue;
            }
            bySite.computeIfAbsent(site, k -> new ArrayList<>()).add(h);
        }
        bySite.forEach((site, items) -> saveHypotheses(turn.episode(site), items));

        if (!images.isEmpty()) {
            Map<String, Set<String>> codes = new HashMap<>();
            bySite.forEach((site, items) -> codes.put(site, items.stream().map(h -> String.valueOf(h.getOrDefault("code", ""))).collect(Collectors.toSet())));
            saveImages(turn, images, codes);
        }
    }

    private void saveHypotheses(ClinicalEpisode episode, List<Map<String, Object>> items) {
        if (!"open".equals(episode.status)) {
            log.info("[clinical] đợt {} đang {}, giả thuyết đã khoá, bỏ cập nhật", episode.id, episode.status);
            return;
        }
        List<AiHypothesis> rows = new ArrayList<>();
        for (Map<String, Object> h : items) {
            String code = String.valueOf(h.getOrDefault("code", "")), confidence = String.valueOf(h.getOrDefault("confidence", ""));
            if (!ClinicalCodes.DIAGNOSIS_CODE_LABELS.containsKey(code) || !ClinicalCodes.HYPOTHESIS_CONFIDENCES.contains(confidence)) {
                log.warn("[clinical] bỏ giả thuyết {}: mã {} / độ tin cậy {} không hợp lệ", h.get("disease"), code, confidence);
                continue;
            }
            AiHypothesis row = new AiHypothesis();
            row.episodeId = episode.id;
            row.rank = rows.size() + 1;
            row.diagnosisCode = code;
            row.disease = cut(String.valueOf(h.getOrDefault("disease", "")), 255);
            row.confidence = confidence;
            row.evidence = json.writeValueAsString(orEmpty(h.get("evidence")));
            row.missing = json.writeValueAsString(orEmpty(h.get("missing")));
            rows.add(row);
        }
        // thay toàn bộ danh sách: xoá cũ và đẩy xuống DB trước khi thêm để không đụng unique (đợt, hạng)
        hypotheses.deleteByEpisodeId(episode.id);
        hypotheses.flush();
        hypotheses.saveAll(rows);
    }

    private void saveImages(Turn turn, List<Map<String, Object>> images, Map<String, Set<String>> codes) {
        for (Map<String, Object> image : images) {
            String storageKey = String.valueOf(image.getOrDefault("storage_key", ""));
            if (storageKey.isBlank()) {
                log.warn("[clinical] bỏ dự đoán ảnh không có storage_key");
                continue;
            }
            List<Map<String, Object>> topK = orEmpty(image.get("top_k"));
            // lượt chạm nhiều vùng: ảnh thuộc đợt có giả thuyết trùng nhãn top-1 của CNN
            String top = topK.isEmpty() ? "" : String.valueOf(topK.get(0).getOrDefault("label", ""));
            List<String> matched = codes.entrySet().stream().filter(e -> !top.isEmpty() && e.getValue().contains(top)).map(Map.Entry::getKey).toList();
            String site = matched.size() == 1 ? matched.get(0) : turn.onlyTouchedSite() != null ? turn.onlyTouchedSite() : turn.fallbackSite();
            if (site == null) {
                log.warn("[clinical] bỏ dự đoán ảnh {}: không xác định được đợt", storageKey);
                continue;
            }
            ClinicalEpisode episode = turn.episode(site);
            Map<String, Map<String, Object>> byKey = new LinkedHashMap<>();
            readList(episode.imagePredictions).forEach(p -> byKey.put(String.valueOf(p.get("storage_key")), p));
            byKey.put(storageKey, Map.of("storage_key", storageKey, "top_k", topK));
            episode.imagePredictions = json.writeValueAsString(new ArrayList<>(byKey.values()));
            episodes.save(episode);
        }
    }

    private static String siteOf(Object value) {
        String raw = value == null ? "" : String.valueOf(value).trim().toLowerCase();
        return ClinicalCodes.BODY_SITE_LABELS.containsKey(raw) ? raw : null;
    }

    private static String cut(String text, int max) {
        return text.length() <= max ? text : text.substring(0, max);
    }

    @SuppressWarnings("unchecked")
    private static <T> List<T> orEmpty(Object value) {
        return value instanceof List<?> list ? (List<T>) list : List.of();
    }

    private List<Map<String, Object>> readList(String text) {
        return text == null || text.isBlank() ? List.of() : json.readValue(text, LIST_OF_MAPS);
    }

    /** Các đợt đã chạm trong một lượt, để fact/ảnh chưa rõ vùng gắn được vào đúng đợt. */
    private final class Turn {

        final String profileId;
        final String conversationId;
        final Instant now;
        final Map<String, ClinicalEpisode> touched = new LinkedHashMap<>();

        Turn(String profileId, String conversationId, Instant now) {
            this.profileId = profileId;
            this.conversationId = conversationId;
            this.now = now;
        }

        /** Đợt đang hoạt động của vùng; quá hạn thì đóng `expired` và mở đợt mới. */
        ClinicalEpisode episode(String site) {
            ClinicalEpisode cached = touched.get(site);
            if (cached != null) {
                return cached;
            }
            ClinicalEpisode episode = episodes.findActive(profileId, site).orElse(null);
            if (episode != null && isExpired(episode)) {
                episode.status = "expired";
                episode.closedAt = now;
                episodes.saveAndFlush(episode); // nhả unique "1 đợt hoạt động / vùng" trước khi mở đợt mới
                log.info("[clinical] đợt {} ({}) hết hạn, mở đợt mới", episode.id, site);
                episode = null;
            }
            if (episode == null) {
                episode = new ClinicalEpisode();
                episode.patientProfileId = profileId;
                episode.bodySite = site;
                episode.openedAt = now;
            }
            episode.lastConversationId = conversationId;
            episode.updatedAt = now;
            episode = episodes.save(episode);
            touched.put(site, episode);
            return episode;
        }

        boolean isExpired(ClinicalEpisode episode) {
            return ClinicalRecordService.this.isExpired(episode, now);
        }

        String onlyTouchedSite() {
            return touched.size() == 1 ? touched.keySet().iterator().next() : null;
        }

        /** Vùng cho mục chưa rõ vùng: đợt duy nhất lượt này đã chạm, hoặc đợt đang hoạt động duy nhất của hội thoại. */
        String fallbackSite() {
            if (onlyTouchedSite() != null) {
                return onlyTouchedSite();
            }
            if (!touched.isEmpty()) {
                return null;
            }
            List<ClinicalEpisode> open = episodes.findActiveOfConversation(conversationId).stream().filter(e -> !isExpired(e)).toList();
            return open.size() == 1 ? open.get(0).bodySite : null;
        }
    }
}
