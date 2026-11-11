package vn.derma.consultation.controller;

import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import lombok.AllArgsConstructor;
import vn.derma.consultation.common.ApiResponse;
import vn.derma.consultation.common.AppException;
import vn.derma.consultation.common.AuthenticatedUser;
import vn.derma.consultation.common.CurrentUser;
import vn.derma.consultation.dto.FollowupDtos.FollowupChannelOutput;
import vn.derma.consultation.service.FollowupService;

@RestController
@RequestMapping("/api/v1")
@AllArgsConstructor
public class FollowupController {

    private final FollowupService followups;

    @GetMapping("/followup-channels/by-encounter/{encounterId}")
    ApiResponse<FollowupChannelOutput> getByEncounter(@CurrentUser AuthenticatedUser user, @PathVariable String encounterId) {
        return new ApiResponse<>(followups.getByEncounter(encounterId, user));
    }

    @GetMapping("/doctor/followup-channels")
    ApiResponse<List<FollowupChannelOutput>> listMine(@CurrentUser AuthenticatedUser user) {
        requireDoctor(user);
        return new ApiResponse<>(followups.listForDoctor(user.id()));
    }

    private static void requireDoctor(AuthenticatedUser user) {
        if (!"doctor".equals(user.role())) {
            throw AppException.forbidden("Bạn không có quyền truy cập chức năng này (yêu cầu vai trò: doctor).");
        }
    }
}
