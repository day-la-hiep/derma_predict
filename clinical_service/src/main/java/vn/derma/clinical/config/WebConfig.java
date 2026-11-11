package vn.derma.clinical.config;

import lombok.AllArgsConstructor;
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.MethodParameter;
import org.springframework.web.bind.support.WebDataBinderFactory;
import org.springframework.web.context.request.NativeWebRequest;
import org.springframework.web.method.support.HandlerMethodArgumentResolver;
import org.springframework.web.method.support.ModelAndViewContainer;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import vn.derma.clinical.common.AppException;
import vn.derma.clinical.common.AuthenticatedUser;
import vn.derma.clinical.common.CurrentUser;
import vn.derma.clinical.service.TokenService;

@Configuration
@AllArgsConstructor
public class WebConfig implements WebMvcConfigurer {

    private final TokenService tokens;
    private final DermaProperties properties;

    /** `/internal/**` chỉ nhận lời gọi giữa service, kèm `X-Internal-Key`. */
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new org.springframework.web.servlet.HandlerInterceptor() {
            @Override
            public boolean preHandle(jakarta.servlet.http.HttpServletRequest request, jakarta.servlet.http.HttpServletResponse response, Object handler) {
                if (!properties.internalApiKey().equals(request.getHeader("X-Internal-Key"))) {
                    throw AppException.forbidden("Thiếu hoặc sai X-Internal-Key.");
                }
                return true;
            }
        }).addPathPatterns("/internal/**");
    }

    @Override
    public void addArgumentResolvers(List<HandlerMethodArgumentResolver> resolvers) {
        resolvers.add(new HandlerMethodArgumentResolver() {
            @Override
            public boolean supportsParameter(MethodParameter parameter) {
                return parameter.hasParameterAnnotation(CurrentUser.class);
            }

            @Override
            public Object resolveArgument(MethodParameter parameter, ModelAndViewContainer mav, NativeWebRequest request,
                    WebDataBinderFactory binderFactory) {
                String header = request.getHeader("Authorization");
                if (header == null || !header.startsWith("Bearer ")) {
                    throw AppException.unauthorized("Yêu cầu đăng nhập (thiếu Authorization Bearer header).");
                }
                TokenService.Claims claims = tokens.parse(header.substring("Bearer ".length()).trim());
                if (!"access".equals(claims.type()) || claims.userId() == null) {
                    throw AppException.unauthorized("Token không phải là access token.");
                }
                return new AuthenticatedUser(claims.userId(), claims.role());
            }
        });
    }
}
