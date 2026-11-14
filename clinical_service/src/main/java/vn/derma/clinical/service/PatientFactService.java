package vn.derma.clinical.service;

import java.time.Instant;
import java.util.Collection;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

import lombok.AllArgsConstructor;
import vn.derma.clinical.client.PatientFactClient;
import vn.derma.clinical.client.PatientFactClient.GraphFact;
import vn.derma.clinical.client.PatientFactClient.GraphFacts;
import vn.derma.clinical.client.PatientFactClient.Lesion;
import vn.derma.clinical.model.PatientFact;

/** Nguồn duy nhất của dữ kiện lâm sàng theo dõi: graph ở knowledge. Clinical chỉ chụp snapshot lúc bác sĩ chốt. */
@Service
@AllArgsConstructor
public class PatientFactService {

    private final PatientFactClient client;

    /** Mọi dữ kiện hiện hành của hồ sơ (dài hạn lẫn theo tổn thương), cũ trước. */
    public List<PatientFact> current(String profileId) {
        GraphFacts graph = client.getFacts(profileId);
        Map<String, Lesion> lesions = graph.lesions().stream().collect(Collectors.toMap(Lesion::id, l -> l, (a, b) -> a));
        return graph.facts().stream().map(g -> toFact(profileId, g, lesions.get(g.lesionId()))).toList();
    }

    /** Dữ kiện theo tổn thương (triệu chứng, hình thái, đặc điểm...) của hồ sơ. */
    public List<PatientFact> lesionFacts(String profileId) {
        return current(profileId).stream().filter(f -> !f.isLongTerm()).toList();
    }

    /** Dị ứng, tiền sử, thuốc của từng hồ sơ; hồ sơ chưa có thì danh sách rỗng. */
    public Map<String, List<PatientFact>> longTermOf(Collection<String> profileIds) {
        Map<String, List<PatientFact>> out = new HashMap<>();
        if (profileIds.isEmpty()) {
            return out;
        }
        client.getLongTerm(profileIds).forEach((id, facts) -> out.put(id, facts.stream().map(g -> toFact(id, g, null)).toList()));
        return out;
    }

    static PatientFact toFact(String profileId, GraphFact g, Lesion lesion) {
        PatientFact fact = new PatientFact();
        fact.id = g.id();
        fact.patientProfileId = profileId;
        fact.factType = g.factType();
        fact.label = g.label();
        fact.detail = g.detail() == null ? "" : g.detail();
        fact.present = !Boolean.FALSE.equals(g.present());
        fact.category = g.category();
        fact.lesionId = g.lesionId();
        fact.siteText = lesion == null || lesion.siteText() == null || lesion.siteText().isBlank() ? null : lesion.siteText();
        fact.onsetText = g.onsetText() == null || g.onsetText().isBlank() ? null : g.onsetText();
        fact.onsetAt = g.onsetAt();
        fact.kgNodeId = g.kgNodeId();
        fact.kgName = g.kgName() == null || g.kgName().isBlank() ? null : g.kgName();
        fact.sourceMessageId = g.sourceMessageId();
        fact.stale = g.stale();
        fact.createdAt = parse(g.observedAt());
        fact.updatedAt = parse(g.lastConfirmedAt());
        return fact;
    }

    private static Instant parse(String text) {
        return text == null || text.isBlank() ? null : Instant.parse(text);
    }
}
