package vn.derma.clinical;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
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
import vn.derma.clinical.service.AttachmentStore;

@SpringBootTest
@AutoConfigureMockMvc
class AppointmentApiTest {

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

    @BeforeEach
    void setUp() {
        reset(consultation, identity, store);
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
                "evidence", List.of(Map.of("source", "chat", "text", "ngứa đêm", "ref", Map.of("document_id", "doc1", "chunk_id", "c1", "page_start", 12, "page_end", 13))),
                "missing", List.of("tiền sử"))) : List.of());
        body.put("image_predictions", List.of());
        mvc.perform(post("/internal/episodes/apply-turn").header("X-Internal-Key", KEY).contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body)))
                .andExpect(status().isOk());
        JsonNode episodes = data(call(get("/api/v1/patient-profiles/pp-" + user + "/episodes"), token(user, "patient"), null).andExpect(status().isOk()));
        return episodes.get(0).get("id").asText();
    }

    Map<String, Object> book(String user, String episodeId, long secondsFromNow) {
        return Map.of("patient_profile_id", "pp-" + user, "episode_id", episodeId, "scheduled_at", Instant.now().plusSeconds(secondsFromNow).toString(), "reason", "khám");
    }

    @Test
    void episodeWithoutHypothesisIsNotBookable() throws Exception {
        String episode = seedEpisode("ap-nohyp", false);
        JsonNode episodes = data(call(get("/api/v1/patient-profiles/pp-ap-nohyp/episodes"), token("ap-nohyp", "patient"), null));
        assertEquals(false, episodes.get(0).get("bookable").asBoolean());
        call(post("/api/v1/appointments"), token("ap-nohyp", "patient"), book("ap-nohyp", episode, 3600)).andExpect(status().isUnprocessableEntity());
    }

    @Test
    void patientBooksThenCannotBookTwiceAndCanCancelAndRebook() throws Exception {
        String user = "ap-book", episode = seedEpisode(user, true);
        String bearer = token(user, "patient");
        call(post("/api/v1/appointments"), bearer, book(user, episode, -60)).andExpect(status().isUnprocessableEntity());
        String id = data(call(post("/api/v1/appointments"), bearer, book(user, episode, 3600)).andExpect(status().isCreated())).get("id").asText();
        call(post("/api/v1/appointments"), bearer, book(user, episode, 7200)).andExpect(status().isUnprocessableEntity());
        call(get("/api/v1/appointments"), bearer, null).andExpect(jsonPath("$.data[0].status").value("requested")).andExpect(jsonPath("$.data[0].body_site_label").exists());

        call(post("/api/v1/appointments/" + id + "/cancel"), bearer, Map.of("reason", "bận")).andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("cancelled"));
        call(post("/api/v1/appointments/" + id + "/cancel"), bearer, Map.of("reason", "bận")).andExpect(status().isConflict());
        call(post("/api/v1/appointments"), bearer, book(user, episode, 7200)).andExpect(status().isCreated());
    }

    @Test
    void strangerCannotUseSomeoneElsesProfileOrAppointment() throws Exception {
        String user = "ap-own", episode = seedEpisode(user, true);
        call(get("/api/v1/patient-profiles/pp-" + user + "/episodes"), token("stranger", "patient"), null).andExpect(status().isNotFound());
        String id = data(call(post("/api/v1/appointments"), token(user, "patient"), book(user, episode, 3600))).get("id").asText();
        call(post("/api/v1/appointments/" + id + "/cancel"), token("stranger", "patient"), Map.of("reason", "x")).andExpect(status().isNotFound());
        call(get("/api/v1/doctor/appointments"), token(user, "patient"), null).andExpect(status().isForbidden());
    }

    @Test
    void doctorConfirmsStartsEncounterAndLocksEpisode() throws Exception {
        String user = "ap-doc", episode = seedEpisode(user, true);
        String id = data(call(post("/api/v1/appointments"), token(user, "patient"), book(user, episode, 3600))).get("id").asText();
        String doctor = token("doc-1", "doctor");

        call(post("/api/v1/doctor/appointments/" + id + "/start"), doctor, null).andExpect(status().isConflict());
        JsonNode confirmed = data(call(post("/api/v1/doctor/appointments/" + id + "/confirm"), doctor, null).andExpect(status().isOk()));
        assertEquals("confirmed", confirmed.get("status").asText());
        assertEquals("BS doc-1", confirmed.get("doctor_name").asText());
        assertEquals("Chàm", confirmed.get("top_hypothesis").asText());
        assertNotNull(confirmed.get("episode").get("summary").asText());
        assertEquals(1, confirmed.get("long_term_facts").size());
        assertEquals("Ngứa về đêm", confirmed.get("episode").get("facts").get(0).get("source_messages").get(0).get("content").asText());

        // bác sĩ khác không đụng được lịch đã có người phụ trách
        call(post("/api/v1/doctor/appointments/" + id + "/no-show"), token("doc-2", "doctor"), null).andExpect(status().isForbidden());

        JsonNode started = data(call(post("/api/v1/doctor/appointments/" + id + "/start"), doctor, null).andExpect(status().isOk()));
        assertEquals("in_progress", started.get("status").asText());
        assertNotNull(started.get("encounter_id").asText());
        // kênh theo dõi mở sau khi commit lúc bắt đầu khám
        verify(consultation).openFollowupChannel(started.get("encounter_id").asText(), started.get("patient").get("id").asText(), "doc-1");
        assertEquals(true, started.get("episode").get("hypotheses_locked").asBoolean());
        // truy vết trích dẫn: `ref` của bằng chứng đi nguyên vẹn ra API bác sĩ
        JsonNode ref = started.get("episode").get("hypotheses").get(0).get("evidence").get(0).get("ref");
        assertEquals("doc1", ref.get("document_id").asText());
        assertEquals(13, ref.get("page_end").asInt());
        call(post("/api/v1/doctor/appointments/" + id + "/cancel"), doctor, Map.of("reason", "x")).andExpect(status().isConflict());

        call(get("/api/v1/doctor/appointments"), doctor, null).andExpect(status().isOk()).andExpect(jsonPath("$.data[?(@.id=='" + id + "')].status").value("in_progress"));
        call(get("/api/v1/doctor/appointments").param("status", "requested").param("start", "2000-01-01T00:00:00Z"), doctor, null).andExpect(status().isOk());
    }
}
