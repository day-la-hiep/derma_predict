import type { Metadata } from "next";
import { LoginPage } from "@/features/auth/components/LoginPage";

export const metadata: Metadata = { title: "Đăng nhập bác sĩ | Derma AI" };

export default function DoctorLoginRoute() {
  return <LoginPage area="doctor" />;
}
