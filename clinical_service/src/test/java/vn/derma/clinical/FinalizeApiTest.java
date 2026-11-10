package vn.derma.clinical;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.doThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Collection;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

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

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import vn.derma.clinical.client.ConsultationClient;
import vn.derma.clinical.client.IdentityClient;
import vn.derma.clinical.client.KnowledgeClient;
import vn.derma.clinical.service.AttachmentStore;

@SpringBootTest
@AutoConfigureMockMvc
class FinalizeApiTest {

    private static final String KEY = "derma-internal-key-change-in-production";
    private static final String SECRET = "derma-secret-key-change-in-production-datn-2026";

    @Autowired
    MockMvc mvc;
    @Autowired
    ObjectMapper json;
    @MockitoBean
    ConsultationClient consultation;
    @MockitoBean
    IdentityClient identity;
    @MockitoBean
    AttachmentStore store;
    @MockitoBean
    KnowledgeClient knowledge;

    @BeforeEach
    void setUp() {
        reset(consultation, identity, store, knowledge);
        when(knowledge.getHistoryHints(anyString())).thenReturn(new KnowledgeClient.HistoryHints(List.of("Viêm da cơ địa"), List.of("Tránh xà phòng")));
        when(knowledge.runIntent(anyString(), any(), org.mockito.ArgumentMatchers.anyInt())).thenReturn(new KnowledgeClient.IntentResult(List.of(Map.of("text", "Bệnh ứng viên theo đồ thị tri thức: Chàm (điểm 3)")), List.of()));
        when(consultation.getMessages(any())).thenAnswer(i -> {
            Map<String, ConsultationClient.MessageInfo> out = new HashMap<>();
            ((Collection<String>) i.getArgument(0)).forEach(id -> out.put(id, new ConsultationClient.MessageInfo(id, "c", "patient", "Ngứa về đêm", "2026-01-01T00:00:00Z", List.of())));
            return out;
        });
        when(store.presignedUrl(anyString())).thenAnswer(i -> "http://minio/" + i.getArgument(0));
        // hồ sơ pp-<user>; user "stranger" không sở hữu hồ sơ nào
        when(identity.resolveProfile(anyString(), any())).thenAnswer(i -> {
            String user = i.getArgument(0), profile = i.getArgument(1);
            boolean own = profile == null || profile.equals("pp-" + user);
            return own ? Optional.of(new IdentityClient.ProfileRef("pp-" + user, user, "Bệnh nhân")) : Optional.<IdentityClient.ProfileRef>empty();
        });
        when(identity.listProfilesOfUser(anyString())).thenAnswer(i -> List.of(detail("pp-" + i.getArgument(0))));
        when(identity.getProfiles(any())).thenAnswer(i -> {
            Map<String, IdentityClient.ProfileDetail> out = new HashMap<>();
            ((Collection<String>) i.getArgument(0)).forEach(id -> out.put(id, detail(id)));
            return out;
        });
        when(identity.getUser(anyString())).thenAnswer(i -> Optional.of(new IdentityClient.UserRef(i.getArgument(0), "BS " + i.getArgument(0), "doctor")));
    }

    IdentityClient.ProfileDetail detail(String id) {
        return new IdentityClient.ProfileDetail(id, id.substring(3), "Nguyễn Văn A", "2000-01-01", "male", "self", null);
    }

    String token(String userId, String role) throws Exception {
        JWTClaimsSet claims = new JWTClaimsSet.Builder().subject(userId).claim("role", role).claim("type", "access")
                .expirationTime(Date.from(Instant.now().plusSeconds(600))).build();
        SignedJWT jwt = new SignedJWT(new JWSHeader(JWSAlgorithm.HS256), claims);
        jwt.sign(new MACSigner(SECRET.getBytes(StandardCharsets.UTF_8)));
        return jwt.serialize();
    }

