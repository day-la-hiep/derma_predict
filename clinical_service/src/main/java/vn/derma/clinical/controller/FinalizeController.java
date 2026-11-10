package vn.derma.clinical.controller;

import lombok.AllArgsConstructor;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import tools.jackson.databind.JsonNode;
import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.common.AuthenticatedUser;
import vn.derma.clinical.common.CurrentUser;
import vn.derma.clinical.client.IdentityClient;
import vn.derma.clinical.dto.FinalizeDtos.EncounterDraftOutput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeDraftOutput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeInput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeReportItemOutput;
import vn.derma.clinical.dto.FinalizeDtos.FinalizeReportOutput;
import vn.derma.clinical.dto.FinalizeDtos.PatientFinalizeReportOutput;
import vn.derma.clinical.service.FinalizeReportService;

/** Báo cáo kết luận. `/doctor/consultations/{id}/finalize*` nằm ở đây, không phải consultation (gateway route theo đường dẫn dài hơn trước). */
@RestController
@RequestMapping("/api/v1")
@AllArgsConstructor
public class FinalizeController {

    private final FinalizeReportService service;
    private final IdentityClient identity;

    @GetMapping("/patient-profiles/{profileId}/finalize-reports")
    ApiResponse<List<PatientFinalizeReportOutput>> listForPatient(@CurrentUser AuthenticatedUser user, @PathVariable String profileId) {
        return new ApiResponse<>(service.listForPatient(user.id(), profileId));
    }

    @GetMapping("/doctor/consultations/{sessionId}/finalize-reports")
    ApiResponse<List<FinalizeReportOutput>> listForSession(@CurrentUser AuthenticatedUser user, @PathVariable String sessionId) {
        requireDoctor(user);
        return new ApiResponse<>(service.listForSession(sessionId, user.id()));
    }

    @GetMapping("/doctor/consultations/{sessionId}/finalize-draft")
    ApiResponse<FinalizeDraftOutput> draftForSession(@CurrentUser AuthenticatedUser user, @PathVariable String sessionId) {
        requireDoctor(user);
        return new ApiResponse<>(service.draftForSession(sessionId, user.id()));
    }

    @PostMapping("/doctor/consultations/{sessionId}/finalize")
    @ResponseStatus(HttpStatus.CREATED)
    ApiResponse<FinalizeReportOutput> finalizeSession(@CurrentUser AuthenticatedUser user, @PathVariable String sessionId, @Valid @RequestBody FinalizeInput body) {
        requireDoctor(user);
        return new ApiResponse<>(service.finalizeSession(sessionId, user.id(), doctorName(user), body));
    }

    @GetMapping("/doctor/finalize-reports")
    ApiResponse<List<FinalizeReportItemOutput>> listMine(@CurrentUser AuthenticatedUser user, @RequestParam(defaultValue = "") String q) {
        requireDoctor(user);
        if (q.length() > 100) {
            throw AppException.invalid("Từ khoá tối đa 100 ký tự.");
        }
        return new ApiResponse<>(service.listMine(user.id(), q));
    }

    @GetMapping("/doctor/patient-profiles/{profileId}/finalize-reports")
    ApiResponse<List<FinalizeReportOutput>> listForProfile(@CurrentUser AuthenticatedUser user, @PathVariable String profileId) {
        requireDoctor(user);
        return new ApiResponse<>(service.listForProfile(profileId));
    }

    @GetMapping({ "/doctor/patient-profiles/{profileId}/journey-graph", "/doctor/patients/{profileId}/journey-graph" })
    ApiResponse<JsonNode> getJourneyGraph(@CurrentUser AuthenticatedUser user, @PathVariable String profileId) {
        requireDoctor(user);
        return new ApiResponse<>(service.getJourneyGraph(profileId));
    }

    @GetMapping("/doctor/encounters/{encounterId}/finalize-draft")
    ApiResponse<EncounterDraftOutput> draftForEncounter(@CurrentUser AuthenticatedUser user, @PathVariable String encounterId) {
        requireDoctor(user);
        return new ApiResponse<>(service.draftForEncounter(encounterId, user.id()));
    }

    @PostMapping("/doctor/encounters/{encounterId}/finalize")
    @ResponseStatus(HttpStatus.CREATED)
    ApiResponse<FinalizeReportOutput> finalizeEncounter(@CurrentUser AuthenticatedUser user, @PathVariable String encounterId, @Valid @RequestBody FinalizeInput body) {
        requireDoctor(user);
        return new ApiResponse<>(service.finalizeEncounter(encounterId, user.id(), doctorName(user), body));
    }

    /** Tên bác sĩ lưu cùng báo cáo để khỏi gọi identity mỗi lần liệt kê. */
    private String doctorName(AuthenticatedUser user) {
        return identity.getUser(user.id()).map(IdentityClient.UserRef::fullName).orElse(null);
    }

    private static void requireDoctor(AuthenticatedUser user) {
        if (!"doctor".equals(user.role())) {
            throw AppException.forbidden("Bạn không có quyền truy cập chức năng này (yêu cầu vai trò: doctor).");
        }
    }
}
