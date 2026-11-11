package vn.derma.consultation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.reset;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
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
import vn.derma.consultation.client.AiClient;
import vn.derma.consultation.client.IdentityClient;
import vn.derma.consultation.service.AttachmentStore;
import vn.derma.consultation.service.ConversationEvents;
import vn.derma.consultation.service.PubSubStreams;

@SpringBootTest
@AutoConfigureMockMvc
class ConsultationApiTest {

    private static final String SECRET = "derma-secret-key-change-in-production-datn-2026";
    private static final String INTERNAL_KEY = "derma-internal-key-change-in-production";
    /** Access token do `core/app/config/security.py` (PyJWT) ký, hạn tới 2100: consultation phải đọc được token Python. */
    private static final String PYTHON_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyLTkiLCJ1c2VybmFtZSI6ImJzLmFuIiwicm9sZSI6ImRvY3RvciIsInR5cGUiOiJhY2Nlc3MiLCJpYXQiOjE3OTQyMzcwODAsImV4cCI6NDk0NzgzNzA4MH0.vqR2ZlXy0VsDTdpldPOwiUqZMx-A68jtKigejiC-H4Q";

    @Autowired
    MockMvc mvc;
    @Autowired
    ObjectMapper json;
    @MockitoBean
    StringRedisTemplate redis;
    @MockitoBean
    ConversationEvents events;
    @MockitoBean
    AiClient ai;
    @MockitoBean
    IdentityClient identity;
    @MockitoBean
    AttachmentStore store;
    @MockitoBean
    PubSubStreams inbox;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUpFakes() {
        reset(ai, events, identity, store, inbox);
        when(identity.getUser(anyString())).thenAnswer(i -> Optional.of(new IdentityClient.UserRef(i.getArgument(0), "BS. " + i.getArgument(0), "doctor")));
        when(identity.getProfiles(any())).thenAnswer(i -> {
            Map<String, IdentityClient.ProfileDetail> out = new java.util.HashMap<>();
            // hồ sơ `pp-<user>` thuộc tài khoản `<user>` (khớp resolveProfile bên dưới)
            ((java.util.Collection<String>) i.getArgument(0)).forEach(id -> out.put(id, new IdentityClient.ProfileDetail(id, id.startsWith("pp-") ? id.substring(3) : "u", "Bệnh nhân " + id, "1990-01-01", "male", "self", null)));
            return out;
        });
        when(store.presignedUrl(anyString())).thenAnswer(i -> "http://minio/" + i.getArgument(0));
        when(identity.resolveProfile(anyString(), any())).thenAnswer(i -> Optional.of(
                new IdentityClient.ProfileRef(i.getArgument(1) == null ? "pp-" + i.getArgument(0) : i.getArgument(1), i.getArgument(0), "Bệnh nhân")));
    }

    String token(String userId) throws Exception {
        return token(userId, "patient");
    }

    String token(String userId, String role) throws Exception {
        JWTClaimsSet claims = new JWTClaimsSet.Builder().subject(userId).claim("role", role).claim("type", "access")
                .expirationTime(Date.from(Instant.now().plusSeconds(600))).build();
        SignedJWT jwt = new SignedJWT(new JWSHeader(JWSAlgorithm.HS256), claims);
        jwt.sign(new MACSigner(SECRET.getBytes(StandardCharsets.UTF_8)));
        return jwt.serialize();
    }

