import type { Metadata } from "next";
import { LoginPage } from "@/features/auth/components/LoginPage";

export const metadata: Metadata = { title: "Đăng nhập | Derma AI" };

export default function PatientLoginRoute() {
  return <LoginPage area="patient" />;
}
