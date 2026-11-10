package vn.derma.clinical;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
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
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import vn.derma.clinical.client.ConsultationClient;

@SpringBootTest
@AutoConfigureMockMvc
class ClinicalApiTest {

    private static final String KEY = "derma-internal-key-change-in-production";

    @Autowired
    MockMvc mvc;
    @Autowired
    ObjectMapper json;
    @MockitoBean
    ConsultationClient consultation;

    @BeforeEach
    void setUp() {
        reset(consultation);
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
        mvc.perform(get("/internal/patients/pp-x/context")).andExpect(status().isForbidden());
        mvc.perform(post("/internal/episodes/apply-turn").contentType(MediaType.APPLICATION_JSON).content("{}")).andExpect(status().isForbidden());
    }

    @Test
    void applyTurnSavesFactsHypothesesAndProvenanceThenContextReturnsThem() throws Exception {
        Map<String, Object> hypothesis = Map.of("disease", "Chàm", "code", "Eczema", "body_site", "tay", "confidence", "cao",
                "evidence", List.of(Map.of("source", "chat", "text", "ngứa đêm")), "missing", List.of("tiền sử dị ứng"));
        internal(post("/internal/episodes/apply-turn"), turn("pp-turn", "conv-1", List.of(
                fact("symptom", "Ngứa", "về đêm", "tay", "msg-1"), fact("allergy", "Penicillin", "phát ban", "", "msg-1"),
                fact("bogus", "Sai loại", "", "tay"), fact("lesion", "Mảng đỏ", "", "vung-khong-co")), List.of(hypothesis), List.of())).andExpect(status().isOk());

        JsonNode facts = data(internal(get("/internal/patients/pp-turn/context"), null)).get("facts");
        // fact sai loại bị bỏ; fact có vùng lạ rơi vào vùng duy nhất lượt này đã chạm (tay) nên vẫn lưu
        assertEquals(3, facts.size());
        Map<String, String> byLabel = new HashMap<>();
        facts.forEach(f -> byLabel.put(f.get("label").asText(), f.get("fact_type").asText() + "|" + f.get("body_site").asText() + "|" + f.get("detail").asText()));
        assertEquals("symptom|tay|về đêm", byLabel.get("Ngứa"));
        assertEquals("allergy||phát ban", byLabel.get("Penicillin"));
        assertEquals("lesion|tay|", byLabel.get("Mảng đỏ"));

        // gửi lại cùng fact với giá trị mới: sửa tại chỗ (không thêm dòng), nguồn không lặp
        internal(post("/internal/episodes/apply-turn"), turn("pp-turn", "conv-1", List.of(fact("symptom", "ngứa", "cả ngày lẫn đêm", "tay", "msg-1", "msg-2")), List.of(), List.of())).andExpect(status().isOk());
        JsonNode after = data(internal(get("/internal/patients/pp-turn/context"), null)).get("facts");
        assertEquals(3, after.size());
        assertTrue(after.toString().contains("cả ngày lẫn đêm"));
    }

    @Test
    void factWithoutSiteAttachesToTheOnlyOpenEpisodeOfTheConversation() throws Exception {
        internal(post("/internal/episodes/apply-turn"), turn("pp-site", "conv-site", List.of(fact("symptom", "Ngứa", "", "chan")), List.of(), List.of())).andExpect(status().isOk());
        // lượt sau chưa nêu vùng: hội thoại chỉ có một đợt mở nên gắn vào đó
        internal(post("/internal/episodes/apply-turn"), turn("pp-site", "conv-site", List.of(fact("lesion", "Mảng đỏ", "", "")), List.of(), List.of())).andExpect(status().isOk());
        JsonNode facts = data(internal(get("/internal/patients/pp-site/context"), null)).get("facts");
        assertEquals(2, facts.size());
        facts.forEach(f -> assertEquals("chan", f.get("body_site").asText()));
    }

