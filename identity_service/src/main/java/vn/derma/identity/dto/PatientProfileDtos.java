package vn.derma.identity.dto;

import java.time.LocalDate;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public final class PatientProfileDtos {

    private PatientProfileDtos() {
    }

    /** Fact dài hạn bệnh nhân tự khai; lưu ở clinical. */
    public record ProfileFactInput(
            @NotNull @Pattern(regexp = "allergy|history|medication") String factType,
            @NotBlank @Size(max = 255) String label,
            @Size(max = 300) String detail) {
    }

    public record ProfileFactOutput(String id, String factType, String label, String detail, String verifiedAt) {
    }

    public record CreatePatientProfileInput(
            @NotBlank @Size(max = 255) String fullName,
            @NotNull LocalDate dob,
            @NotNull Gender gender,
            ProfileRelationship relationship,
            @Size(max = 32) String phone,
            @Valid List<ProfileFactInput> longTermFacts) {
    }

    /**
     * PATCH: trường null là không đổi. `phone` có thể gửi null để xoá số nên cần biết có được gửi hay không;
     * Jackson chỉ gọi setter khi JSON có khoá `phone`, record/Optional không phân biệt được.
     */
    public static class UpdatePatientProfileInput {

        @Size(min = 1, max = 255)
        public String fullName;
        public LocalDate dob;
        public Gender gender;
        public ProfileRelationship relationship;
        @Valid
        public List<ProfileFactInput> longTermFacts;
        private String phone;
        private boolean phoneProvided;

        public void setPhone(String phone) {
            this.phone = phone;
            this.phoneProvided = true;
        }

        public String phone() {
            return phone;
        }

        public boolean phoneProvided() {
            return phoneProvided;
        }
    }

    public record PatientProfileOutput(
            String id,
            String fullName,
            String dob,
            String gender,
            String relationship,
            String phone,
            List<ProfileFactOutput> longTermFacts,
            String createdAt) {
    }
}
