import type { Metadata } from "next";
import { LoginPage } from "@/features/auth/components/LoginPage";

export const metadata: Metadata = { title: "Đăng nhập quản trị | Derma AI" };

export default function AdminLoginRoute() {
  return <LoginPage area="admin" />;
}
