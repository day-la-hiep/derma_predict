package vn.derma.identity;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Duration;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import vn.derma.identity.client.ClinicalClient;
import vn.derma.identity.client.ConsultationClient;
import vn.derma.identity.dto.PatientProfileDtos.ProfileFactOutput;

@SpringBootTest
@AutoConfigureMockMvc
class IdentityApiTest {

    @Autowired
    MockMvc mvc;
    @Autowired
    ObjectMapper json;
    @MockitoBean
    StringRedisTemplate redis;
    @MockitoBean
    ClinicalClient clinical;
    @MockitoBean
    ConsultationClient consultation;

    final Set<String> refreshKeys = new HashSet<>();

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUpFakes() {
        ValueOperations<String, String> ops = org.mockito.Mockito.mock(ValueOperations.class);
        when(redis.opsForValue()).thenReturn(ops);
        org.mockito.Mockito.doAnswer(i -> refreshKeys.add(i.getArgument(0))).when(ops).set(anyString(), anyString(), org.mockito.ArgumentMatchers.any(Duration.class));
        when(redis.delete(anyString())).thenAnswer(i -> refreshKeys.remove((String) i.getArgument(0)));
        when(clinical.getLongTermFacts(org.mockito.ArgumentMatchers.anyList())).thenReturn(Map.of());
        when(clinical.hasPatientData(anyString())).thenReturn(false);
        when(consultation.hasPatientData(anyString())).thenReturn(false);
    }

