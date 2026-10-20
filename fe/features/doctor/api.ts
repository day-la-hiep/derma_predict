/**
 * API client cho module Bác sĩ tư vấn & Báo cáo AI.
 *
 * Tuân thủ quy ước derma-fe-conventions:
 * - Dùng axios instance từ `@/services/client` (đã có gắn sẵn Authorization token).
 * - unwrap response bọc qua `{ data: T }` của FastAPI.
 * - Chỉ dùng Mock Data khi NEXT_PUBLIC_USE_MOCK=true; lỗi thật (401/403/mạng) được ném ra để UI báo.
 */
// adapter nhận payload thô (snake_case từ backend hoặc camelCase từ mock) nên cố ý để `any`
/* eslint-disable @typescript-eslint/no-explicit-any */
import axios from "axios";
import { api } from "@/services/client";
import type {
  ClinicalFact,
  ClinicalFactType,
  ConsultationSession,
  ConsultationStatus,
  DoctorMedicalRecordItem,
  DoctorViewMessage,
  FactOrigin,
  FinalizeDraft,
  FinalizeInput,
  MedicalRecord,
  MedicalRecordSnapshot,
  PatientProfile,
  PreConsultationReport,
  ProfileRelationship,
  SnapshotMessage,
  Urgency,
  PatientJourneyGraph,
} from "./types";
import { MOCK_SESSIONS, MOCK_MESSAGES, getMockPatientJourneyGraph } from "./mockData";

/** Trích xuất thông báo lỗi chuẩn từ FastAPI detail */
export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail))
      return detail.map((d) => d?.msg ?? String(d)).join("; ");
    if (e.code === "ECONNABORTED") return "Quá thời gian chờ phản hồi từ máy chủ.";
    if (!e.response) return "Không thể kết nối đến máy chủ Core API.";
    return `Lỗi HTTP ${e.response.status}`;
  }
  return e instanceof Error ? e.message : "Đã có lỗi không xác định xảy ra.";
}

/** Backend FastAPI bọc mọi kết quả trong `{ data: T }` (`ApiResponse[T]`) */
async function unwrap<T>(p: Promise<{ data: { data?: T } } | { data: T }>): Promise<T> {
  const res = (await p).data;
  if (res && typeof res === "object" && "data" in res) {
    return (res as { data: T }).data;
  }
  return res as T;
}

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";

function adaptPatient(raw: any): PatientProfile {
  return {
    id: raw?.id ?? "",
    fullName: raw?.fullName ?? raw?.full_name ?? "Bệnh nhân",
    dob: raw?.dob ?? "1995-01-01",
    gender: raw?.gender === "female" ? "female" : "male",
    relationship: (raw?.relationship ?? "self") as ProfileRelationship,
    phone: raw?.phone ?? null,
    allergies: raw?.allergies ?? "",
    medicalHistory: raw?.medicalHistory ?? raw?.medical_history ?? "",
  };
}

/** Chuyển đổi dữ liệu từ backend (snake_case) hoặc mock (camelCase) sang kiểu frontend chuẩn */
export function adaptSession(raw: any): ConsultationSession {
  const patient = adaptPatient(raw.patient);

  const rawFacts: any[] = raw.clinicalFacts ?? raw.clinical_facts ?? [];
  const clinicalFacts: ClinicalFact[] = rawFacts.map((f: any) => ({
    id: f.id ?? "",
    templateLabel: f.templateLabel ?? f.template_label ?? "Dữ kiện lâm sàng",
    factType: (f.factType ?? f.fact_type ?? "other") as ClinicalFactType,
    detail: f.detail ?? "",
    status: f.status === "superseded" ? "superseded" : "active",
    createdAt: f.createdAt ?? f.created_at ?? new Date().toISOString(),
  }));

  const report: PreConsultationReport | null = raw.report
    ? {
        id: raw.report.id ?? "",
        summary: raw.report.summary ?? "",
        createdAt: raw.report.createdAt ?? raw.report.created_at ?? new Date().toISOString(),
      }
    : null;

  return {
    id: raw.id,
    conversationId: raw.conversationId ?? raw.conversation_id ?? "",
    conversationTitle: raw.conversationTitle ?? raw.conversation_title ?? "Tư vấn da liễu",
    patient,
    doctorId: raw.doctorId ?? raw.doctor_id ?? null,
    status: (raw.status ?? "pending") as ConsultationStatus,
    reason: raw.reason ?? "",
    requestedAt: raw.requestedAt ?? raw.requested_at ?? new Date().toISOString(),
    startedAt: raw.startedAt ?? raw.started_at ?? null,
    resolvedAt: raw.resolvedAt ?? raw.resolved_at ?? null,
    report,
    clinicalFacts,
  };
}

