import axios from "axios";
import { api, updateStoredUser, type AuthenticatedUser } from "@/services/client";

export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
    if (!e.response) return "Không kết nối được máy chủ. Vui lòng thử lại.";
    return `Lỗi HTTP ${e.response.status}`;
  }
  return e instanceof Error ? e.message : "Đã có lỗi không xác định xảy ra.";
}

export async function updateAccount(body: {
  full_name: string;
  dob: string;
  gender: "male" | "female";
}): Promise<AuthenticatedUser> {
  const res = await api.patch<{ data: AuthenticatedUser }>("/auth/me", body);
  const user = res.data.data;
  updateStoredUser(user);
  return user;
}
