import { api, clearAuthSession, getCurrentArea, getRefreshToken, loginPathOf } from "@/services/client";

// Chỉ đăng xuất khu hiện tại (bệnh nhân / bác sĩ / quản trị); phiên của các khu khác trong cùng trình duyệt giữ nguyên.
export async function logout(): Promise<void> {
  const area = getCurrentArea();
  const refreshToken = getRefreshToken(area);
  if (refreshToken) {
    try {
      await api.post("/auth/logout", { refresh_token: refreshToken });
    } catch {
      // xoá phiên cục bộ dù không gọi được API
    }
  }
  clearAuthSession(area);
  // tải lại hẳn trang (không điều hướng mềm): store còn dữ liệu của tài khoản cũ, tài khoản sau không được thấy
  window.location.assign(loginPathOf(area));
}