    ResultActions call(MockHttpServletRequestBuilder request, String bearer, Object body) throws Exception {
        if (bearer != null) {
            request.header("Authorization", "Bearer " + bearer);
        }
        if (body != null) {
            request.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body));
        }
        return mvc.perform(request);
    }

    ResultActions internal(MockHttpServletRequestBuilder request, Object body) throws Exception {
        request.header("X-Internal-Key", INTERNAL_KEY);
        if (body != null) {
            request.contentType(MediaType.APPLICATION_JSON).content(json.writeValueAsString(body));
        }
        return mvc.perform(request);
    }

    JsonNode data(ResultActions result) throws Exception {
        return json.readTree(result.andReturn().getResponse().getContentAsString()).get("data");
    }

    /** Tạo hội thoại có lượt đầu; trả (conversationId, id tin AI đang chờ). */
    String[] createConversation(String user, String content) throws Exception {
        reset(ai);
        String conversationId = data(call(post("/api/v1/conversations"), token(user), Map.of("content", content)).andExpect(status().isCreated())).get("id").asText();
        ArgumentCaptor<AiClient.TurnRequest> sent = ArgumentCaptor.forClass(AiClient.TurnRequest.class);
        verify(ai).startTurn(sent.capture());
        return new String[] {conversationId, sent.getValue().messageId()};
    }

    void finishTurn(String assistantId) throws Exception {
        internal(post("/internal/turns/" + assistantId + "/result"), Map.of("status", "done", "content", "Đây là câu trả lời.", "reasoning", List.of(Map.of("tool", "x"))))
                .andExpect(status().isOk());
    }

    @Test
    void readsAccessTokenIssuedByPython() throws Exception {
        call(get("/api/v1/conversations"), PYTHON_TOKEN, null).andExpect(status().isOk()).andExpect(jsonPath("$.data").isArray());
    }

    @Test
    void createConversationStartsFirstTurnOnAiWithOnlyIds() throws Exception {
        String[] ids = createConversation("u-create", "Da tôi bị ngứa");
        ArgumentCaptor<AiClient.TurnRequest> sent = ArgumentCaptor.forClass(AiClient.TurnRequest.class);
        verify(ai).startTurn(sent.capture());
        AiClient.TurnRequest request = sent.getValue();
        assertEquals(List.of("turn", ids[0], "Da tôi bị ngứa"), List.of(request.type(), request.conversationId(), request.content()));
        assertTrue(request.userMessageId() != null && request.messageId() != null);

        JsonNode messages = data(call(get("/api/v1/conversations/" + ids[0] + "/messages"), token("u-create"), null).andExpect(status().isOk()));
        assertEquals(2, messages.size());
        assertEquals("patient", messages.get(0).get("sender").asText());
        assertEquals("queued", messages.get(1).get("status").asText());
        call(get("/api/v1/conversations"), token("u-create"), null).andExpect(jsonPath("$.data[0].patient_profile_id").value("pp-u-create"))
                .andExpect(jsonPath("$.data[0].model").value("gemma4-26b"));
    }

    @Test
    void validatesModelAndProfile() throws Exception {
        call(post("/api/v1/conversations"), token("u-val"), Map.of("content", "x", "model", "khong-co")).andExpect(status().isUnprocessableEntity());
        when(identity.resolveProfile(anyString(), any())).thenReturn(Optional.empty());
        call(post("/api/v1/conversations"), token("u-val"), Map.of("content", "x")).andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("Không tìm thấy hồ sơ bệnh nhân của tài khoản."));
        call(get("/api/v1/conversations"), null, null).andExpect(status().isUnauthorized());
        call(get("/api/v1/models"), null, null).andExpect(status().isOk()).andExpect(jsonPath("$.data[2].id").value("gemma4-26b"));
    }

    @Test
    void sendMessageIsRejectedWhileTurnIsActiveThenAcceptedAfterResult() throws Exception {
        String[] ids = createConversation("u-send", "Xin chào");
        String body = "{\"client_message_id\":\"c1\",\"content\":\"hỏi thêm\"}";
        mvc.perform(post("/api/v1/conversations/" + ids[0] + "/messages").header("Authorization", "Bearer " + token("u-send")).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isConflict());

        finishTurn(ids[1]);
        reset(ai);
        ResultActions accepted = mvc.perform(post("/api/v1/conversations/" + ids[0] + "/messages").header("Authorization", "Bearer " + token("u-send")).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isAccepted()).andExpect(jsonPath("$.data.assistant_message.status").value("queued"));
        String corr = data(accepted).get("user_message").get("id").asText();
        ArgumentCaptor<AiClient.TurnRequest> sent = ArgumentCaptor.forClass(AiClient.TurnRequest.class);
        verify(ai).startTurn(sent.capture());
        assertEquals(List.of("hỏi thêm", "c1", corr), List.of(sent.getValue().content(), sent.getValue().corrId(), sent.getValue().userMessageId()));
        call(post("/api/v1/conversations/" + ids[0] + "/messages"), token("u-send"), Map.of("client_message_id", "c2", "content", "x", "attached_files", List.of(Map.of("storage_key", "k"))))
                .andExpect(status().isBadRequest());
    }

    @Test
    void turnResultReplacesContentStatusAndMetadata() throws Exception {
        String[] ids = createConversation("u-result", "Xin chào");
        finishTurn(ids[1]);
        JsonNode assistant = data(call(get("/api/v1/conversations/" + ids[0] + "/messages"), token("u-result"), null)).get(1);
        assertEquals("done", assistant.get("status").asText());
        assertEquals("Đây là câu trả lời.", assistant.get("content").asText());
        assertEquals("x", assistant.get("metadata").get("reasoning").get(0).get("tool").asText());
        assertEquals("text", assistant.get("metadata").get("message_type").asText());
        internal(post("/internal/turns/khong-co/result"), Map.of("status", "done")).andExpect(status().isNotFound());
        mvc.perform(post("/internal/turns/" + ids[1] + "/result").contentType(MediaType.APPLICATION_JSON).content("{\"status\":\"done\"}")).andExpect(status().isForbidden());
    }

    @Test
    void askUserQuestionBlocksNewMessagesAndAnswerResumesTheSameTurn() throws Exception {
        String[] ids = createConversation("u-ask", "Xin chào");
        internal(post("/internal/turns/" + ids[1] + "/result"), Map.of("status", "question", "content", "",
                "choice", Map.of("question_id", "q1", "question", "Ngứa mấy ngày?", "options", List.of(Map.of("id", "opt-0", "label", "1 ngày"))))).andExpect(status().isOk());
        call(post("/api/v1/conversations/" + ids[0] + "/messages"), token("u-ask"), Map.of("client_message_id", "c", "content", "x")).andExpect(status().isConflict());
        call(post("/api/v1/conversations/" + ids[0] + "/questions/sai/answer"), token("u-ask"), Map.of("option_id", "opt-0", "label", "1 ngày")).andExpect(status().isNotFound());

        reset(ai);
        call(post("/api/v1/conversations/" + ids[0] + "/questions/q1/answer"), token("u-ask"), Map.of("option_id", "opt-0", "label", "1 ngày"))
                .andExpect(status().isAccepted()).andExpect(jsonPath("$.data.id").value(ids[1]));
        ArgumentCaptor<AiClient.TurnRequest> sent = ArgumentCaptor.forClass(AiClient.TurnRequest.class);
        verify(ai).startTurn(sent.capture());
        assertEquals(List.of("resume", ids[1], "1 ngày"), List.of(sent.getValue().type(), sent.getValue().messageId(), sent.getValue().answer()));
    }

    @Test
    void cancelClosesTheMessageOnlyWhenAiDoesNotHoldTheTurn() throws Exception {
        String[] ids = createConversation("u-cancel", "Xin chào");
        when(ai.cancelTurn(ids[1])).thenReturn(true);
        call(post("/api/v1/conversations/" + ids[0] + "/cancel"), token("u-cancel"), null).andExpect(status().isAccepted());
        verify(events, never()).publish(eq(ids[0]), eq(Map.of("type", "message.done", "conversation_id", ids[0], "message_id", ids[1], "content", "")));
        assertEquals("queued", data(call(get("/api/v1/conversations/" + ids[0] + "/messages"), token("u-cancel"), null)).get(1).get("status").asText());

        when(ai.cancelTurn(ids[1])).thenReturn(false);
        call(post("/api/v1/conversations/" + ids[0] + "/cancel"), token("u-cancel"), null).andExpect(status().isAccepted());
        assertEquals("done", data(call(get("/api/v1/conversations/" + ids[0] + "/messages"), token("u-cancel"), null)).get(1).get("status").asText());
        verify(events).publish(eq(ids[0]), eq(Map.of("type", "message.done", "conversation_id", ids[0], "message_id", ids[1], "content", "")));
    }

    @Test
    void aiFailureClosesTheAssistantMessageWithAnErrorText() throws Exception {
        doThrow(new IllegalStateException("ai chết")).when(ai).startTurn(any());
        String conversationId = data(call(post("/api/v1/conversations"), token("u-fail"), Map.of("content", "Xin chào")).andExpect(status().isCreated())).get("id").asText();
        JsonNode assistant = data(call(get("/api/v1/conversations/" + conversationId + "/messages"), token("u-fail"), null)).get(1);
        assertEquals("done", assistant.get("status").asText());
        assertTrue(assistant.get("content").asText().startsWith("Xin lỗi, hệ thống gặp sự cố"));
    }

    @Test
    void conversationsAreOnlyVisibleToTheirOwner() throws Exception {
        String[] ids = createConversation("u-owner", "Xin chào");
        call(get("/api/v1/conversations/" + ids[0] + "/messages"), token("u-other"), null).andExpect(status().isForbidden());
        call(patch("/api/v1/conversations/" + ids[0] + "/model"), token("u-other"), Map.of("model", "gemma4-26b")).andExpect(status().isNotFound());
        call(get("/api/v1/conversations"), token("u-other"), null).andExpect(jsonPath("$.data.length()").value(0));
        call(patch("/api/v1/conversations/" + ids[0] + "/model"), token("u-owner"), Map.of("model", "deepseek-v4-pro")).andExpect(jsonPath("$.data.model").value("deepseek-v4-pro"));
    }

    @Test
    void internalEndpointsServeAiAndIdentity() throws Exception {
        String[] ids = createConversation("u-int", "Da tôi ngứa");
        finishTurn(ids[1]);
        data(internal(get("/internal/conversations/" + ids[0]), null)).get("user_id").asText().equals("u-int");
        assertEquals("pp-u-int", data(internal(get("/internal/conversations/" + ids[0]), null)).get("patient_profile_id").asText());
        JsonNode history = data(internal(get("/internal/conversations/" + ids[0] + "/history"), null));
        assertEquals(List.of("patient", "Da tôi ngứa", "text"), List.of(history.get(0).get("sender").asText(), history.get(0).get("content").asText(), history.get(0).get("message_type").asText()));
        assertEquals("ai", history.get(1).get("sender").asText());
        assertTrue(data(internal(get("/internal/patients/pp-u-int/has-data"), null)).get("has_data").asBoolean());
        assertEquals(false, data(internal(get("/internal/patients/pp-khac/has-data"), null)).get("has_data").asBoolean());
        internal(get("/internal/conversations/khong-co"), null).andExpect(status().isNotFound());
    }

    @Test
    void uploadAcceptsOnlySmallImagesAndReturnsFileDtoWithoutEnvelope() throws Exception {
        String bearer = token("u-up");
        ResultActions ok = mvc.perform(multipart("/api/v1/uploads").file(new MockMultipartFile("file", "da-tay.png", "image/png", new byte[] {1, 2, 3})).header("Authorization", "Bearer " + bearer))
                .andExpect(status().isOk()).andExpect(jsonPath("$.file_name").value("da-tay.png")).andExpect(jsonPath("$.content_type").value("image/png"))
                .andExpect(jsonPath("$.size").value(3)).andExpect(jsonPath("$.storage_key").value(org.hamcrest.Matchers.endsWith(".png")));
        String key = json.readTree(ok.andReturn().getResponse().getContentAsString()).get("storage_key").asText();
        verify(store).put(eq(key), eq(new byte[] {1, 2, 3}), eq("image/png"));
        assertEquals("http://minio/" + key, json.readTree(ok.andReturn().getResponse().getContentAsString()).get("url").asText());
        mvc.perform(multipart("/api/v1/uploads").file(new MockMultipartFile("file", "a.pdf", "application/pdf", new byte[] {1})).header("Authorization", "Bearer " + bearer))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.detail").value("Định dạng không hỗ trợ: application/pdf"));
        mvc.perform(multipart("/api/v1/uploads").file(new MockMultipartFile("file", "a.png", "image/png", new byte[10 * 1024 * 1024 + 1])).header("Authorization", "Bearer " + bearer))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.detail").value("File vượt quá 10MB."));
        mvc.perform(multipart("/api/v1/uploads").file(new MockMultipartFile("file", "a.png", "image/png", new byte[] {1}))).andExpect(status().isUnauthorized());
    }

    @Test
    void messageWithImageIsLinkedToTheFileAndForwardedToAi() throws Exception {
        String bearer = token("u-img");
        String[] ids = createConversation("u-img", "Xin chào");
        finishTurn(ids[1]);
        String key = json.readTree(mvc.perform(multipart("/api/v1/uploads").file(new MockMultipartFile("file", "ton-thuong.jpg", "image/jpeg", new byte[] {9}))
                .header("Authorization", "Bearer " + bearer)).andReturn().getResponse().getContentAsString()).get("storage_key").asText();

        reset(ai);
        ResultActions sent = call(post("/api/v1/conversations/" + ids[0] + "/messages"), bearer,
                Map.of("client_message_id", "c1", "content", "ảnh vùng da", "attached_files", List.of(Map.of("storage_key", key))))
                .andExpect(status().isAccepted()).andExpect(jsonPath("$.data.user_message.metadata.message_type").value("attached"))
                .andExpect(jsonPath("$.data.user_message.metadata.attached_files[0].file_name").value("ton-thuong.jpg"))
                .andExpect(jsonPath("$.data.user_message.metadata.attached_files[0].url").value("http://minio/" + key));
        assertTrue(data(sent).get("assistant_message") != null);
        ArgumentCaptor<AiClient.TurnRequest> turn = ArgumentCaptor.forClass(AiClient.TurnRequest.class);
        verify(ai).startTurn(turn.capture());
        assertEquals(List.of(new AiClient.AttachmentRef("ton-thuong.jpg", "image/jpeg", key)), turn.getValue().attachedFiles());

        JsonNode listed = data(call(get("/api/v1/conversations/" + ids[0] + "/messages"), bearer, null));
        assertEquals(key, listed.get(2).get("metadata").get("attached_files").get(0).get("storage_key").asText());
        assertTrue(listed.get(0).get("metadata").get("attached_files") == null);

        finishTurn(turn.getValue().messageId());
        call(post("/api/v1/conversations/" + ids[0] + "/messages"), bearer,
                Map.of("client_message_id", "c2", "content", "x", "attached_files", List.of(Map.of("storage_key", "chua-upload.png"))))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.detail").value("Tệp đính kèm chưa được tải lên: chua-upload.png"));
    }

    /** clinical mở kênh theo dõi của một lần khám; trả conversationId. Hồ sơ `pp-<user>` map về tài khoản `<user>` (xem setUpFakes). */
    String openChannel(String encounterId, String patient, String doctor) throws Exception {
        return data(internal(post("/internal/encounters/" + encounterId + "/followup-channel"), Map.of("patient_profile_id", "pp-" + patient, "doctor_id", doctor))
                .andExpect(status().isOk())).get("conversation_id").asText();
    }

    void setUntil(String encounterId, Instant until) throws Exception {
        internal(put("/internal/encounters/" + encounterId + "/followup-channel/until"), Map.of("followup_until", until.toString())).andExpect(status().isOk());
    }

    @Test
    void followupChannelIsCreatedIdempotentlyAndIsNotAnAiConversation() throws Exception {
        String channel = openChannel("enc-1", "u-fu1", "d-1");
        assertEquals(channel, openChannel("enc-1", "u-fu1", "d-1"));
        internal(post("/internal/encounters/enc-x/followup-channel"), Map.of("patient_profile_id", "", "doctor_id", "d-1")).andExpect(status().isUnprocessableEntity());

        call(get("/api/v1/conversations"), token("u-fu1"), null).andExpect(jsonPath("$.data.length()").value(0));
        call(get("/api/v1/followup-channels/by-encounter/enc-1"), token("u-fu1"), null).andExpect(status().isOk())
                .andExpect(jsonPath("$.data.conversation_id").value(channel)).andExpect(jsonPath("$.data.status").value("open"))
                .andExpect(jsonPath("$.data.doctor_name").value("BS. d-1")).andExpect(jsonPath("$.data.followup_until").doesNotExist());
        call(get("/api/v1/followup-channels/by-encounter/enc-1"), token("d-1", "doctor"), null).andExpect(status().isOk());
        call(get("/api/v1/followup-channels/by-encounter/enc-1"), token("u-ngoai"), null).andExpect(status().isForbidden());
        call(get("/api/v1/followup-channels/by-encounter/enc-khong-co"), token("u-fu1"), null).andExpect(status().isNotFound());
    }

    @Test
    void patientAndDoctorChatInTheChannelWithoutAiAndStrangersAreRejected() throws Exception {
        String channel = openChannel("enc-2", "u-fu2", "d-1");
        String patient = token("u-fu2"), doctor = token("d-1", "doctor");
        call(post("/api/v1/conversations/" + channel + "/messages"), patient, Map.of("client_message_id", "c1", "content", "Thuốc bôi bị rát")).andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.user_message.sender").value("patient")).andExpect(jsonPath("$.data.assistant_message").doesNotExist());
        call(post("/api/v1/conversations/" + channel + "/messages"), doctor, Map.of("client_message_id", "c2", "content", "Ngưng thuốc 2 ngày")).andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.user_message.sender").value("doctor"));
        verify(ai, never()).startTurn(any());

        JsonNode messages = data(call(get("/api/v1/conversations/" + channel + "/messages"), doctor, null));
        assertEquals(List.of("patient", "doctor"), List.of(messages.get(0).get("sender").asText(), messages.get(1).get("sender").asText()));
        call(get("/api/v1/conversations/" + channel + "/messages"), token("d-2", "doctor"), null).andExpect(status().isForbidden());
        call(get("/api/v1/conversations/" + channel + "/stream"), token("u-ngoai"), null).andExpect(status().isForbidden());
        call(post("/api/v1/conversations/" + channel + "/messages"), token("d-2", "doctor"), Map.of("client_message_id", "c3", "content", "x")).andExpect(status().isNotFound());

        // bác sĩ không xem được hội thoại AI của bệnh nhân
        String[] ai = createConversation("u-fu2", "Xin chào");
        call(get("/api/v1/conversations/" + ai[0] + "/messages"), doctor, null).andExpect(status().isForbidden());
        call(post("/api/v1/conversations/" + ai[0] + "/messages"), doctor, Map.of("client_message_id", "c4", "content", "x")).andExpect(status().isNotFound());
    }

    @Test
    void channelBecomesReadOnlyAfterFollowupUntilAndDoctorCanOnlyExtendWhileOpen() throws Exception {
        String channel = openChannel("enc-3", "u-fu3", "d-1");
        String patient = token("u-fu3"), doctor = token("d-1", "doctor");
        call(post("/api/v1/doctor/followup-channels/" + channel + "/extend"), doctor, null).andExpect(status().isConflict());

        Instant until = Instant.now().plusSeconds(3600);
        setUntil("enc-3", until);
        call(post("/api/v1/doctor/followup-channels/" + channel + "/extend"), patient, null).andExpect(status().isForbidden());
        call(post("/api/v1/doctor/followup-channels/" + channel + "/extend"), doctor, Map.of("days", 100)).andExpect(status().isUnprocessableEntity());
        String extended = data(call(post("/api/v1/doctor/followup-channels/" + channel + "/extend"), doctor, Map.of("days", 10)).andExpect(status().isOk())).get("followup_until").asText();
        assertEquals(until.plusSeconds(10 * 86400).toEpochMilli(), Instant.parse(extended).toEpochMilli());

        setUntil("enc-3", Instant.now().minusSeconds(60));
        call(get("/api/v1/followup-channels/by-encounter/enc-3"), patient, null).andExpect(jsonPath("$.data.status").value("read_only"));
        call(post("/api/v1/conversations/" + channel + "/messages"), patient, Map.of("client_message_id", "c", "content", "x")).andExpect(status().isConflict());
        call(post("/api/v1/conversations/" + channel + "/messages"), doctor, Map.of("client_message_id", "c", "content", "x")).andExpect(status().isConflict());
        call(get("/api/v1/conversations/" + channel + "/messages"), patient, null).andExpect(status().isOk());
        call(post("/api/v1/doctor/followup-channels/" + channel + "/extend"), doctor, null).andExpect(status().isConflict());
        call(post("/api/v1/conversations/" + channel + "/video-calls"), doctor, null).andExpect(status().isConflict());
    }

    @Test
    void doctorListsOnlyTheirOwnChannelsWithPatientAndLastMessage() throws Exception {
        String mine = openChannel("enc-4", "u-fu4", "d-list");
        openChannel("enc-5", "u-fu5", "d-khac");
        call(post("/api/v1/conversations/" + mine + "/messages"), token("u-fu4"), Map.of("client_message_id", "c", "content", "Em đã đỡ ngứa")).andExpect(status().isAccepted());
        call(get("/api/v1/doctor/followup-channels"), token("u-fu4"), null).andExpect(status().isForbidden());
        call(get("/api/v1/doctor/followup-channels"), token("d-list", "doctor"), null).andExpect(status().isOk()).andExpect(jsonPath("$.data.length()").value(1))
                .andExpect(jsonPath("$.data[0].conversation_id").value(mine)).andExpect(jsonPath("$.data[0].patient_name").value("Bệnh nhân pp-u-fu4"))
                .andExpect(jsonPath("$.data[0].preview").value("Em đã đỡ ngứa"));
    }

    @Test
    void videoCallLifecycleNotifiesBothUsersAndPostsLinesInTheChat() throws Exception {
        String channel = openChannel("enc-6", "u-call", "d-1");
        String doctor = token("d-1", "doctor"), patient = token("u-call");
        call(post("/api/v1/conversations/" + channel + "/video-calls"), patient, null).andExpect(status().isForbidden());
        call(post("/api/v1/conversations/" + channel + "/video-calls"), token("d-2", "doctor"), null).andExpect(status().isForbidden());

        String callId = data(call(post("/api/v1/conversations/" + channel + "/video-calls"), doctor, Map.of("mode", "video")).andExpect(status().isCreated())
                .andExpect(jsonPath("$.data.status").value("pending")).andExpect(jsonPath("$.data.doctor_id").value("d-1"))).get("id").asText();
        verify(inbox).publish(eq("user:calls:d-1"), any());
        verify(inbox).publish(eq("user:calls:u-call"), any());
        call(post("/api/v1/conversations/" + channel + "/video-calls"), doctor, null).andExpect(status().isConflict());
        call(post("/api/v1/video-calls/" + callId + "/signal"), doctor, Map.of("kind", "offer", "payload", Map.of("sdp", "x"))).andExpect(status().isConflict());
        call(post("/api/v1/video-calls/" + callId + "/accept"), doctor, null).andExpect(status().isForbidden());
        call(post("/api/v1/video-calls/" + callId + "/accept"), token("u-ngoai"), null).andExpect(status().isForbidden());

        call(post("/api/v1/video-calls/" + callId + "/accept"), patient, null).andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("ongoing"));
        call(post("/api/v1/video-calls/" + callId + "/accept"), patient, null).andExpect(status().isConflict());
        reset(inbox);
        call(post("/api/v1/video-calls/" + callId + "/signal"), doctor, Map.of("kind", "offer", "payload", Map.of("sdp", "x"))).andExpect(status().isNoContent());
        verify(inbox).publish(eq("user:calls:u-call"), any());
        verify(inbox, never()).publish(eq("user:calls:d-1"), any());
        call(post("/api/v1/video-calls/" + callId + "/signal"), doctor, Map.of("kind", "khong-hop-le", "payload", Map.of())).andExpect(status().isUnprocessableEntity());

        call(post("/api/v1/video-calls/" + callId + "/end"), patient, null).andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("ended"));
        call(post("/api/v1/video-calls/" + callId + "/end"), doctor, null).andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("ended"));

        JsonNode messages = data(call(get("/api/v1/conversations/" + channel + "/messages"), patient, null));
        JsonNode first = messages.get(messages.size() - 2), last = messages.get(messages.size() - 1);
        assertEquals(List.of("video_call", "doctor", "Cuộc gọi bắt đầu"), List.of(first.get("metadata").get("message_type").asText(), first.get("sender").asText(), first.get("content").asText()));
        assertTrue(last.get("content").asText().startsWith("Cuộc gọi kết thúc · 00:0"));
        assertEquals("ended", last.get("metadata").get("video_call").get("status").asText());
        // cuộc gọi mới được khi cuộc trước đã kết thúc
        call(post("/api/v1/conversations/" + channel + "/video-calls"), doctor, null).andExpect(status().isCreated());
    }

    @Test
    void videoCallRejectedByPatientOrMissedAndAiConversationCannotBeCalled() throws Exception {
        String[] aiChat = createConversation("u-nocall", "Xin chào");
        call(post("/api/v1/conversations/" + aiChat[0] + "/video-calls"), token("d-1", "doctor"), null).andExpect(status().isNotFound());

        String channel = openChannel("enc-7", "u-reject", "d-1");
        String callId = data(call(post("/api/v1/conversations/" + channel + "/video-calls"), token("d-1", "doctor"), null).andExpect(status().isCreated())).get("id").asText();
        call(post("/api/v1/video-calls/" + callId + "/end"), token("u-reject"), null).andExpect(status().isOk());
        JsonNode messages = data(call(get("/api/v1/conversations/" + channel + "/messages"), token("u-reject"), null));
        assertEquals("Bệnh nhân đã từ chối cuộc gọi", messages.get(messages.size() - 1).get("content").asText());

        String missed = data(call(post("/api/v1/conversations/" + channel + "/video-calls"), token("d-1", "doctor"), null).andExpect(status().isCreated())).get("id").asText();
        call(post("/api/v1/video-calls/" + missed + "/end"), token("d-1", "doctor"), Map.of("reason", "missed")).andExpect(status().isOk());
        JsonNode after = data(call(get("/api/v1/conversations/" + channel + "/messages"), token("u-reject"), null));
        assertEquals("Cuộc gọi nhỡ", after.get(after.size() - 1).get("content").asText());
    }

    @Autowired
    vn.derma.consultation.service.MessageService messageService;

    @Test
    void staleQueuedAiTurnsAreClosedWithAnErrorTextSoTheUserCanSendAgain() throws Exception {
        String[] ids = createConversation("u-stale", "Xin chào");
        assertEquals(0, messageService.closeStaleTurns(Instant.now().minusSeconds(3600)));
        assertTrue(messageService.closeStaleTurns(Instant.now().plusSeconds(60)) >= 1);
        JsonNode assistant = data(call(get("/api/v1/conversations/" + ids[0] + "/messages"), token("u-stale"), null)).get(1);
        assertEquals("done", assistant.get("status").asText());
        assertTrue(assistant.get("content").asText().startsWith("Xin lỗi, hệ thống gặp sự cố"));
        verify(events).publish(eq(ids[0]), eq(Map.of("type", "message.done", "conversation_id", ids[0], "message_id", ids[1], "content", assistant.get("content").asText())));
        call(post("/api/v1/conversations/" + ids[0] + "/messages"), token("u-stale"), Map.of("client_message_id", "c", "content", "x")).andExpect(status().isAccepted());
    }

    @Test
    void iceConfigHasStunAndTurnOnlyWhenConfigured() throws Exception {
        call(get("/api/v1/video-calls/ice-config"), token("u-ice"), null).andExpect(status().isOk()).andExpect(jsonPath("$.data.ice_servers.length()").value(1))
                .andExpect(jsonPath("$.data.ice_servers[0].urls[0]").value("stun:stun.l.google.com:19302"));
        call(get("/api/v1/video-calls/ice-config"), null, null).andExpect(status().isUnauthorized());
    }
}
