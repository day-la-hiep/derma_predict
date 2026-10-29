import type { Metadata } from "next";
import { AdminShell } from "@/features/admin/components/AdminShell";

export const metadata: Metadata = {
  title: "Quản trị tri thức | Derma AI",
  description: "Màn hình quản trị: nhập sách giáo khoa và cấu hình đồ thị tri thức",
};

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AdminShell>{children}</AdminShell>;
}