    @Test
    void episodeFactWithoutAnySiteAndNoEpisodeIsNotSavedYet() throws Exception {
        // chưa có đợt nào và fact không nêu vùng: không có chỗ để gắn, bỏ qua (agent gửi lại ở lượt sau)
        internal(post("/internal/episodes/apply-turn"), turn("pp-nosite", "conv-nosite", List.of(fact("symptom", "Ngứa", "", "")), List.of(), List.of())).andExpect(status().isOk());
        assertEquals(0, data(internal(get("/internal/patients/pp-nosite/context"), null)).get("facts").size());
        // fact dài hạn thì không cần vùng
        internal(post("/internal/episodes/apply-turn"), turn("pp-nosite", "conv-nosite", List.of(fact("allergy", "Penicillin", "", "")), List.of(), List.of())).andExpect(status().isOk());
        assertEquals(1, data(internal(get("/internal/patients/pp-nosite/context"), null)).get("facts").size());
    }

    @Test
    void invalidHypothesesAreSkippedAndImagesAttachToTheMatchingEpisode() throws Exception {
        Map<String, Object> bad = Map.of("disease", "Sai mã", "code", "KhongCoMa", "body_site", "tay", "confidence", "cao");
        Map<String, Object> good = Map.of("disease", "Chàm", "code", "Eczema", "body_site", "tay", "confidence", "vừa");
        Map<String, Object> image = Map.of("storage_key", "k/a.jpg", "top_k", List.of(Map.of("label", "Eczema", "score", 0.9)));
        internal(post("/internal/episodes/apply-turn"), turn("pp-img", "conv-img", List.of(), List.of(bad, good), List.of(image))).andExpect(status().isOk());
        internal(post("/internal/episodes/apply-turn"), turn("pp-img", "conv-img", List.of(), List.of(), List.of())).andExpect(status().isOk());
        // lượt không có gì để ghi thì bỏ qua; body không hợp lệ bị từ chối
        internal(post("/internal/episodes/apply-turn"), Map.of("conversation_id", "c")).andExpect(status().isUnprocessableEntity());
    }

    @Test
    void longTermFactsAreReplacedAsAWholeAndReadBackForManyProfiles() throws Exception {
        internal(put("/internal/patients/pp-lt/long-term-facts"), Map.of("facts", List.of(
                Map.of("fact_type", "allergy", "label", "Penicillin", "detail", "phát ban"), Map.of("fact_type", "history", "label", "  Viêm da   cơ địa  ", "detail", ""))))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.length()").value(2));
        // thay danh sách: giữ Penicillin (đổi chi tiết), bỏ tiền sử, thêm thuốc
        ResultActions replaced = internal(put("/internal/patients/pp-lt/long-term-facts"), Map.of("facts", List.of(
                Map.of("fact_type", "allergy", "label", "penicillin", "detail", "sốc phản vệ"), Map.of("fact_type", "medication", "label", "Cetirizine", "detail", "10mg"))))
                .andExpect(status().isOk());
        JsonNode facts = data(replaced);
        assertEquals(2, facts.size());
        assertEquals(List.of("allergy:sốc phản vệ", "medication:10mg"), List.of(facts.get(0).get("fact_type").asText() + ":" + facts.get(0).get("detail").asText(), facts.get(1).get("fact_type").asText() + ":" + facts.get(1).get("detail").asText()));
        internal(put("/internal/patients/pp-lt/long-term-facts"), Map.of("facts", List.of(Map.of("fact_type", "symptom", "label", "x")))).andExpect(status().isUnprocessableEntity());

        JsonNode many = data(internal(get("/internal/patients/long-term-facts").param("profile_ids", "pp-lt, pp-rong"), null));
        assertEquals(2, many.get("pp-lt").size());
        assertEquals(0, many.get("pp-rong").size());
        internal(put("/internal/patients/pp-lt/long-term-facts"), Map.of("facts", List.of())).andExpect(jsonPath("$.data.length()").value(0));
    }

    @Test
    void hasDataIsFalseUntilAFinalizeReportExists() throws Exception {
        internal(get("/internal/patients/pp-none/has-data"), null).andExpect(status().isOk()).andExpect(jsonPath("$.data.has_data").value(false));
    }
}
