"use client";

import { Suspense } from "react";
import { DoctorConsultationPage } from "@/features/doctor";

export default function DoctorPage() {
  // `?session=` (từ nút "Mở ca gốc") đọc bằng useSearchParams nên cần Suspense
  return (
    <Suspense>
      <DoctorConsultationPage />
    </Suspense>
  );
}
