package vn.derma.identity.dto;

import java.time.LocalDate;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** DTO của luồng xác thực, gom một file vì đều là record ngắn. */
public final class AuthDtos {

    private AuthDtos() {
    }

    public record RegisterInput(
            @NotBlank @Size(min = 3, max = 64) String username,
            @NotBlank @Size(min = 6, max = 128) String password,
            @NotBlank @Size(max = 255) String fullName,
            @NotNull LocalDate dob,
            @NotNull Gender gender) {
    }

    public record LoginInput(@NotBlank @Size(max = 64) String username, @NotBlank @Size(max = 128) String password) {
    }

    public record RefreshTokenInput(@NotBlank String refreshToken) {
    }

    /** PATCH: trường null là không đổi. */
    public record UpdateAccountInput(@Size(min = 1, max = 255) String fullName, LocalDate dob, Gender gender) {
    }

    public record UserSummaryOutput(String id, String username, String fullName, LocalDate dob, Gender gender, String role) {
    }

    public record TokenPairOutput(String accessToken, String refreshToken, String tokenType, UserSummaryOutput user) {
    }
}
