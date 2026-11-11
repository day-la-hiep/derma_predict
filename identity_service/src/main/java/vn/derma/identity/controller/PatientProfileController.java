package vn.derma.identity.controller;

import lombok.AllArgsConstructor;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import vn.derma.identity.common.ApiResponse;
import vn.derma.identity.common.AuthenticatedUser;
import vn.derma.identity.common.CurrentUser;
import vn.derma.identity.dto.PatientProfileDtos.CreatePatientProfileInput;
import vn.derma.identity.dto.PatientProfileDtos.PatientProfileOutput;
import vn.derma.identity.dto.PatientProfileDtos.UpdatePatientProfileInput;
import vn.derma.identity.service.PatientProfileService;

/** `/patient-profiles/{id}/finalize-reports` và `/episodes` thuộc clinical (gateway route theo đường dẫn dài hơn trước). */
@RestController
@RequestMapping("/api/v1/patient-profiles")
@AllArgsConstructor
public class PatientProfileController {

    private final PatientProfileService profiles;

    @GetMapping
    ApiResponse<List<PatientProfileOutput>> list(@CurrentUser AuthenticatedUser user) {
        return new ApiResponse<>(profiles.list(user.id()));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    ApiResponse<PatientProfileOutput> create(@CurrentUser AuthenticatedUser user, @Valid @RequestBody CreatePatientProfileInput body) {
        return new ApiResponse<>(profiles.create(user.id(), body));
    }

    @PatchMapping("/{profileId}")
    ApiResponse<PatientProfileOutput> update(@CurrentUser AuthenticatedUser user, @PathVariable String profileId,
            @Valid @RequestBody UpdatePatientProfileInput body) {
        return new ApiResponse<>(profiles.update(user.id(), profileId, body));
    }

    @DeleteMapping("/{profileId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void delete(@CurrentUser AuthenticatedUser user, @PathVariable String profileId) {
        profiles.delete(user.id(), profileId);
    }
}