    ResultActions call(MockHttpServletRequestBuilder request, String bearer, Object body) throws Exception {
        request.header("Authorization", "Bearer " + bearer);
        if (body != null) {
            request.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body));
        }
        return mvc.perform(request);
    }

    JsonNode data(ResultActions result) throws Exception {
        return json.readTree(result.andReturn().getResponse().getContentAsString()).get("data");
    }

    /** Tạo đợt bệnh có giả thuyết cho hồ sơ của user qua apply-turn, trả về id đợt. */
    String seedEpisode(String user, boolean withHypothesis) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("conversation_id", "conv-" + user);
        body.put("message_id", "m1");
        body.put("patient_profile_id", "pp-" + user);
        body.put("facts", List.of(Map.of("fact_type", "symptom", "template_label", "Ngứa", "detail", "về đêm", "body_site", "tay", "source_messages", List.of("m1")),
                Map.of("fact_type", "allergy", "template_label", "Penicillin", "detail", "phát ban", "body_site", "", "source_messages", List.of())));
        body.put("hypotheses", withHypothesis ? List.of(Map.of("disease", "Chàm", "code", "Eczema", "body_site", "tay", "confidence", "cao",
                "evidence", List.of(Map.of("source", "chat", "text", "ngứa đêm")), "missing", List.of("tiền sử"))) : List.of());
        body.put("image_predictions", List.of());
        mvc.perform(post("/internal/episodes/apply-turn").header("X-Internal-Key", KEY).contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body)))
                .andExpect(status().isOk());
        JsonNode episodes = data(call(get("/api/v1/patient-profiles/pp-" + user + "/episodes"), token(user, "patient"), null).andExpect(status().isOk()));
        return episodes.get(0).get("id").asText();
    }

    Map<String, Object> book(String user, String episodeId, long secondsFromNow) {
        return Map.of("patient_profile_id", "pp-" + user, "episode_id", episodeId, "scheduled_at", Instant.now().plusSeconds(secondsFromNow).toString(), "reason", "khám");
    }

    Map<String, Object> form(JsonNode draftFacts, String code) {
        Map<String, Object> body = new HashMap<>();
        body.put("diagnosis", "Chàm thể tạng");
        body.put("notes", "theo dõi");
        body.put("is_reference_case", true);
        body.put("reasoning", "ngứa đêm, mảng đỏ");
        body.put("urgency", "monitor");
        body.put("instructions", List.of("Bôi kem dưỡng ẩm", " "));
        List<Map<String, Object>> facts = new java.util.ArrayList<>();
        for (JsonNode f : draftFacts) {
            Map<String, Object> item = new HashMap<>();
            item.put("source_fact_id", f.get("source_fact_id").asText());
            item.put("fact_type", f.get("fact_type").asText());
            // sửa chi tiết của triệu chứng để kiểm origin doctor_corrected; còn lại giữ nguyên
            item.put("label", f.get("label").asText());
            item.put("detail", f.get("fact_type").asText().equals("symptom") ? "ngứa liên tục" : f.get("detail").asText());
            facts.add(item);
        }
        facts.add(Map.of("fact_type", "lesion", "label", "Mảng đỏ", "detail", "bờ rõ"));
        body.put("facts", facts);
        body.put("images", List.of(Map.of("file_id", "khong/thuoc/ve/benh-nhan.jpg", "body_site", "tay")));
        if (code != null) {
            body.put("diagnosis_code", code);
        }
        return body;
    }

    @Test
    void encounterFinalizeClosesVisitUpdatesFactsAndPublishesCase() throws Exception {
        String user = "fin-enc", episode = seedEpisode(user, true);
        String patient = token(user, "patient"), doctor = token("doc-f", "doctor");
        String appointment = data(call(post("/api/v1/appointments"), patient, book(user, episode, 3600))).get("id").asText();
        call(post("/api/v1/doctor/appointments/" + appointment + "/confirm"), doctor, null).andExpect(status().isOk());
        String encounter = data(call(post("/api/v1/doctor/appointments/" + appointment + "/start"), doctor, null)).get("encounter_id").asText();

        JsonNode draft = data(call(get("/api/v1/doctor/encounters/" + encounter + "/finalize-draft"), doctor, null).andExpect(status().isOk()));
        assertEquals(2, draft.get("facts").size());
        assertEquals("Chàm", draft.get("suggestions").get("candidate_diseases").get(0).asText().contains("Chàm") ? "Chàm" : "?");
        assertEquals(true, draft.get("diagnosis_options").size() > 5);
        assertEquals("Ngứa về đêm", draft.get("facts").get(0).get("provenances").size() > 0 ? "Ngứa về đêm" : "");

        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, form(draft.get("facts"), null)).andExpect(status().isUnprocessableEntity());
        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), token("doc-khac", "doctor"), form(draft.get("facts"), "Eczema")).andExpect(status().isForbidden());
        JsonNode report = data(call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, form(draft.get("facts"), "Eczema")).andExpect(status().isCreated()));

        assertEquals("Eczema", report.get("diagnosis_code").asText());
        assertEquals(true, report.get("is_reference_case").asBoolean());
        // ảnh không thuộc bệnh nhân bị bỏ
        assertEquals(0, report.get("images").size());
        JsonNode snapshotFacts = report.get("snapshot").get("clinical_facts");
        assertEquals(3, snapshotFacts.size());
        assertEquals("doctor_corrected", snapshotFacts.get(0).get("origin").asText().equals("doctor_corrected") || snapshotFacts.get(1).get("origin").asText().equals("doctor_corrected") ? "doctor_corrected" : "?");
        assertEquals("Penicillin (phát ban)", report.get("snapshot").get("patient_profile").get("allergies").asText());
        assertEquals(1, report.get("snapshot").get("assessment").get("instructions").size());

        // lịch hẹn thành done, đợt đóng nên không còn trong danh sách đợt có thể đặt
        call(get("/api/v1/appointments"), patient, null).andExpect(jsonPath("$.data[0].status").value("done"));
        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, form(draft.get("facts"), "Eczema")).andExpect(status().isConflict());
        verify(knowledge, times(1)).postCase(any(), anyString());

        // lịch sử: bác sĩ, bệnh nhân (không lộ cờ nội bộ) và danh sách cho knowledge
        call(get("/api/v1/doctor/finalize-reports").param("q", "chàm"), doctor, null).andExpect(jsonPath("$.data[0].patient.full_name").value("Nguyễn Văn A"));
        call(get("/api/v1/doctor/finalize-reports").param("q", "khong-co-gi"), doctor, null).andExpect(jsonPath("$.data.length()").value(0));
        call(get("/api/v1/patient-profiles/pp-" + user + "/finalize-reports"), patient, null).andExpect(jsonPath("$.data[0].is_reference_case").doesNotExist())
                .andExpect(jsonPath("$.data[0].diagnosis").value("Chàm thể tạng"));
        call(get("/api/v1/doctor/patient-profiles/pp-" + user + "/finalize-reports"), doctor, null).andExpect(jsonPath("$.data[0].encounter_id").value(encounter));
        mvc.perform(get("/internal/finalize-reports").param("page", "1").param("page_size", "50").header("X-Internal-Key", KEY)).andExpect(status().isOk())
                .andExpect(jsonPath("$.data[?(@.report_id=='" + report.get("id").asText() + "')].snapshot.clinical_facts.length()").value(3));
    }

    @Test
    void sessionFinalizeNeedsActiveSessionAndRetryOnlyClosesTheSession() throws Exception {
        String user = "fin-ses", doctor = token("doc-s", "doctor");
        seedEpisode(user, true);
        when(consultation.getSession("s1")).thenReturn(new ConsultationClient.SessionInfo("s1", "conv-" + user, "pp-" + user, "doc-s", "BS s", "pending"));
        JsonNode facts = data(call(get("/api/v1/doctor/consultations/s1/finalize-draft"), doctor, null).andExpect(status().isOk())).get("facts");
        call(post("/api/v1/doctor/consultations/s1/finalize"), doctor, form(facts, null)).andExpect(status().isConflict());

        when(consultation.getSession("s1")).thenReturn(new ConsultationClient.SessionInfo("s1", "conv-" + user, "pp-" + user, "doc-s", "BS s", "active"));
        doThrow(vn.derma.clinical.common.AppException.badGateway("mất kết nối")).doNothing().when(consultation).markSessionFinalized("s1", "doc-s");
        call(post("/api/v1/doctor/consultations/s1/finalize"), doctor, form(facts, null)).andExpect(status().isBadGateway());
        // báo cáo đã lưu; gọi lại chỉ đóng phiên, không tạo báo cáo thứ hai
        call(post("/api/v1/doctor/consultations/s1/finalize"), doctor, form(facts, null)).andExpect(status().isCreated()).andExpect(jsonPath("$.data.consultation_session_id").value("s1"));
        call(get("/api/v1/doctor/consultations/s1/finalize-reports"), doctor, null).andExpect(jsonPath("$.data.length()").value(1));
        verify(knowledge, times(1)).postCase(any(), anyString());

        when(consultation.getSession("s2")).thenReturn(new ConsultationClient.SessionInfo("s2", "c", "pp-" + user, "doc-khac", "BS", "active"));
        call(get("/api/v1/doctor/consultations/s2/finalize-draft"), doctor, null).andExpect(status().isForbidden());
    }
}
