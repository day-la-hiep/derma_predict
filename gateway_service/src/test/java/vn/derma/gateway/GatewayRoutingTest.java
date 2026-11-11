package vn.derma.gateway;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webtestclient.autoconfigure.AutoConfigureWebTestClient;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

import com.sun.net.httpserver.HttpServer;

/** Mỗi service giả trả về tên của nó; kiểm đường dẫn nào rơi vào service nào, đặc biệt các route con của /doctor và /patient-profiles. */
@AutoConfigureWebTestClient
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewayRoutingTest {

    private static final Map<String, HttpServer> BACKENDS = new java.util.LinkedHashMap<>();

    static {
        for (String name : List.of("identity", "consultation", "clinical", "knowledge")) {
            try {
                HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
                server.createContext("/", exchange -> {
                    byte[] body = name.getBytes(StandardCharsets.UTF_8);
                    exchange.sendResponseHeaders(200, body.length);
                    exchange.getResponseBody().write(body);
                    exchange.close();
                });
                server.start();
                BACKENDS.put(name, server);
            } catch (IOException e) {
                throw new IllegalStateException(e);
            }
        }
    }

    @DynamicPropertySource
    static void backends(DynamicPropertyRegistry registry) {
        BACKENDS.forEach((name, server) -> registry.add(name.toUpperCase() + "_URL", () -> "http://127.0.0.1:" + server.getAddress().getPort()));
    }

    @AfterAll
    static void stop() {
        BACKENDS.values().forEach(s -> s.stop(0));
    }

    @Autowired
    WebTestClient client;

    void expect(String path, String service) {
        String body = client.get().uri(path).exchange().expectStatus().isOk().expectBody(String.class).returnResult().getResponseBody();
        assertEquals(service, body, path);
    }

    @Test
    void routesEachPrefixToItsService() {
        expect("/api/v1/auth/login", "identity");
        expect("/api/v1/patient-profiles", "identity");
        expect("/api/v1/patient-profiles/p1", "identity");
        expect("/api/v1/patient-profiles/p1/episodes", "clinical");
        expect("/api/v1/patient-profiles/p1/finalize-reports", "clinical");
        expect("/api/v1/conversations/c1/messages", "consultation");
        expect("/api/v1/uploads", "consultation");
        expect("/api/v1/models", "consultation");
        expect("/api/v1/video-calls/ice-config", "consultation");
        expect("/api/v1/followup-channels/by-encounter/e1", "consultation");
        expect("/api/v1/doctor/followup-channels", "consultation");
        expect("/api/v1/conversations/c1/video-calls", "consultation");
        expect("/api/v1/appointments/a1/cancel", "clinical");
        expect("/api/v1/doctor/appointments/a1/start", "clinical");
        expect("/api/v1/doctor/encounters/e1/finalize-draft", "clinical");
        expect("/api/v1/doctor/finalize-reports", "clinical");
        expect("/api/v1/doctor/patient-profiles/p1/journey-graph", "clinical");
        expect("/api/v1/admin/documents/documents", "knowledge");
        expect("/api/v1/admin/graph-schema/relations", "knowledge");
        expect("/api/v1/citations/documents/d1/source-url", "knowledge");
        expect("/api/v1/citations/documents/d1/passages", "knowledge");
    }

    @Test
    void unknownPathIsNotFound() {
        client.get().uri("/api/v1/khong-co").exchange().expectStatus().isNotFound();
    }
}
