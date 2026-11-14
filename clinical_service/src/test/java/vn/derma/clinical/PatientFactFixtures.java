package vn.derma.clinical;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;

import java.util.Collection;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import vn.derma.clinical.client.PatientFactClient;
import vn.derma.clinical.client.PatientFactClient.GraphFact;
import vn.derma.clinical.client.PatientFactClient.GraphFacts;
import vn.derma.clinical.client.PatientFactClient.Lesion;

/** Dữ liệu mẫu trả về từ graph theo dõi (knowledge) cho các test của clinical. */
final class PatientFactFixtures {

    private PatientFactFixtures() {
    }

    static GraphFact fact(String id, String factType, String lesionId, int category, String label, String detail, String sourceMessageId) {
        return new GraphFact(id, factType, lesionId, category, "PT_X", label, null, detail, "", null, true, "current", "", "", "", "", null, null,
                "2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00", false, sourceMessageId, "none");
    }

    static final GraphFact ITCH = fact("f-itch", "symptom", "l1", 1, "Ngứa", "về đêm", "m1");
    static final GraphFact ALLERGY = fact("f-allergy", "allergy", null, 5, "Penicillin", "phát ban", null);

    /** Mọi hồ sơ đều có tổn thương `l1` (ngứa về đêm ở khuỷu tay) và một dị ứng dài hạn. */
    @SuppressWarnings("unchecked")
    static void stub(PatientFactClient client) {
        org.mockito.Mockito.reset(client); // stub lại sau khi đã cho ném lỗi: `when(...)` sẽ gọi chính stub cũ
        when(client.getFacts(anyString())).thenReturn(new GraphFacts(List.of(new Lesion("l1", "khuỷu tay", "skin")), List.of(ITCH, ALLERGY)));
        when(client.getLongTerm(any())).thenAnswer(i -> {
            Map<String, List<GraphFact>> out = new HashMap<>();
            ((Collection<String>) i.getArgument(0)).forEach(id -> out.put(id, List.of(ALLERGY)));
            return out;
        });
    }
}
