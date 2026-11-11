package vn.derma.identity.common;

import org.springframework.http.HttpStatus;

/** Lỗi nghiệp vụ; thông báo hiển thị nguyên văn cho người dùng. */
public class AppException extends RuntimeException {

    private final HttpStatus status;

    private AppException(HttpStatus status, String message) {
        super(message);
        this.status = status;
    }

    public static AppException notFound(String what) {
        return new AppException(HttpStatus.NOT_FOUND, "Không tìm thấy: " + what);
    }

    public static AppException conflict(String message) {
        return new AppException(HttpStatus.CONFLICT, message);
    }

    public static AppException unauthorized(String message) {
        return new AppException(HttpStatus.UNAUTHORIZED, message);
    }

    public static AppException forbidden(String message) {
        return new AppException(HttpStatus.FORBIDDEN, message);
    }

    public static AppException invalid(String message) {
        return new AppException(HttpStatus.UNPROCESSABLE_ENTITY, message);
    }

    public static AppException badGateway(String message) {
        return new AppException(HttpStatus.BAD_GATEWAY, message);
    }

    public HttpStatus status() {
        return status;
    }
}