function adaptSnapshotMessage(raw: any): SnapshotMessage {
  return {
    id: raw?.id ?? "",
    sender: raw?.sender ?? "patient",
    content: raw?.content ?? "",
    createdAt: raw?.created_at ?? null,
    files: (raw?.files ?? []).map((f: any) => ({
      fileName: f.file_name ?? "",
      contentType: f.content_type ?? null,
      url: f.url ?? null,
    })),
  };
}

function adaptSources(provenances: any[] | undefined): SnapshotMessage[] {
  return (provenances ?? []).map((p) => adaptSnapshotMessage(p.message));
}

function adaptSnapshot(raw: any): MedicalRecordSnapshot | null {
  if (!raw) return null;
  const p = adaptPatient(raw.patient_profile);
  return {
    patientProfile: {
      fullName: p.fullName,
      dob: p.dob,
      gender: p.gender,
      relationship: p.relationship,
      phone: p.phone,
      allergies: p.allergies,
      medicalHistory: p.medicalHistory,
    },
    assessment: {
      reasoning: raw.assessment?.reasoning ?? "",
      urgency: (raw.assessment?.urgency ?? "monitor") as Urgency,
      instructions: raw.assessment?.instructions ?? [],
    },
    clinicalFacts: (raw.clinical_facts ?? []).map((f: any) => ({
      factType: (f.fact_type ?? "other") as ClinicalFactType,
      label: f.label ?? "",
      detail: f.detail ?? "",
      origin: (f.origin ?? "doctor_observed") as FactOrigin,
      sources: adaptSources(f.provenances),
    })),
  };
}

function adaptMedicalRecord(raw: any): MedicalRecord {
  return {
    id: raw.id ?? "",
    diagnosis: raw.diagnosis ?? "",
    notes: raw.notes ?? "",
    isReferenceCase: Boolean(raw.isReferenceCase ?? raw.is_reference_case),
    doctorName: raw.doctorName ?? raw.doctor_name ?? null,
    createdAt: raw.createdAt ?? raw.created_at ?? new Date().toISOString(),
    consultationSessionId: raw.consultation_session_id ?? null,
    conversationId: raw.conversation_id ?? null,
    snapshot: adaptSnapshot(raw.snapshot),
  };
}

function adaptMedicalRecordItem(raw: any): DoctorMedicalRecordItem {
  return { ...adaptMedicalRecord(raw), patient: adaptPatient(raw.patient) };
}

function adaptDraft(raw: any): FinalizeDraft {
  return {
    patient: adaptPatient(raw.patient),
    facts: (raw.facts ?? []).map((f: any) => {
      const factType = (f.fact_type ?? "other") as ClinicalFactType;
      return {
        key: f.source_fact_id,
        sourceFactId: f.source_fact_id,
        factType,
        label: f.label ?? "",
        detail: f.detail ?? "",
        original: { label: f.label ?? "", detail: f.detail ?? "", factType, origin: f.origin as FactOrigin },
        sources: adaptSources(f.provenances),
      };
    }),
  };
}

function toFinalizeBody(body: FinalizeInput) {
  return {
    diagnosis: body.diagnosis.trim(),
    notes: body.notes.trim(),
    is_reference_case: body.isReferenceCase,
    reasoning: body.reasoning.trim(),
    urgency: body.urgency,
    instructions: body.instructions.map((i) => i.trim()).filter(Boolean),
    facts: body.facts
      .filter((f) => f.label.trim())
      .map((f) => ({
        source_fact_id: f.sourceFactId,
        fact_type: f.factType,
        label: f.label.trim(),
        detail: f.detail.trim(),
      })),
  };
}

