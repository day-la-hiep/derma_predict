/**
 * Types cho màn hình bác sĩ — báo cáo tư vấn (consultation report).
 *
 * Map từ database schema: `consultation_sessions`, `pre_consultation_reports`,
 * `clinical_facts`, `clinical_fact_templates`, `patient_profiles`, `messages`.
 */

/* ────────── Patient Profile ────────── */

export type ProfileRelationship = "self" | "child" | "parent" | "spouse" | "other";

export interface PatientProfile {
  id: string;
  fullName: string;
  dob: string;
  gender: "male" | "female";
  relationship: ProfileRelationship;
  phone: string | null;
  allergies: string;
  medicalHistory: string;
}

/* ────────── Finalize Report (báo cáo kết luận) ────────── */

export type Urgency = "emergency" | "few_days" | "monitor";
export type FactOrigin = "patient_reported" | "ai_inferred" | "doctor_observed" | "doctor_corrected";

export interface SnapshotFile {
  fileName: string;
  contentType: string | null;
  url: string | null;
}

export interface SnapshotMessage {
  id: string;
  sender: "patient" | "ai" | "doctor";
  content: string;
  createdAt: string | null;
  files: SnapshotFile[];
}

export interface SnapshotFact {
  factType: ClinicalFactType;
  label: string;
  detail: string;
  origin: FactOrigin;
  sources: SnapshotMessage[];
}

/** Bản chụp bất biến của phiếu bác sĩ đã chốt (cột `finalize_reports.snapshot`) */
export interface FinalizeReportSnapshot {
  patientProfile: Omit<PatientProfile, "id">;
  assessment: { reasoning: string; urgency: Urgency; instructions: string[] };
  clinicalFacts: SnapshotFact[];
}

export interface FinalizeReportImage {
  id: string;
  file: { fileName: string; contentType: string | null; storageKey: string; url: string | null };
  bodySite: string;
  description: string;
  confirmedLabel: string | null;
  capturedAt: string | null;
}

export interface FinalizeReport {
  id: string;
  diagnosis: string;
  notes: string;
  isReferenceCase: boolean;
  doctorName: string | null;
  createdAt: string;
  consultationSessionId: string | null;
  conversationId: string | null;
  /** null với báo cáo kết luận ghi trước khi có snapshot */
  snapshot: FinalizeReportSnapshot | null;
  images: FinalizeReportImage[];
}

/** Một dòng ở màn Lịch sử khám: báo cáo kết luận kèm hồ sơ bệnh nhân */
export interface FinalizeReportItem extends FinalizeReport {
  patient: PatientProfile;
}

/** Một dòng dữ kiện trong form chốt */
export interface FactDraft {
  key: string;
  /** fact trích từ hội thoại mà dòng này dựa vào; null = bác sĩ tự ghi */
  sourceFactId: string | null;
  factType: ClinicalFactType;
  label: string;
  detail: string;
  /** giá trị gốc để biết bác sĩ đã sửa hay chưa (tính origin hiển thị) */
  original: { label: string; detail: string; factType: ClinicalFactType; origin: FactOrigin } | null;
  sources: SnapshotMessage[];
}

/** Gợi ý tổng hợp từ đồ thị (lịch sử bệnh nhân + tri thức da liễu); chỉ tham khảo, không phải chẩn đoán */
export interface GraphSuggestions {
  previousConditions: string[];
  previousAdvice: string[];
  candidateDiseases: string[];
  redFlags: string[];
  notes: string[];
}

export interface FinalizeDraft {
  patient: PatientProfile;
  facts: FactDraft[];
  suggestions: GraphSuggestions;
}

export interface FinalizeInput {
  diagnosis: string;
  notes: string;
  isReferenceCase: boolean;
  reasoning: string;
  urgency: Urgency;
  instructions: string[];
  facts: FactDraft[];
  images: { fileId: string; bodySite: string; description: string; confirmedLabel: string | null }[];
}

/* ────────── Clinical Facts ────────── */

export type ClinicalFactType =
  | "symptom"
  | "lesion"
  | "history"
  | "medication"
  | "allergy"
  | "image_finding"
  | "other";

export interface ClinicalFact {
  id: string;
  templateLabel: string;
  factType: ClinicalFactType;
  detail: string;
  status: "active" | "superseded";
  createdAt: string;
  sourceMessageIds?: string[];
  sourceMessages?: SnapshotMessage[];
}

/* ────────── Pre-Consultation Report ────────── */

export interface PreConsultationReport {
  id: string;
  summary: string;
  createdAt: string;
}

/* ────────── Consultation Session ────────── */

export type ConsultationStatus = "pending" | "active" | "resolved";

export interface ConsultationSession {
  id: string;
  conversationId: string;
  conversationTitle: string;
  patient: PatientProfile;
  doctorId: string | null;
  status: ConsultationStatus;
  reason: string;
  requestedAt: string;
  startedAt: string | null;
  resolvedAt: string | null;
  report: PreConsultationReport | null;
  clinicalFacts: ClinicalFact[];
}

/* ────────── Chat Message (read-only cho bác sĩ) ────────── */

export interface DoctorViewMessage {
  id: string;
  conversationId?: string;
  sender: "patient" | "ai" | "doctor";
  content: string;
  messageType: string;
  createdAt: string;
  attachments?: { id: string; name: string; url?: string; contentType?: string }[];
}

/* ────────── Patient Journey Graph ────────── */

export type PatientJourneyNodeType =
  | "Patient"
  | "ConsultationSession"
  | "Symptom"
  | "Condition"
  | "Advice"
  | "Doctor"
  | string;

export type PatientJourneyEdgeType =
  | "HAD_SESSION"
  | "HAS_SYMPTOM"
  | "HAS_CONDITION"
  | "RECEIVED_ADVICE"
  | "NEXT"
  | "CONDUCTED_BY"
  | string;

export interface PatientJourneyNode {
  id: string;
  label: PatientJourneyNodeType;
  name: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  properties: Record<string, any>;
}

export interface PatientJourneyEdge {
  source: string;
  target: string;
  type: PatientJourneyEdgeType;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  properties: Record<string, any>;
}

export interface PatientJourneyGraph {
  patientId: string;
  nodes: PatientJourneyNode[];
  edges: PatientJourneyEdge[];
}
