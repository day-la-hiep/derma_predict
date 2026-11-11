// adapter nhận payload thô (snake_case từ backend hoặc camelCase từ mock) nên cố ý để `any`
/* eslint-disable @typescript-eslint/no-explicit-any */
import axios from "axios";
import { api } from "@/services/client";
import type {
  ClinicalFactType,
  FinalizeReportItem,
  DoctorViewMessage,
  FactOrigin,
  FinalizeDraft,
  FinalizeInput,
  FinalizeReport,
  FinalizeReportSnapshot,
  PatientProfile,
  ProfileRelationship,
  SnapshotMessage,
  Urgency,
  PatientJourneyGraph,
} from "./types";
import { getMockPatientJourneyGraph } from "./mockData";

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

export function adaptPatient(raw: any): PatientProfile {
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

function adaptSnapshot(raw: any): FinalizeReportSnapshot | null {
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

export function adaptFinalizeReport(raw: any): FinalizeReport {
  return {
    id: raw.id ?? "",
    diagnosis: raw.diagnosis ?? "",
    notes: raw.notes ?? "",
    isReferenceCase: Boolean(raw.isReferenceCase ?? raw.is_reference_case),
    doctorName: raw.doctorName ?? raw.doctor_name ?? null,
    createdAt: raw.createdAt ?? raw.created_at ?? new Date().toISOString(),
    consultationSessionId: raw.consultation_session_id ?? null,
    conversationId: raw.conversation_id ?? null,
    encounterId: raw.encounter_id ?? null,
    snapshot: adaptSnapshot(raw.snapshot),
  images: (raw.images ?? []).map((img: any) => ({
    id: img.id ?? "",
    file: {
      fileName: img.file?.file_name ?? img.file?.fileName ?? "",
      contentType: img.file?.content_type ?? img.file?.contentType ?? null,
      storageKey: img.file?.storage_key ?? img.file?.storageKey ?? "",
      url: img.file?.url ?? null,
    },
    bodySite: img.body_site ?? img.bodySite ?? "",
    description: img.description ?? "",
    confirmedLabel: img.confirmed_label ?? img.confirmedLabel ?? null,
    capturedAt: img.captured_at ?? img.capturedAt ?? null,
  })),
  };
}

function adaptFinalizeReportItem(raw: any): FinalizeReportItem {
  return { ...adaptFinalizeReport(raw), patient: adaptPatient(raw.patient) };
}

export function adaptDraft(raw: any): FinalizeDraft {
  return {
    patient: adaptPatient(raw.patient),
    suggestions: {
      previousConditions: raw.suggestions?.previous_conditions ?? [],
      previousAdvice: raw.suggestions?.previous_advice ?? [],
      candidateDiseases: raw.suggestions?.candidate_diseases ?? [],
      redFlags: raw.suggestions?.red_flags ?? [],
      notes: raw.suggestions?.notes ?? [],
    },
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

export function toFinalizeBody(body: FinalizeInput) {
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
    images: (body.images ?? []).map((img) => ({
      file_id: img.fileId,
      body_site: img.bodySite,
      description: img.description,
      confirmed_label: img.confirmedLabel,
    })),
  };
}

export const doctorApi = {
  /** Lấy lịch sử tin nhắn của cuộc hội thoại */
  async getMessages(conversationId: string): Promise<DoctorViewMessage[]> {
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

  /** Lịch sử khám: báo cáo kết luận do chính bác sĩ đang đăng nhập chốt */
  async listMyFinalizeReports(q: string): Promise<FinalizeReportItem[]> {
    if (USE_MOCK) return [];
    const raw = await unwrap<any[]>(api.get("/doctor/finalize-reports", { params: q ? { q } : undefined }));
    return Array.isArray(raw) ? raw.map(adaptFinalizeReportItem) : [];
  },

  /** Toàn bộ lịch sử khám của một bệnh nhân (mọi bác sĩ) */
  async listProfileFinalizeReports(profileId: string): Promise<FinalizeReport[]> {
    if (USE_MOCK) return [];
    const raw = await unwrap<any[]>(
      api.get(`/doctor/patient-profiles/${encodeURIComponent(profileId)}/finalize-reports`)
    );
    return Array.isArray(raw) ? raw.map(adaptFinalizeReport) : [];
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
