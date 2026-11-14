package vn.derma.clinical;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.mockito.ArgumentCaptor;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import vn.derma.clinical.client.ConsultationClient;
import vn.derma.clinical.client.PatientFactClient;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.entity.ClinicalEpisode;
import vn.derma.clinical.repository.AiHypothesisRepository;
import vn.derma.clinical.repository.ClinicalEpisodeRepository;

@SpringBootTest
@AutoConfigureMockMvc
class ClinicalApiTest {

    private static final String KEY = "derma-internal-key-change-in-production";

    @Autowired
    MockMvc mvc;
    @Autowired
    ObjectMapper json;
    @Autowired
    ClinicalEpisodeRepository episodes;
    @Autowired
    AiHypothesisRepository hypotheses;
    @MockitoBean
    ConsultationClient consultation;
    @MockitoBean
    PatientFactClient patientFacts;

    @BeforeEach
    void setUp() {
        reset(consultation, patientFacts);
        when(consultation.getMessages(any())).thenAnswer(i -> {
            Map<String, ConsultationClient.MessageInfo> out = new HashMap<>();
            ((java.util.Collection<String>) i.getArgument(0)).forEach(id -> out.put(id,
                    new ConsultationClient.MessageInfo(id, "c1", "patient", "Tôi bị ngứa về đêm rất nhiều", "2026-01-01T00:00:00Z", List.of())));
            return out;
        });
    }

