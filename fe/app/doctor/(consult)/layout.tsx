import { DoctorConsultationPage } from "@/features/doctor";

// nhóm (consult) không vào URL; layout giữ nguyên khi đổi ca nên SSE và danh sách ca không bị dựng lại
export default function ConsultLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <DoctorConsultationPage />
    </>
  );
}
