import type { Metadata } from "next";
import { DoctorShell } from "@/features/doctor/components/DoctorShell";

export const metadata: Metadata = {
  title: "Khu bác sĩ | Derma AI",
  description: "Lịch khám, theo dõi sau khám và lịch sử khám của bác sĩ",
};

export default function DoctorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <DoctorShell>{children}</DoctorShell>;
}