export const doctorApi = {
  /** Lấy danh sách phiên tư vấn */
  async listSessions(): Promise<ConsultationSession[]> {
    if (USE_MOCK) return MOCK_SESSIONS;
    const raw = await unwrap<any[]>(api.get("/doctor/consultations"));
    return Array.isArray(raw) ? raw.map(adaptSession) : [];
  },

  /** Lấy chi tiết một phiên tư vấn (kèm dữ kiện lâm sàng và báo cáo AI) */
  async getSession(sessionId: string): Promise<ConsultationSession | null> {
    if (USE_MOCK) {
      return MOCK_SESSIONS.find((s) => s.id === sessionId) ?? null;
    }
    const raw = await unwrap<any>(
      api.get(`/doctor/consultations/${encodeURIComponent(sessionId)}`)
    );
    return raw ? adaptSession(raw) : null;
  },

  /** Lấy lịch sử tin nhắn của cuộc hội thoại */
  async getMessages(conversationId: string): Promise<DoctorViewMessage[]> {
    if (USE_MOCK) {
      return MOCK_MESSAGES[conversationId] ?? [];
    }
    const raw = await unwrap<unknown[]>(
      api.get(`/conversations/${encodeURIComponent(conversationId)}/messages`)
    );
    return raw.map((m) => doctorApi.adaptRoomMessage(m, conversationId));
  },

  /** Chuyển 1 `MessageOutput` (snake_case, từ REST hoặc event room) sang kiểu hiển thị của bác sĩ */
  adaptRoomMessage(raw: unknown, fallbackConversationId: string): DoctorViewMessage {
    const m = raw as {
      id: string;
      conversation_id?: string;
      sender: "patient" | "ai" | "doctor";
      content?: string;
      created_at?: string;
      metadata?: {
        message_type?: string | null;
        attached_files?: Array<{
          storage_key: string;
          file_name: string;
          content_type?: string | null;
          url?: string | null;
        }> | null;
      } | null;
    };
    return {
      id: m.id,
      conversationId: m.conversation_id ?? fallbackConversationId,
      sender: m.sender,
      messageType: m.metadata?.message_type ?? "text",
      content: m.content ?? "",
      createdAt: m.created_at ?? new Date().toISOString(),
      attachments: m.metadata?.attached_files?.map((f) => ({
        id: f.storage_key,
        name: f.file_name,
        url: f.url ?? undefined,
        contentType: f.content_type ?? undefined,
      })),
    };
  },

  /** Bác sĩ nhận tiếp quản ca tư vấn */
  async acceptSession(sessionId: string): Promise<ConsultationSession | null> {
    if (USE_MOCK) return null;
    const raw = await unwrap<Record<string, unknown>>(
      api.post(`/doctor/consultations/${encodeURIComponent(sessionId)}/accept`)
    );
    return raw ? adaptSession(raw) : null;
  },

  /** Bác sĩ hoàn thành & đóng phiên tư vấn */
  async resolveSession(sessionId: string): Promise<ConsultationSession | null> {
    if (USE_MOCK) return null;
    const raw = await unwrap<Record<string, unknown>>(
      api.post(`/doctor/consultations/${encodeURIComponent(sessionId)}/resolve`)
    );
    return raw ? adaptSession(raw) : null;
  },

  /** Bác sĩ gửi tin nhắn phản hồi tới bệnh nhân */
  async sendDoctorMessage(
    sessionId: string,
    conversationId: string,
    content: string
  ): Promise<DoctorViewMessage> {
    const fallbackMessage: DoctorViewMessage = {
      id: `msg-doc-${Date.now()}`,
      conversationId,
      sender: "doctor",
      messageType: "text",
      content,
      createdAt: new Date().toISOString(),
    };

    if (USE_MOCK) return fallbackMessage;

    const res = await unwrap<{
      id: string;
      conversation_id?: string;
      content: string;
      created_at?: string;
    }>(
      api.post(`/doctor/consultations/${encodeURIComponent(sessionId)}/reply`, {
        content,
      })
    );
    return {
      id: res.id,
      conversationId: res.conversation_id ?? conversationId,
      sender: "doctor",
      messageType: "text",
      content: res.content,
      createdAt: res.created_at ?? new Date().toISOString(),
    };
  },

  /** Lịch sử bệnh án của bệnh nhân thuộc phiên này (mọi lần khám) */
  async listMedicalRecords(sessionId: string): Promise<MedicalRecord[]> {
    if (USE_MOCK) return [];
    const raw = await unwrap<any[]>(
      api.get(`/doctor/consultations/${encodeURIComponent(sessionId)}/medical-records`)
    );
    return Array.isArray(raw) ? raw.map(adaptMedicalRecord) : [];
  },

  /** Dữ liệu điền sẵn form chốt: hồ sơ + dữ kiện đang hiệu lực kèm tin nguồn */
  async getFinalizeDraft(sessionId: string): Promise<FinalizeDraft> {
    const raw = await unwrap<any>(api.get(`/doctor/consultations/${encodeURIComponent(sessionId)}/finalize-draft`));
    return adaptDraft(raw);
  },

  /** Chốt bệnh án cho ca đang tư vấn và đóng ca (một giao dịch) */
  async finalizeSession(sessionId: string, body: FinalizeInput): Promise<MedicalRecord> {
    const raw = await unwrap<any>(
      api.post(`/doctor/consultations/${encodeURIComponent(sessionId)}/finalize`, toFinalizeBody(body))
    );
    return adaptMedicalRecord(raw);
  },

  /** Lịch sử khám: bệnh án do chính bác sĩ đang đăng nhập chốt */
  async listMyMedicalRecords(q: string): Promise<DoctorMedicalRecordItem[]> {
    if (USE_MOCK) return [];
    const raw = await unwrap<any[]>(api.get("/doctor/medical-records", { params: q ? { q } : undefined }));
    return Array.isArray(raw) ? raw.map(adaptMedicalRecordItem) : [];
  },

  /** Ghi bệnh án cho ca khám trực tiếp (chọn hồ sơ bệnh nhân, không qua ca tư vấn) */
  async createMedicalRecordForProfile(
    patientProfileId: string,
    body: FinalizeInput
  ): Promise<DoctorMedicalRecordItem> {
    const raw = await unwrap<any>(
      api.post("/doctor/medical-records", { patient_profile_id: patientProfileId, ...toFinalizeBody(body) })
    );
    return adaptMedicalRecordItem(raw);
  },

  async searchPatientProfiles(q: string): Promise<PatientProfile[]> {
    if (USE_MOCK) return MOCK_SESSIONS.map((s) => s.patient);
    const raw = await unwrap<any[]>(api.get("/doctor/patient-profiles", { params: q ? { q } : undefined }));
    return Array.isArray(raw) ? raw.map(adaptPatient) : [];
  },

  /** Toàn bộ lịch sử khám của một bệnh nhân (mọi bác sĩ) */
  async listProfileMedicalRecords(profileId: string): Promise<MedicalRecord[]> {
    if (USE_MOCK) return [];
    const raw = await unwrap<any[]>(
      api.get(`/doctor/patient-profiles/${encodeURIComponent(profileId)}/medical-records`)
    );
    return Array.isArray(raw) ? raw.map(adaptMedicalRecord) : [];
  },

  /** Bệnh nhân gửi yêu cầu bác sĩ tư vấn & AI tự động bóc tách dữ kiện sinh báo cáo */
  async requestConsultation(
    conversationId: string,
    reason: string = "Bệnh nhân yêu cầu bác sĩ tư vấn"
  ): Promise<ConsultationSession> {
    const raw = await unwrap<any>(
      api.post(`/conversations/${encodeURIComponent(conversationId)}/request-consultation`, {
        reason,
      })
    );
    return adaptSession(raw);
  },

  /** Lấy đồ thị hành trình bệnh nhân (Personal Knowledge Graph qua các phiên) */
  async getPatientJourneyGraph(patientId: string): Promise<PatientJourneyGraph> {
    if (USE_MOCK) {
      return getMockPatientJourneyGraph(patientId);
    }
    const raw = await unwrap<any>(
      api.get(`/doctor/patient-profiles/${encodeURIComponent(patientId)}/journey-graph`)
    );
    return {
      patientId: raw?.patient_id ?? patientId,
      nodes: Array.isArray(raw?.nodes)
        ? raw.nodes.map((n: any) => ({
            id: String(n.id),
            label: String(n.label),
            name: String(n.name ?? ""),
            properties: n.properties ?? {},
          }))
        : [],
      edges: Array.isArray(raw?.edges)
        ? raw.edges.map((e: any) => ({
            source: String(e.source),
            target: String(e.target),
            type: String(e.type),
            properties: e.properties ?? {},
          }))
        : [],
    };
  },
};
