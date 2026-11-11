package vn.derma.clinical;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.never;
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
import vn.derma.clinical.client.AiClient;
import vn.derma.clinical.client.ConsultationClient;
import vn.derma.clinical.common.AppException;
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
    @MockitoBean
    AiClient ai;

    @BeforeEach
    void setUp() {
        reset(consultation, identity, store, knowledge, ai);
        // mô tả của bác sĩ → một tổn thương mới và đổi chi tiết của triệu chứng "Ngứa" đã có
        when(ai.extractFactsFromDescription(anyString(), anyString(), any())).thenReturn(List.of(new AiClient.DescribedFact("lesion", "Mảng đỏ", "bờ rõ"), new AiClient.DescribedFact("symptom", "ngứa", "liên tục")));
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
        body.put("description", "Mảng đỏ bờ rõ ở khuỷu tay, bệnh nhân ngứa liên tục.");
        body.put("urgency", "monitor");
        body.put("instructions", List.of("Bôi kem dưỡng ẩm", " "));
        // bác sĩ chỉ giữ nguyên dữ kiện AI ghi nhận (dữ kiện bỏ khỏi danh sách là bị xoá); dữ kiện mới đến từ mô tả
        List<Map<String, Object>> facts = new java.util.ArrayList<>();
        for (JsonNode f : draftFacts) {
            facts.add(Map.of("source_fact_id", f.get("source_fact_id").asText(), "fact_type", f.get("fact_type").asText(), "label", f.get("label").asText(),
                    "detail", f.get("detail").asText()));
        }
        body.put("facts", facts);
        body.put("images", List.of(Map.of("file_id", "khong/thuoc/ve/benh-nhan.jpg", "body_site", "tay")));
        if (code != null) {
            body.put("diagnosis_code", code);
        }
        return body;
    }

    /** Đặt lịch → xác nhận → bắt đầu khám; trả {mã lịch, mã lần khám}. */
    String[] startEncounter(String user, String doctor) throws Exception {
        String episode = seedEpisode(user, true);
        String appointment = data(call(post("/api/v1/appointments"), token(user, "patient"), book(user, episode, 3600))).get("id").asText();
        call(post("/api/v1/doctor/appointments/" + appointment + "/confirm"), doctor, null).andExpect(status().isOk());
        String encounter = data(call(post("/api/v1/doctor/appointments/" + appointment + "/start"), doctor, null)).get("encounter_id").asText();
        return new String[] { appointment, encounter };
    }

    @Test
    void encounterFinalizeClosesVisitUpdatesFactsAndPublishesCase() throws Exception {
        String user = "fin-enc";
        String patient = token(user, "patient"), doctor = token("doc-f", "doctor");
        String[] started = startEncounter(user, doctor);
        String appointment = started[0], encounter = started[1];

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
        // origin: "Ngứa" bị mô tả đổi chi tiết → doctor_corrected; "Mảng đỏ" chỉ có trong mô tả → doctor_observed; Penicillin giữ nguyên → patient_reported
        Map<String, String> origins = new HashMap<>();
        snapshotFacts.forEach(f -> origins.put(f.get("label").asText(), f.get("origin").asText()));
        assertEquals(Map.of("Ngứa", "doctor_corrected", "Mảng đỏ", "doctor_observed", "Penicillin", "patient_reported"), origins);
        snapshotFacts.forEach(f -> {
            if (f.get("label").asText().equals("Ngứa")) {
                assertEquals("liên tục", f.get("detail").asText());
            }
        });
        assertEquals("Mảng đỏ bờ rõ ở khuỷu tay, bệnh nhân ngứa liên tục.", report.get("snapshot").get("assessment").get("description").asText());
        // ai nhận đúng mô tả, tên vùng và các dữ kiện đã giữ
        verify(ai, times(1)).extractFactsFromDescription(eq("Mảng đỏ bờ rõ ở khuỷu tay, bệnh nhân ngứa liên tục."), eq("Tay"), argThat(k -> k.size() == 2));
        // mọi dữ kiện (giữ nguyên và mới từ mô tả) đều đã xác nhận
        JsonNode after = data(call(get("/api/v1/doctor/appointments/" + appointment), doctor, null).andExpect(status().isOk()));
        int checked = 0;
        for (JsonNode f : after.get("episode").get("facts")) {
            assertNotNull(f.get("verified_at").asText(null));
            checked++;
        }
        for (JsonNode f : after.get("long_term_facts")) {
            assertNotNull(f.get("verified_at").asText(null));
            checked++;
        }
        assertEquals(3, checked);
        assertEquals("Penicillin (phát ban)", report.get("snapshot").get("patient_profile").get("allergies").asText());
        assertEquals(1, report.get("snapshot").get("assessment").get("instructions").size());

        // lịch hẹn thành done, đợt đóng nên không còn trong danh sách đợt có thể đặt
        call(get("/api/v1/appointments"), patient, null).andExpect(jsonPath("$.data[0].status").value("done"));
        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, form(draft.get("facts"), "Eczema")).andExpect(status().isConflict());
        verify(knowledge, times(1)).postCase(any(), anyString());
        // chốt xong thì đặt hạn kênh theo dõi = chốt + 30 ngày (followup-days)
        verify(consultation).openFollowupUntil(eq(encounter), eq("pp-" + user), eq("doc-f"), argThat(t -> t.isAfter(java.time.Instant.now().plus(java.time.Duration.ofDays(29)))));

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
    void descriptionAndReasoningAreRequiredBeforeCallingAi() throws Exception {
        String doctor = token("doc-req", "doctor");
        String encounter = startEncounter("fin-req", doctor)[1];
        JsonNode draft = data(call(get("/api/v1/doctor/encounters/" + encounter + "/finalize-draft"), doctor, null).andExpect(status().isOk()));

        Map<String, Object> noDescription = form(draft.get("facts"), "Eczema");
        noDescription.put("description", "  ");
        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, noDescription).andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.detail").value(org.hamcrest.Matchers.containsString("Mô tả của bác sĩ là bắt buộc")));
        Map<String, Object> noReasoning = form(draft.get("facts"), "Eczema");
        noReasoning.remove("reasoning");
        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, noReasoning).andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.detail").value(org.hamcrest.Matchers.containsString("Cơ sở nhận định là bắt buộc")));
        Map<String, Object> noDiagnosis = form(draft.get("facts"), "Eczema");
        noDiagnosis.put("diagnosis", "");
        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, noDiagnosis).andExpect(status().isUnprocessableEntity())
                .andExpect(jsonPath("$.detail").value(org.hamcrest.Matchers.containsString("Nhận định là bắt buộc")));
        verify(ai, never()).extractFactsFromDescription(anyString(), anyString(), any());
    }

    @Test
    void aiFailureDoesNotFinalizeAndCanBeRetried() throws Exception {
        String user = "fin-ai";
        String doctor = token("doc-ai", "doctor");
        String[] started = startEncounter(user, doctor);
        String encounter = started[1];
        JsonNode draft = data(call(get("/api/v1/doctor/encounters/" + encounter + "/finalize-draft"), doctor, null).andExpect(status().isOk()));

        when(ai.extractFactsFromDescription(anyString(), anyString(), any())).thenThrow(AppException.badGateway("Chưa chuyển được mô tả thành dữ kiện, vui lòng thử lại."));
        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, form(draft.get("facts"), "Eczema")).andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.detail").value("Chưa chuyển được mô tả thành dữ kiện, vui lòng thử lại."));
        // không tạo báo cáo, không nạp knowledge, lần khám và lịch vẫn đang khám
        verify(knowledge, never()).postCase(any(), anyString());
        call(get("/api/v1/doctor/finalize-reports"), doctor, null).andExpect(jsonPath("$.data.length()").value(0));
        call(get("/api/v1/appointments"), token(user, "patient"), null).andExpect(jsonPath("$.data[0].status").value("in_progress"));

        // ai phục hồi thì chốt lại được
        // doReturn: `when(ai.…)` sẽ gọi lại mock đang ném lỗi
        org.mockito.Mockito.doReturn(List.of()).when(ai).extractFactsFromDescription(anyString(), anyString(), any());
        call(post("/api/v1/doctor/encounters/" + encounter + "/finalize"), doctor, form(draft.get("facts"), "Eczema")).andExpect(status().isCreated());
    }
}
