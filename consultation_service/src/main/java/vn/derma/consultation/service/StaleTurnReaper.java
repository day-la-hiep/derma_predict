package vn.derma.consultation.service;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import java.time.Duration;
import java.time.Instant;

import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import vn.derma.consultation.config.DermaProperties;

@Component
@Slf4j
@AllArgsConstructor
public class StaleTurnReaper {


    private final MessageService messages;
    private final DermaProperties properties;

    @Scheduled(fixedDelay = 60_000, initialDelay = 60_000)
    void closeStaleTurns() {
        int closed = messages.closeStaleTurns(Instant.now().minus(Duration.ofMinutes(properties.staleTurnMinutes())));
        if (closed > 0) {
            log.warn("Đã đóng {} lượt AI treo quá {} phút", closed, properties.staleTurnMinutes());
        }
    }
}
