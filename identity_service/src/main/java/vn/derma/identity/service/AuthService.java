package vn.derma.identity.service;

import lombok.AllArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import java.util.Optional;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import vn.derma.identity.common.AppException;
import vn.derma.identity.dto.AuthDtos.LoginInput;
import vn.derma.identity.dto.AuthDtos.RegisterInput;
import vn.derma.identity.dto.AuthDtos.TokenPairOutput;
import vn.derma.identity.dto.AuthDtos.UpdateAccountInput;
import vn.derma.identity.dto.AuthDtos.UserSummaryOutput;
import vn.derma.identity.dto.Gender;
import vn.derma.identity.entity.PatientProfile;
import vn.derma.identity.entity.User;
import vn.derma.identity.mapper.IdentityMapper;
import vn.derma.identity.repository.AdminRepository;
import vn.derma.identity.repository.DoctorRepository;
import vn.derma.identity.repository.PatientProfileRepository;
import vn.derma.identity.repository.UserRepository;

@Service
@Slf4j
@AllArgsConstructor
public class AuthService {

    private static final String REFRESH_KEY = "auth:refresh:%s:%s";

    private final UserRepository users;
    private final DoctorRepository doctors;
    private final AdminRepository admins;
    private final PatientProfileRepository profiles;
    private final TokenService tokens;
    private final StringRedisTemplate redis;
    private final BCryptPasswordEncoder passwordEncoder = new BCryptPasswordEncoder();
    private final IdentityMapper mapper;

    @Transactional
    public TokenPairOutput register(RegisterInput input) {
        if (users.findByUsername(input.username()).isPresent()) {
            throw AppException.conflict("Tên đăng nhập '" + input.username() + "' đã được sử dụng.");
        }
        User user = new User();
        user.username = input.username();
        user.fullName = input.fullName();
        user.dob = input.dob();
        user.gender = input.gender().value();
        user.passwordHash = passwordEncoder.encode(input.password());
        users.save(user);

        PatientProfile profile = new PatientProfile();
        profile.userId = user.id;
        profile.fullName = user.fullName;
        profile.dob = user.dob;
        profile.gender = user.gender;
        profiles.save(profile);
        return createTokenPair(user, "patient");
    }

    public TokenPairOutput login(LoginInput input) {
        Optional<User> found = users.findByUsername(input.username());
        if (found.isEmpty() || found.get().passwordHash == null
                || !passwordEncoder.matches(input.password(), found.get().passwordHash)) {
            throw AppException.unauthorized("Tên đăng nhập hoặc mật khẩu không chính xác.");
        }
        return createTokenPair(found.get(), getRole(found.get().id));
    }

    /** Làm mới token; refresh cũ bị thu hồi (rotation). */
    public TokenPairOutput refresh(String refreshToken) {
        TokenService.Claims claims = tokens.parse(refreshToken);
        if (!"refresh".equals(claims.type())) {
            throw AppException.unauthorized("Loại token không hợp lệ.");
        }
        if (claims.userId() == null || claims.jti() == null) {
            throw AppException.unauthorized("Token thiếu thông tin định danh.");
        }
        if (!Boolean.TRUE.equals(redis.delete(REFRESH_KEY.formatted(claims.userId(), claims.jti())))) {
            throw AppException.unauthorized("Refresh token đã bị thu hồi hoặc đã hết hạn.");
        }
        User user = users.findById(claims.userId())
                .orElseThrow(() -> AppException.unauthorized("Không tìm thấy tài khoản người dùng."));
        return createTokenPair(user, getRole(user.id));
    }

    public void logout(String refreshToken) {
        try {
            TokenService.Claims claims = tokens.parse(refreshToken);
            if ("refresh".equals(claims.type()) && claims.userId() != null && claims.jti() != null) {
                redis.delete(REFRESH_KEY.formatted(claims.userId(), claims.jti()));
            }
        } catch (AppException e) {
            // đăng xuất với token đã hỏng/hết hạn thì không còn gì để thu hồi
            log.info("Bỏ qua logout vì refresh token không hợp lệ: {}", e.getMessage());
        }
    }

    public UserSummaryOutput getAccount(String userId) {
        User user = users.findById(userId).orElseThrow(() -> AppException.unauthorized("Không tìm thấy tài khoản người dùng."));
        return mapper.toSummary(user, getRole(userId));
    }

    @Transactional
    public UserSummaryOutput updateAccount(String userId, UpdateAccountInput input) {
        User user = users.findById(userId).orElseThrow(() -> AppException.unauthorized("Không tìm thấy tài khoản người dùng."));
        if (input.fullName() != null) {
            user.fullName = input.fullName();
        }
        if (input.dob() != null) {
            user.dob = input.dob();
        }
        if (input.gender() != null) {
            user.gender = input.gender().value();
        }
        return mapper.toSummary(user, getRole(userId));
    }

    public String getRole(String userId) {
        if (admins.existsById(userId)) {
            return "admin";
        }
        return doctors.existsById(userId) ? "doctor" : "patient";
    }

    private TokenPairOutput createTokenPair(User user, String role) {
        TokenService.RefreshToken refresh = tokens.createRefreshToken(user.id);
        redis.opsForValue().set(REFRESH_KEY.formatted(user.id, refresh.jti()), "1", refresh.ttl());
        return new TokenPairOutput(tokens.createAccessToken(user.id, user.username, role), refresh.token(), "bearer", mapper.toSummary(user, role));
    }
}
