package vn.derma.clinical.controller;

import lombok.AllArgsConstructor;
import java.time.Instant;
import java.util.List;

import org.springframework.format.annotation.DateTimeFormat;
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
import vn.derma.clinical.common.ApiResponse;
import vn.derma.clinical.common.AppException;
import vn.derma.clinical.common.AuthenticatedUser;
import vn.derma.clinical.common.CurrentUser;
import vn.derma.clinical.dto.AppointmentDtos.AppointmentOutput;
import vn.derma.clinical.dto.AppointmentDtos.BookAppointmentInput;
import vn.derma.clinical.dto.AppointmentDtos.CancelAppointmentInput;
import vn.derma.clinical.dto.AppointmentDtos.ChangeEpisodeInput;
import vn.derma.clinical.dto.AppointmentDtos.DoctorAppointmentDetailOutput;
import vn.derma.clinical.dto.AppointmentDtos.DoctorAppointmentItemOutput;
import vn.derma.clinical.dto.AppointmentDtos.PatientEpisodeOutput;
import vn.derma.clinical.service.AppointmentService;

@RestController
@RequestMapping("/api/v1")
@AllArgsConstructor
public class AppointmentController {

    private final AppointmentService service;

    @GetMapping("/patient-profiles/{profileId}/episodes")
    ApiResponse<List<PatientEpisodeOutput>> listEpisodes(@CurrentUser AuthenticatedUser user, @PathVariable String profileId) {
        return new ApiResponse<>(service.listEpisodes(user.id(), profileId));
    }

    @PostMapping("/appointments")
    @ResponseStatus(HttpStatus.CREATED)
    ApiResponse<AppointmentOutput> book(@CurrentUser AuthenticatedUser user, @Valid @RequestBody BookAppointmentInput body) {
        return new ApiResponse<>(service.book(user.id(), body));
    }

    @GetMapping("/appointments")
    ApiResponse<List<AppointmentOutput>> listMine(@CurrentUser AuthenticatedUser user) {
        return new ApiResponse<>(service.listMine(user.id()));
    }

    @PostMapping("/appointments/{id}/cancel")
    ApiResponse<AppointmentOutput> cancelMine(@CurrentUser AuthenticatedUser user, @PathVariable String id, @Valid @RequestBody CancelAppointmentInput body) {
        return new ApiResponse<>(service.cancelMine(user.id(), id, body.reason()));
    }

    @GetMapping("/doctor/appointments")
    ApiResponse<List<DoctorAppointmentItemOutput>> listForDoctor(@CurrentUser AuthenticatedUser user,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant start,
            @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) Instant end, @RequestParam(required = false) String status) {
        requireDoctor(user);
        return new ApiResponse<>(service.listForDoctor(user.id(), start, end, status));
    }

    @GetMapping("/doctor/appointments/{id}")
    ApiResponse<DoctorAppointmentDetailOutput> detail(@CurrentUser AuthenticatedUser user, @PathVariable String id) {
        requireDoctor(user);
        return new ApiResponse<>(service.detail(user.id(), id));
    }

    @PostMapping("/doctor/appointments/{id}/confirm")
    ApiResponse<DoctorAppointmentDetailOutput> confirm(@CurrentUser AuthenticatedUser user, @PathVariable String id) {
        requireDoctor(user);
        return new ApiResponse<>(service.confirm(user.id(), id));
    }

    @PostMapping("/doctor/appointments/{id}/cancel")
    ApiResponse<DoctorAppointmentDetailOutput> cancelByDoctor(@CurrentUser AuthenticatedUser user, @PathVariable String id,
            @Valid @RequestBody CancelAppointmentInput body) {
        requireDoctor(user);
        return new ApiResponse<>(service.cancelByDoctor(user.id(), id, body.reason()));
    }

    @PostMapping("/doctor/appointments/{id}/no-show")
    ApiResponse<DoctorAppointmentDetailOutput> noShow(@CurrentUser AuthenticatedUser user, @PathVariable String id) {
        requireDoctor(user);
        return new ApiResponse<>(service.markNoShow(user.id(), id));
    }

    @PostMapping("/doctor/appointments/{id}/change-episode")
    ApiResponse<DoctorAppointmentDetailOutput> changeEpisode(@CurrentUser AuthenticatedUser user, @PathVariable String id,
            @Valid @RequestBody ChangeEpisodeInput body) {
        requireDoctor(user);
        return new ApiResponse<>(service.changeEpisode(user.id(), id, body.episodeId()));
    }

    @PostMapping("/doctor/appointments/{id}/start")
    ApiResponse<DoctorAppointmentDetailOutput> start(@CurrentUser AuthenticatedUser user, @PathVariable String id) {
        requireDoctor(user);
        return new ApiResponse<>(service.startEncounter(user.id(), id));
    }

    private static void requireDoctor(AuthenticatedUser user) {
        if (!"doctor".equals(user.role())) {
            throw AppException.forbidden("Bạn không có quyền truy cập chức năng này (yêu cầu vai trò: doctor).");
        }
    }
}
