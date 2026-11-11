package vn.derma.identity.common;

import java.net.http.HttpClient;

import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/** Ép HTTP/1.1: JDK mặc định thử nâng lên h2c và làm mất body POST khi gọi server Python (uvicorn). */
public final class Http11 {

    private Http11() {
    }

    public static RestClient.Builder apply(RestClient.Builder builder) {
        return builder.requestFactory(new JdkClientHttpRequestFactory(HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).build()));
    }
}
