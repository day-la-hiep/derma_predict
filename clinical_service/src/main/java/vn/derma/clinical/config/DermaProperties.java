package vn.derma.clinical.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "derma")
public record DermaProperties(Jwt jwt, String internalApiKey, String consultationUrl, String knowledgeUrl, String identityUrl,
        int episodeExpireDays, Minio minio) {

    public record Jwt(String secret) {
    }

    public record Minio(String endpoint, String accessKey, String secretKey, boolean secure, String bucket) {
    }
}
