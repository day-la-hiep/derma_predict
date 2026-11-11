package vn.derma.identity.controller;

import lombok.AllArgsConstructor;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;
import vn.derma.identity.common.ApiResponse;
import vn.derma.identity.common.AuthenticatedUser;
import vn.derma.identity.common.CurrentUser;
import vn.derma.identity.dto.AuthDtos.LoginInput;
import vn.derma.identity.dto.AuthDtos.RefreshTokenInput;
import vn.derma.identity.dto.AuthDtos.RegisterInput;
import vn.derma.identity.dto.AuthDtos.TokenPairOutput;
import vn.derma.identity.dto.AuthDtos.UpdateAccountInput;
import vn.derma.identity.dto.AuthDtos.UserSummaryOutput;
import vn.derma.identity.service.AuthService;

@RestController
@RequestMapping("/api/v1/auth")
@AllArgsConstructor
public class AuthController {

    private final AuthService auth;

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    ApiResponse<TokenPairOutput> register(@Valid @RequestBody RegisterInput body) {
        return new ApiResponse<>(auth.register(body));
    }

    @PostMapping("/login")
    ApiResponse<TokenPairOutput> login(@Valid @RequestBody LoginInput body) {
        return new ApiResponse<>(auth.login(body));
    }

    @PostMapping("/refresh")
    ApiResponse<TokenPairOutput> refresh(@Valid @RequestBody RefreshTokenInput body) {
        return new ApiResponse<>(auth.refresh(body.refreshToken()));
    }

    @PostMapping("/logout")
    ApiResponse<Map<String, String>> logout(@Valid @RequestBody RefreshTokenInput body) {
        auth.logout(body.refreshToken());
        return new ApiResponse<>(Map.of("message", "Đăng xuất thành công."));
    }

    @GetMapping("/me")
    ApiResponse<UserSummaryOutput> getAccount(@CurrentUser AuthenticatedUser user) {
        return new ApiResponse<>(auth.getAccount(user.id()));
    }

    @PatchMapping("/me")
    ApiResponse<UserSummaryOutput> updateAccount(@CurrentUser AuthenticatedUser user, @Valid @RequestBody UpdateAccountInput body) {
        return new ApiResponse<>(auth.updateAccount(user.id(), body));
    }
}
