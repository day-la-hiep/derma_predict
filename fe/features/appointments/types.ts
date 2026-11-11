import type { ClinicalFact, FinalizeDraft, PatientProfile } from "@/features/doctor";

export type AppointmentStatus = "requested" | "confirmed" | "in_progress" | "done" | "cancelled" | "no_show";

export interface Appointment {
  id: string;
  patientProfileId: string;
  episodeId: string;
  bodySite: string;
  bodySiteLabel: string;
  doctorId: string | null;
  doctorName: string | null;
  scheduledAt: string;
  status: AppointmentStatus;
  reason: string;
  cancelReason: string | null;
  createdAt: string;
  encounterId: string | null;
}

/** Đợt bệnh nhìn từ bệnh nhân: không có giả thuyết AI */
export interface PatientEpisode {
  id: string;
  bodySite: string;
  bodySiteLabel: string;
  status: string;
  updatedAt: string;
  facts: string[];
  bookable: boolean;
  notBookableReason: string | null;
  appointment: Appointment | null;
}

/** Tham chiếu để mở đúng đoạn sách đã dẫn; ca cũ không có */
export interface EvidenceRef {
  documentId: string;
  chunkId: string | null;
  pageStart: number | null;
  pageEnd: number | null;
}

export interface Evidence {
  source: string;
  text: string;
  ref: EvidenceRef | null;
}

export interface Hypothesis {
  rank: number;
  diagnosisCode: string;
  diagnosisLabel: string;
  disease: string;
  confidence: string;
  evidence: Evidence[];
  missing: string[];
}

export interface ImagePrediction {
  fileId: string;
  url: string | null;
  fileName: string;
  topK: { label: string; labelName: string; score: number }[];
}

export interface DoctorEpisode {
  id: string;
  bodySite: string;
  bodySiteLabel: string;
  status: string;
  summary: string;
  urgency: string | null;
  redFlags: string[];
  hypotheses: Hypothesis[];
  hypothesesLocked: boolean;
  facts: ClinicalFact[];
  imagePredictions: ImagePrediction[];
  updatedAt: string;
  disclaimer: string;
}

export interface DoctorAppointment extends Appointment {
  patient: PatientProfile;
  topHypothesis: string | null;
}

export interface DoctorAppointmentDetail extends DoctorAppointment {
  episode: DoctorEpisode;
  longTermFacts: ClinicalFact[];
  otherEpisodes: PatientEpisode[];
}

export interface DiagnosisOption {
  code: string;
  label: string;
}

export interface EncounterDraft extends FinalizeDraft {
  encounterId: string;
  appointmentId: string;
  episode: DoctorEpisode;
  images: ImagePrediction[];
  diagnosisOptions: DiagnosisOption[];
}
