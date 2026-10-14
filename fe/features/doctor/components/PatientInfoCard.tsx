import { TriangleAlert } from "lucide-react";
import { Hint, HintIcon } from "@/components/ui/hint";
import { RELATIONSHIP_LABELS } from "@/features/patient-profile/constants";
import type { PatientProfile } from "../types";

export function PatientInfoCard({ patient, reason }: { patient: PatientProfile; reason: string }) {
  const dob = patient?.dob ? new Date(patient.dob).toLocaleDateString("vi-VN") : "Chưa cập nhật";
  const gender = patient?.gender === "female" ? "Nữ" : "Nam";
  const relationship = patient?.relationship ? RELATIONSHIP_LABELS[patient.relationship] : null;

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5">
        <Hint side="left" content={`Ngày sinh: ${dob}`}>
          <p className="w-fit text-sm font-semibold text-foreground">
            {patient?.fullName ?? "Chưa rõ"} <span className="font-normal text-muted-foreground">· {gender}</span>
            {relationship && <span className="font-normal text-muted-foreground"> · {relationship}</span>}
          </p>
        </Hint>
        {(patient?.phone || patient?.medicalHistory) && (
          <HintIcon
            side="left"
            content={
              <div className="space-y-1">
                {patient.phone && <p>SĐT: {patient.phone}</p>}
                {patient.medicalHistory && <p>Tiền sử: {patient.medicalHistory}</p>}
              </div>
            }
          />
        )}
      </div>
      {patient?.allergies && (
        <p className="flex items-center gap-1 text-xs font-medium text-amber-600 dark:text-amber-400">
          <TriangleAlert className="size-3.5 shrink-0" /> Dị ứng: {patient.allergies}
        </p>
      )}
      <Hint side="left" content={`Lý do tư vấn: ${reason || "chưa ghi"}`}>
        <p className="line-clamp-2 text-xs leading-relaxed text-muted-foreground">{reason}</p>
      </Hint>
    </div>
  );
}
