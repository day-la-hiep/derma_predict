import axios from "axios";

/**
 * Mỗi khu vực (bệnh nhân /chats /profile, bác sĩ /doctor, quản trị /admin) có phiên đăng nhập riêng trong localStorage,
 * nên đăng nhập hay đăng xuất ở khu này không ảnh hưởng khu kia. Khu hiện tại suy ra từ đường dẫn của trang.
 */
export type AuthArea = "patient" | "doctor" | "admin";
export const AUTH_STATE_EVENT = "derma-auth-state-change";

export type AuthenticatedUser = {
  id: string;
  username: string;
  full_name: string;
  dob: string;
  gender: "male" | "female";
  role: string;
};

export function areaOfPath(pathname: string): AuthArea {
  if (pathname.startsWith("/admin")) return "admin";
  if (pathname.startsWith("/doctor")) return "doctor";
  return "patient";
}

export function areaOfRole(role: string): AuthArea {
  return role === "doctor" || role === "admin" ? role : "patient";
}

export function getCurrentArea(): AuthArea {
  return typeof window === "undefined" ? "patient" : areaOfPath(window.location.pathname);
}

const HOME_PATH: Record<AuthArea, string> = { patient: "/chats", doctor: "/doctor", admin: "/admin" };
const LOGIN_PATH: Record<AuthArea, string> = { patient: "/login", doctor: "/doctor/login", admin: "/admin/login" };

export const homePathOf = (area: AuthArea): string => HOME_PATH[area];
export const loginPathOf = (area: AuthArea): string => LOGIN_PATH[area];
export const isLoginPath = (pathname: string): boolean => Object.values(LOGIN_PATH).includes(pathname);

const keyOf = (area: AuthArea, kind: "access-token" | "refresh-token" | "user") => `derma-auth-${area}-${kind}`;
const LEGACY_KEYS = ["derma-auth-access-token", "derma-auth-refresh-token", "derma-auth-user"] as const;

// Phiên cũ dùng chung một bộ khoá: chuyển sang khu đúng vai trò (nếu khu đó chưa có phiên) để không bắt đăng nhập lại
function migrateLegacySession(): void {
  try {
    const [access, refresh, user] = LEGACY_KEYS.map((k) => localStorage.getItem(k));
    if (!access && !refresh && !user) return;
    const role = user ? (JSON.parse(user) as AuthenticatedUser).role : "patient";
    const area = areaOfRole(role);
    if (!localStorage.getItem(keyOf(area, "access-token"))) {
      if (access) localStorage.setItem(keyOf(area, "access-token"), access);
      if (refresh) localStorage.setItem(keyOf(area, "refresh-token"), refresh);
      if (user) localStorage.setItem(keyOf(area, "user"), user);
    }
    LEGACY_KEYS.forEach((k) => localStorage.removeItem(k));
  } catch {
    // localStorage bị chặn hoặc dữ liệu hỏng: bỏ qua, người dùng đăng nhập lại
  }
}

function read(area: AuthArea, kind: "access-token" | "refresh-token" | "user"): string | null {
  if (typeof window === "undefined") return null;
  migrateLegacySession();
  try {
    return localStorage.getItem(keyOf(area, kind));
  } catch {
    return null;
  }
}

function notify(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(AUTH_STATE_EVENT));
}

export function getAccessToken(area: AuthArea = getCurrentArea()): string | null {
  return read(area, "access-token");
}

export function getRefreshToken(area: AuthArea = getCurrentArea()): string | null {
  return read(area, "refresh-token");
}

export function clearAccessToken(area: AuthArea = getCurrentArea()): void {
  try {
    localStorage.removeItem(keyOf(area, "access-token"));
  } catch {
    // no-op
  }
}

export function getAuthenticatedUser(area: AuthArea = getCurrentArea()): AuthenticatedUser | null {
  try {
    const user = read(area, "user");
    return user ? (JSON.parse(user) as AuthenticatedUser) : null;
  } catch {
    return null;
  }
}

/** Id tài khoản đang đăng nhập ở khu hiện tại (rỗng khi chưa có phiên). */
export function getCurrentUserId(): string {
  return getAuthenticatedUser()?.id ?? "";
}

/** Lưu phiên vào khu của vai trò tài khoản (không phải khu của trang hiện tại); trả về khu đã lưu. */
export function setAuthSession(accessToken: string, refreshToken: string, user: AuthenticatedUser): AuthArea {
  const area = areaOfRole(user.role);
  try {
    localStorage.setItem(keyOf(area, "access-token"), accessToken);
    localStorage.setItem(keyOf(area, "refresh-token"), refreshToken);
    localStorage.setItem(keyOf(area, "user"), JSON.stringify(user));
  } catch {
    // Phiên hiện tại vẫn có thể dùng access token nếu localStorage bị chặn.
  }
  notify();
  return area;
}

/** Cập nhật user đã lưu sau khi sửa thông tin tài khoản (không đổi token). */
export function updateStoredUser(user: AuthenticatedUser): void {
  try {
    localStorage.setItem(keyOf(areaOfRole(user.role), "user"), JSON.stringify(user));
  } catch {
    // Phiên hiện tại vẫn dùng được, chỉ không cache tên mới nếu localStorage bị chặn.
  }
  notify();
}

/** Xoá phiên của một khu (mặc định khu hiện tại); các khu khác giữ nguyên. */
export function clearAuthSession(area: AuthArea = getCurrentArea()): void {
  try {
    (["access-token", "refresh-token", "user"] as const).forEach((k) => localStorage.removeItem(keyOf(area, k)));
  } catch {
    // no-op
  }
  notify();
}

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "/api/v1",
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Nơi để thêm interceptor sau này: refresh token, map lỗi HTTP -> thông báo hiển thị, v.v.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const url = error?.config?.url ?? "";
    const isCredentialSubmission = /^\/auth\/(login|register)$/.test(url);
    if (error?.response?.status === 401 && !isCredentialSubmission) {
      clearAccessToken();
      if (typeof window !== "undefined") {
        window.location.reload();
      }
    }
    return Promise.reject(error);
  }
);
