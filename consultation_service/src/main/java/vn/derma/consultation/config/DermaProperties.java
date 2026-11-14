package vn.derma.consultation.config;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "derma")
public record DermaProperties(Jwt jwt, String internalApiKey, String aiUrl, String identityUrl, List<String> models,
        String defaultModel, List<String> imageModels, String defaultImageModel, int streamReplaySeconds, int staleTurnMinutes, Minio minio, Webrtc webrtc) {

    public record Jwt(String secret) {
    }

    public record Webrtc(List<String> stunUrls, String turnUrl, String turnSecret, int turnCredentialTtlSeconds, String meteredHost,
            String meteredUsername, String meteredCredential) {
    }

    public record Minio(String endpoint, String accessKey, String secretKey, boolean secure, String bucket) {
    }
}
