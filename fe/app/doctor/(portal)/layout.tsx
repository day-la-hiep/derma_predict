import type { Metadata } from "next";
import { DoctorShell } from "@/features/doctor/components/DoctorShell";

export const metadata: Metadata = {
  title: "Khu bác sĩ | Derma AI",
  description: "Ca khám, hồ sơ nhận định và trao đổi sau khám của bác sĩ",
};

export default function DoctorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DoctorShell>{children}</DoctorShell>;
}
