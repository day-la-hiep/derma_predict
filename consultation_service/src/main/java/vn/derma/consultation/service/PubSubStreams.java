package vn.derma.consultation.service;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import jakarta.annotation.PreDestroy;
import tools.jackson.databind.ObjectMapper;

/**
 * SSE dài hạn trên Redis Pub/Sub cho thứ chỉ cần tức thời, mất cũng không sao vì người dùng tải lại qua REST:
 * hộp thư ca của bác sĩ (`doctor:inbox`) và sự kiện cuộc gọi của từng tài khoản (`user:calls:{id}`).
 * Container Pub/Sub chỉ tạo khi có người đầu tiên mở SSE.
 */
@Component
@Slf4j
@AllArgsConstructor
public class PubSubStreams {

    public static final String DOCTOR_INBOX = "doctor:inbox";

    public static String userCallsChannel(String userId) {
        return "user:calls:" + userId;
    }


    private final StringRedisTemplate redis;
    private final RedisConnectionFactory connectionFactory;
    private final ObjectMapper json;
    private RedisMessageListenerContainer container;

    public void publish(String channel, Object event) {
        redis.convertAndSend(channel, json.writeValueAsString(event));
    }

    public synchronized SseEmitter subscribe(String channel) {
        if (container == null) {
            container = new RedisMessageListenerContainer();
            container.setConnectionFactory(connectionFactory);
            container.afterPropertiesSet();
            container.start();
        }
        SseEmitter emitter = new SseEmitter(0L);
        MessageListener[] self = new MessageListener[1];
        MessageListener listener = (message, pattern) -> {
            try {
                emitter.send(SseEmitter.event().data(new String(message.getBody(), StandardCharsets.UTF_8)));
            } catch (IOException | IllegalStateException e) {
                log.debug("SSE {} đã đóng: {}", channel, e.toString());
                unsubscribe(self[0], channel);
            }
        };
        self[0] = listener;
        ChannelTopic topic = new ChannelTopic(channel);
        container.addMessageListener(listener, topic);
        Runnable cleanup = () -> unsubscribe(listener, channel);
        emitter.onCompletion(cleanup);
        emitter.onTimeout(cleanup);
        emitter.onError(e -> cleanup.run());
        return emitter;
    }

    private synchronized void unsubscribe(MessageListener listener, String channel) {
        if (container != null) {
            container.removeMessageListener(listener, new ChannelTopic(channel));
        }
    }

    @PreDestroy
    void stop() {
        if (container != null) {
            try {
                container.destroy();
            } catch (Exception e) {
                log.warn("Không đóng được container Pub/Sub", e);
            }
        }
    }
}