    ResultActions internal(MockHttpServletRequestBuilder request, Object body) throws Exception {
        request.header("X-Internal-Key", KEY);
        if (body != null) {
            request.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body));
        }
        return mvc.perform(request);
    }

    JsonNode data(ResultActions result) throws Exception {
        return json.readTree(result.andReturn().getResponse().getContentAsString()).get("data");
    }

    Map<String, Object> fact(String type, String label, String detail, String site, String... sources) {
        Map<String, Object> f = new HashMap<>();
        f.put("fact_type", type);
        f.put("template_label", label);
        f.put("detail", detail);
        f.put("body_site", site);
        f.put("source_messages", List.of(sources));
        return f;
    }

    Map<String, Object> turn(String profile, String conversation, List<Map<String, Object>> facts, List<Map<String, Object>> hypotheses, List<Map<String, Object>> images) {
        Map<String, Object> body = new HashMap<>();
        body.put("conversation_id", conversation);
        body.put("message_id", "m1");
        body.put("patient_profile_id", profile);
        body.put("facts", facts);
        body.put("hypotheses", hypotheses);
        body.put("image_predictions", images);
        return body;
    }

    @Test
    void internalEndpointsRequireTheKey() throws Exception {
        mvc.perform(get("/internal/patients/long-term-facts").param("profile_ids", "pp-x")).andExpect(status().isForbidden());
        mvc.perform(post("/internal/episodes/apply-turn").contentType(MediaType.APPLICATION_JSON).content("{}")).andExpect(status().isForbidden());
        // endpoint cũ cho agent kéo fact đã bỏ: agent đọc fact từ graph ở knowledge
        internal(get("/internal/patients/pp-x/context"), null).andExpect(status().is4xxClientError());
    }

    @Test
    void applyTurnSavesHypothesesAndIgnoresFacts() throws Exception {
        Map<String, Object> hypothesis = Map.of("disease", "Chàm", "code", "Eczema", "body_site", "tay", "confidence", "cao",
                "evidence", List.of(Map.of("source", "chat", "text", "ngứa đêm")), "missing", List.of("tiền sử dị ứng"));
        // `facts` nếu agent cũ còn gửi thì bị bỏ qua: clinical không còn bảng fact và không gọi knowledge để ghi
        internal(post("/internal/episodes/apply-turn"), turn("pp-turn", "conv-1", List.of(fact("symptom", "Ngứa", "về đêm", "tay", "msg-1")), List.of(hypothesis), List.of())).andExpect(status().isOk());
        ClinicalEpisode episode = episodes.findActive("pp-turn", "tay").orElseThrow();
        assertEquals(List.of("Chàm"), hypotheses.findByEpisodeIdOrderByRankAsc(episode.id).stream().map(h -> h.disease).toList());
        verifyNoInteractions(patientFacts);

        // gửi lại: giả thuyết được thay toàn bộ, không nhân đôi
        Map<String, Object> better = Map.of("disease", "Vảy nến", "code", "Psoriasis", "body_site", "tay", "confidence", "vừa");
        internal(post("/internal/episodes/apply-turn"), turn("pp-turn", "conv-1", List.of(), List.of(better), List.of())).andExpect(status().isOk());
        assertEquals(List.of("Vảy nến"), hypotheses.findByEpisodeIdOrderByRankAsc(episode.id).stream().map(h -> h.disease).toList());
    }

    @Test
    void hypothesisWithoutSiteAttachesToTheOnlyOpenEpisodeOfTheConversation() throws Exception {
        Map<String, Object> first = Map.of("disease", "Nấm da", "code", "Tinea", "body_site", "chan", "confidence", "vừa");
        internal(post("/internal/episodes/apply-turn"), turn("pp-site", "conv-site", List.of(), List.of(first), List.of())).andExpect(status().isOk());
        // lượt sau chưa nêu vùng: hội thoại chỉ có một đợt mở nên gắn vào đó
        Map<String, Object> later = Map.of("disease", "Chàm", "code", "Eczema", "body_site", "", "confidence", "cao");
        internal(post("/internal/episodes/apply-turn"), turn("pp-site", "conv-site", List.of(), List.of(later), List.of())).andExpect(status().isOk());
        ClinicalEpisode episode = episodes.findActive("pp-site", "chan").orElseThrow();
        assertEquals(List.of("Chàm"), hypotheses.findByEpisodeIdOrderByRankAsc(episode.id).stream().map(h -> h.disease).toList());
    }

    @Test
    void hypothesisWithoutAnySiteAndNoEpisodeIsNotSaved() throws Exception {
        Map<String, Object> orphan = Map.of("disease", "Chàm", "code", "Eczema", "body_site", "", "confidence", "cao");
        internal(post("/internal/episodes/apply-turn"), turn("pp-nosite", "conv-nosite", List.of(), List.of(orphan), List.of())).andExpect(status().isOk());
        assertTrue(episodes.findActiveOfProfile("pp-nosite").isEmpty());
    }

    @Test
    void invalidHypothesesAreSkippedAndImagesAttachToTheMatchingEpisode() throws Exception {
        Map<String, Object> bad = Map.of("disease", "Sai mã", "code", "KhongCoMa", "body_site", "tay", "confidence", "cao");
        Map<String, Object> good = Map.of("disease", "Chàm", "code", "Eczema", "body_site", "tay", "confidence", "vừa");
        Map<String, Object> image = Map.of("storage_key", "k/a.jpg", "top_k", List.of(Map.of("label", "Eczema", "score", 0.9)));
        internal(post("/internal/episodes/apply-turn"), turn("pp-img", "conv-img", List.of(), List.of(bad, good), List.of(image))).andExpect(status().isOk());
        ClinicalEpisode episode = episodes.findActive("pp-img", "tay").orElseThrow();
        assertEquals(List.of("Chàm"), hypotheses.findByEpisodeIdOrderByRankAsc(episode.id).stream().map(h -> h.disease).toList());
        assertTrue(episode.imagePredictions.contains("k/a.jpg"));
        internal(post("/internal/episodes/apply-turn"), turn("pp-img", "conv-img", List.of(), List.of(), List.of())).andExpect(status().isOk());
        // body không hợp lệ bị từ chối
        internal(post("/internal/episodes/apply-turn"), Map.of("conversation_id", "c")).andExpect(status().isUnprocessableEntity());
    }

    @Test
    void hasDataIsFalseUntilAFinalizeReportExists() throws Exception {
        internal(get("/internal/patients/pp-none/has-data"), null).andExpect(status().isOk()).andExpect(jsonPath("$.data.has_data").value(false));
    }
}
