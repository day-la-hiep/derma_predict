package vn.derma.consultation.controller;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import java.io.IOException;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import vn.derma.consultation.common.AppException;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.common.CurrentUser;
import vn.derma.consultation.config.DermaProperties;
import tools.jackson.databind.ObjectMapper;
import vn.derma.consultation.service.FollowupService;
import vn.derma.consultation.service.ConversationEvents;

/** SSE dài hạn của hội thoại: đọc Redis Stream (có replay) thay cho Pub/Sub + mẹo hoãn publish của core. */
@RestController
@RequestMapping("/api/v1")
@Slf4j
@AllArgsConstructor
public class ConversationStreamController {

    private static final Duration BLOCK = Duration.ofSeconds(5);
    private static final int HEARTBEAT_EVERY_IDLE_READS = 3;

    private final StringRedisTemplate redis;
    private final FollowupService followups;
    private final DermaProperties properties;
    private final ObjectMapper json;

    @GetMapping("/conversations/{conversationId}/stream")
    SseEmitter stream(@CurrentUser AuthenticatedUser user, @PathVariable String conversationId,
            @RequestHeader(name = "Last-Event-ID", required = false) String lastEventId) {
        followups.requireAccess(conversationId, user);
        // không có Last-Event-ID thì phát lại event trong vài chục giây gần nhất: bù đoạn từ lúc POST tin tới lúc SSE mở
        String startId = lastEventId != null && !lastEventId.isBlank()
                ? lastEventId
                : (System.currentTimeMillis() - properties.streamReplaySeconds() * 1000L) + "-0";
        SseEmitter emitter = new SseEmitter(0L);
        AtomicBoolean open = new AtomicBoolean(true);
        emitter.onCompletion(() -> open.set(false));
        emitter.onTimeout(() -> open.set(false));
        emitter.onError(e -> open.set(false));
        Thread.startVirtualThread(() -> pump(emitter, open, ConversationEvents.streamKey(conversationId), startId));
        return emitter;
    }

    private void pump(SseEmitter emitter, AtomicBoolean open, String key, String startId) {
        String lastId = startId;
        int idleReads = 0;
        try {
            while (open.get()) {
                List<MapRecord<String, Object, Object>> records = redis.opsForStream().read(
                        StreamReadOptions.empty().block(BLOCK).count(100), StreamOffset.create(key, ReadOffset.from(lastId)));
                if (records == null || records.isEmpty()) {
                    if (++idleReads % HEARTBEAT_EVERY_IDLE_READS == 0) {
                        emitter.send(SseEmitter.event().comment("ping"));
                    }
                    continue;
                }
                idleReads = 0;
                for (MapRecord<String, Object, Object> record : records) {
                    lastId = record.getId().getValue();
                    String event = String.valueOf(record.getValue().get("event"));
                    emitter.send(SseEmitter.event().id(lastId).data(event));
                }
            }
        } catch (IOException | IllegalStateException e) {
            log.debug("SSE đóng ({}): {}", key, e.toString());
        } catch (RuntimeException e) {
            log.warn("SSE lỗi khi đọc stream {}", key, e);
            emitter.completeWithError(e);
            return;
        }
        emitter.complete();
    }
}
