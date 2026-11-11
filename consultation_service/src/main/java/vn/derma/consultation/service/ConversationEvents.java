package vn.derma.consultation.service;

import lombok.AllArgsConstructor;
import java.time.Duration;
import java.util.Map;

import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

import tools.jackson.databind.ObjectMapper;

/** Ghi event của hội thoại vào Redis Stream `conversation:events:{id}` (cùng stream mà ai ghi); SSE đọc ra cho FE. */
@Component
@AllArgsConstructor
public class ConversationEvents {

    static final long MAX_LENGTH = 2000;
    static final Duration TTL = Duration.ofHours(1);

    private final StringRedisTemplate redis;
    private final ObjectMapper json;

    public static String streamKey(String conversationId) {
        return "conversation:events:" + conversationId;
    }

    public void publish(String conversationId, Map<String, Object> event) {
        String key = streamKey(conversationId);
        redis.opsForStream().add(StreamRecords.string(Map.of("event", json.writeValueAsString(event))).withStreamKey(key));
        redis.opsForStream().trim(key, MAX_LENGTH, true);
        redis.expire(key, TTL);
    }
}