    ResultActions send(org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder request, String token, Object body) throws Exception {
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        if (body != null) {
            request.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body));
        }
        return mvc.perform(request);
    }

    JsonNode register(String username) throws Exception {
        String body = send(post("/api/v1/auth/register"), null,
                Map.of("username", username, "password", "matkhau123", "full_name", "Nguyễn An", "dob", "1990-05-01", "gender", "male"))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        return json.readTree(body).get("data");
    }

    @Test
    void registerLoginMeAndRefreshRotation() throws Exception {
        JsonNode data = register("an.nguyen");
        send(post("/api/v1/auth/register"), null, Map.of("username", "an.nguyen", "password", "matkhau123", "full_name", "X", "dob", "1990-01-01", "gender", "male"))
                .andExpect(status().isConflict());
        send(post("/api/v1/auth/login"), null, Map.of("username", "an.nguyen", "password", "sai")).andExpect(status().isUnauthorized());

        String body = send(post("/api/v1/auth/login"), null, Map.of("username", "an.nguyen", "password", "matkhau123"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.token_type").value("bearer"))
                .andExpect(jsonPath("$.data.user.role").value("patient")).andReturn().getResponse().getContentAsString();
        JsonNode login = json.readTree(body).get("data");
        send(get("/api/v1/auth/me"), login.get("access_token").asText(), null)
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.username").value("an.nguyen")).andExpect(jsonPath("$.data.gender").value("male"));
        send(get("/api/v1/auth/me"), null, null).andExpect(status().isUnauthorized());

        String refresh = login.get("refresh_token").asText();
        send(post("/api/v1/auth/refresh"), null, Map.of("refresh_token", refresh)).andExpect(status().isOk());
        send(post("/api/v1/auth/refresh"), null, Map.of("refresh_token", refresh)).andExpect(status().isUnauthorized());
        send(post("/api/v1/auth/refresh"), null, Map.of("refresh_token", data.get("access_token").asText())).andExpect(status().isUnauthorized());
    }

    @Test
    void seededDemoAccountsCanLogInWithTheirRoles() throws Exception {
        for (String[] account : new String[][] {{"user-1", "patient"}, {"doctor-1", "doctor"}, {"admin-1", "admin"}}) {
            send(post("/api/v1/auth/login"), null, Map.of("username", account[0], "password", "123456"))
                    .andExpect(status().isOk()).andExpect(jsonPath("$.data.user.id").value(account[0])).andExpect(jsonPath("$.data.user.role").value(account[1]));
        }
        String token = json.readTree(send(post("/api/v1/auth/login"), null, Map.of("username", "user-1", "password", "123456"))
                .andReturn().getResponse().getContentAsString()).get("data").get("access_token").asText();
        send(get("/api/v1/patient-profiles"), token, null).andExpect(jsonPath("$.data.length()").value(4)).andExpect(jsonPath("$.data[0].id").exists());
    }

    @Test
    void internalProfileResolveRequiresKeyAndChecksOwnership() throws Exception {
        String key = "derma-internal-key-change-in-production";
        mvc.perform(get("/internal/patient-profiles/resolve").param("user_id", "user-1")).andExpect(status().isForbidden());
        // không chọn hồ sơ: lấy hồ sơ đầu tiên của tài khoản
        mvc.perform(get("/internal/patient-profiles/resolve").param("user_id", "user-1").header("X-Internal-Key", key))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.user_id").value("user-1")).andExpect(jsonPath("$.data.id").exists());
        mvc.perform(get("/internal/patient-profiles/resolve").param("user_id", "user-1").param("profile_id", "pp-user-1-child").header("X-Internal-Key", key))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.id").value("pp-user-1-child"));
        // hồ sơ của người khác, hoặc tài khoản không có hồ sơ: 404
        mvc.perform(get("/internal/patient-profiles/resolve").param("user_id", "doctor-1").param("profile_id", "pp-user-1-child").header("X-Internal-Key", key))
                .andExpect(status().isNotFound());
        mvc.perform(get("/internal/patient-profiles/resolve").param("user_id", "admin-1").header("X-Internal-Key", key)).andExpect(status().isNotFound());
    }

    @Test
    void internalUserAndProfileLookupsServeOtherServices() throws Exception {
        String key = "derma-internal-key-change-in-production";
        mvc.perform(get("/internal/users/doctor-1").header("X-Internal-Key", key))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.full_name").value("BS. Trần Thị Bình")).andExpect(jsonPath("$.data.role").value("doctor"));
        mvc.perform(get("/internal/users/khong-co").header("X-Internal-Key", key)).andExpect(status().isNotFound());
        mvc.perform(get("/internal/users/doctor-1")).andExpect(status().isForbidden());
        mvc.perform(get("/internal/patient-profiles").param("ids", "pp-user-1-self, pp-user-1-child,khong-co").header("X-Internal-Key", key))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.length()").value(2)).andExpect(jsonPath("$.data[0].gender").exists())
                .andExpect(jsonPath("$.data[?(@.id=='pp-user-1-child')].relationship").value("child"));
    }

    @Test
    void internalProfilesOfUserListsAllProfilesOfAnAccount() throws Exception {
        mvc.perform(get("/internal/patient-profiles/by-user").param("user_id", "user-1").header("X-Internal-Key", "derma-internal-key-change-in-production"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.length()").value(4)).andExpect(jsonPath("$.data[0].user_id").value("user-1"));
        mvc.perform(get("/internal/patient-profiles/by-user").param("user_id", "admin-1").header("X-Internal-Key", "derma-internal-key-change-in-production"))
                .andExpect(jsonPath("$.data.length()").value(0));
    }

    @Test
    void validationErrorsAreReturnedAsDetail() throws Exception {
        send(post("/api/v1/auth/register"), null, Map.of("username", "ab", "password", "1", "full_name", "X", "dob", "1990-01-01", "gender", "male"))
                .andExpect(status().isUnprocessableEntity()).andExpect(jsonPath("$.detail").exists());
    }

    @Test
    void profilesCrudWithFactsFromClinical() throws Exception {
        String token = register("binh.tran").get("access_token").asText();
        send(patch("/api/v1/auth/me"), token, Map.of("full_name", "Trần Bình")).andExpect(status().isOk()).andExpect(jsonPath("$.data.full_name").value("Trần Bình"));

        String listed = send(get("/api/v1/patient-profiles"), token, null).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.length()").value(1)).andReturn().getResponse().getContentAsString();
        String ownId = json.readTree(listed).get("data").get(0).get("id").asText();

        when(clinical.replaceLongTermFacts(anyString(), org.mockito.ArgumentMatchers.anyList()))
                .thenReturn(List.of(new ProfileFactOutput("f1", "allergy", "Penicillin", "phát ban", null)));
        String created = send(post("/api/v1/patient-profiles"), token, Map.of("full_name", "Bé Na", "dob", "2020-01-01", "gender", "female",
                "relationship", "child", "long_term_facts", List.of(Map.of("fact_type", "allergy", "label", "Penicillin", "detail", "phát ban"))))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.data.relationship").value("child"))
                .andExpect(jsonPath("$.data.long_term_facts[0].label").value("Penicillin")).andReturn().getResponse().getContentAsString();
        String childId = json.readTree(created).get("data").get("id").asText();

        // FE gửi phone: null để xoá số, không gửi phone thì giữ nguyên
        send(patch("/api/v1/patient-profiles/" + childId), token, Map.of("phone", "0900000000")).andExpect(jsonPath("$.data.phone").value("0900000000"));
        send(patch("/api/v1/patient-profiles/" + childId), token, Map.of("full_name", "Bé Na 2")).andExpect(jsonPath("$.data.phone").value("0900000000"));
        send(patch("/api/v1/patient-profiles/" + childId), token, new java.util.HashMap<>(Map.of("phone", "")) {
            {
                put("phone", null);
            }
        }).andExpect(jsonPath("$.data.phone").doesNotExist());

        when(clinical.hasPatientData(childId)).thenReturn(true);
        send(delete("/api/v1/patient-profiles/" + childId), token, null).andExpect(status().isConflict());
        when(clinical.hasPatientData(childId)).thenReturn(false);
        send(delete("/api/v1/patient-profiles/" + childId), token, null).andExpect(status().isNoContent());
        send(delete("/api/v1/patient-profiles/" + ownId), token, null).andExpect(status().isConflict());
        send(patch("/api/v1/patient-profiles/khong-co"), token, Map.of("full_name", "X")).andExpect(status().isNotFound());
    }
}
