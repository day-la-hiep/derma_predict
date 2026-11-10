package vn.derma.identity.controller;

import lombok.AllArgsConstructor;
import java.util.Arrays;
import java.util.List;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import vn.derma.identity.common.ApiResponse;
import vn.derma.identity.common.AppException;
import vn.derma.identity.mapper.IdentityMapper;
import vn.derma.identity.repository.PatientProfileRepository;
import vn.derma.identity.repository.UserRepository;
import vn.derma.identity.service.AuthService;
import vn.derma.identity.service.PatientProfileService;

/** Chỉ cho service khác (interceptor kiểm `X-Internal-Key`), không qua gateway. Danh sách ở services/contracts/README.md mục 3. */
@RestController
@RequestMapping("/internal")
@AllArgsConstructor
public class InternalController {

    public record ProfileRef(String id, String userId, String fullName) {
    }

    public record UserRef(String id, String fullName, String role) {
    }

    public record ProfileDetail(String id, String userId, String fullName, String dob, String gender, String relationship, String phone) {
    }

    private final PatientProfileService profiles;
    private final PatientProfileRepository profileRepository;
    private final UserRepository users;
    private final AuthService auth;
    private final IdentityMapper mapper;

    /** Tên và vai trò của tài khoản (consultation lưu sẵn tên bác sĩ khi nhận ca). */
    @GetMapping("/users/{userId}")
    ApiResponse<UserRef> getUser(@org.springframework.web.bind.annotation.PathVariable String userId) {
        return users.findById(userId)
                .map(u -> new ApiResponse<>(mapper.toUserRef(u, auth.getRole(u.id))))
                .orElseThrow(() -> AppException.notFound("tài khoản"));
    }

    /** Mọi hồ sơ của một tài khoản (clinical liệt kê lịch hẹn của người dùng). */
    @GetMapping("/patient-profiles/by-user")
    ApiResponse<List<ProfileDetail>> getProfilesOfUser(@RequestParam("user_id") String userId) {
        return new ApiResponse<>(profileRepository.findByUserIdOrderByCreatedAtAsc(userId).stream()
                .map(mapper::toProfileDetail).toList());
    }

    /** Thông tin hồ sơ của nhiều bệnh nhân cùng lúc (danh sách ca của bác sĩ); id không tồn tại thì bỏ qua. */
    @GetMapping("/patient-profiles")
    ApiResponse<List<ProfileDetail>> getProfiles(@RequestParam("ids") String ids) {
        List<String> wanted = Arrays.stream(ids.split(",")).map(String::trim).filter(x -> !x.isEmpty()).toList();
        return new ApiResponse<>(profileRepository.findAllById(wanted).stream()
                .map(mapper::toProfileDetail).toList());
    }

    /** consultation xác định hồ sơ thuộc tài khoản nào khi tạo hội thoại; 404 nếu không có hoặc không phải của tài khoản. */
    @GetMapping("/patient-profiles/resolve")
    ApiResponse<ProfileRef> resolveProfile(@RequestParam("user_id") String userId, @RequestParam(name = "profile_id", required = false) String profileId) {
        return profiles.resolveOwned(userId, profileId)
                .map(p -> new ApiResponse<>(mapper.toProfileRef(p)))
                .orElseThrow(() -> AppException.notFound("hồ sơ bệnh nhân"));
    }
}
