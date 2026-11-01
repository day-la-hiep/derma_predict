import { MedicalHistoryPage } from "@/features/doctor";

// layout giữ nguyên khi đổi báo cáo nên bộ lọc và ô tìm kiếm không bị đặt lại
export default function RecordsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <MedicalHistoryPage />
    </>
  );
}
