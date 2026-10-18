import { Phone, TriangleAlert } from "lucide-react";
import { RELATIONSHIP_LABELS } from "@/features/patient-profile/constants";
import type { PatientProfile } from "../types";

function calculateAge(dob: string): number | null {
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor((Date.now() - d.getTime()) / (365.25 * 24 * 3600 * 1000));
}

/** "Nữ · 31 tuổi · Bản thân · Sinh 20/5/1995" */
export function patientSubtitle(patient: PatientProfile): string {
  const parts = [patient.gender === "female" ? "Nữ" : "Nam"];
  const age = patient.dob ? calculateAge(patient.dob) : null;
  if (age !== null) parts.push(`${age} tuổi`);
  if (patient.relationship) parts.push(RELATIONSHIP_LABELS[patient.relationship]);
  parts.push(patient.dob ? `Sinh ${new Date(patient.dob).toLocaleDateString("vi-VN")}` : "Chưa có ngày sinh");
  return parts.join(" · ");
}

export function PatientProfileDetails({ patient }: { patient: PatientProfile }) {
  return (
    <div className="space-y-4">
      {patient.phone && (
        <p className="flex items-center gap-1.5 text-sm text-foreground">
          <Phone className="size-3.5 text-muted-foreground" /> {patient.phone}
        </p>
      )}

      {patient.allergies && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 dark:border-amber-800/50 dark:bg-amber-950/30">
          <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-400">
            <TriangleAlert className="size-3.5" /> Dị ứng
          </p>
          <p className="mt-1 text-sm text-foreground">{patient.allergies}</p>
        </div>
      )}

      {patient.medicalHistory && (
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Tiền sử bệnh</p>
          <p className="mt-1 text-sm text-foreground">{patient.medicalHistory}</p>
        </div>
      )}
    </div>
  );
}
