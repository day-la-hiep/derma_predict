import { adaptDraft, adaptFinalizeReport, adaptPatient, errorMessage, toFinalizeBody } from "@/features/doctor";
import type { ClinicalFact, FinalizeInput, FinalizeReport } from "@/features/doctor";
import { api } from "@/services/client";
import type {
  Appointment,
  DoctorAppointment,
  DoctorAppointmentDetail,
  DoctorEpisode,
  EncounterDraft,
  ImagePrediction,
  PatientEpisode,
} from "./types";

export { errorMessage };

/* eslint-disable @typescript-eslint/no-explicit-any */

async function unwrap<T>(p: Promise<{ data: any }>): Promise<T> {
  const res = (await p).data;
  return (res && typeof res === "object" && "data" in res ? res.data : res) as T;
}

function adaptAppointment(r: any): Appointment {
  return {
    id: r.id,
    patientProfileId: r.patient_profile_id,
    episodeId: r.episode_id,
    bodySite: r.body_site,
    bodySiteLabel: r.body_site_label,
    doctorId: r.doctor_id ?? null,
    doctorName: r.doctor_name ?? null,
    scheduledAt: r.scheduled_at,
    status: r.status,
    reason: r.reason ?? "",
    cancelReason: r.cancel_reason ?? null,
    createdAt: r.created_at,
    encounterId: r.encounter_id ?? null,
  };
}

function adaptPatientEpisode(r: any): PatientEpisode {
  return {
    id: r.id,
    bodySite: r.body_site,
    bodySiteLabel: r.body_site_label,
    status: r.status,
    updatedAt: r.updated_at,
    facts: r.facts ?? [],
    bookable: r.bookable,
    notBookableReason: r.not_bookable_reason ?? null,
    appointment: r.appointment ? adaptAppointment(r.appointment) : null,
  };
}

function adaptFact(f: any): ClinicalFact {
  return {
    id: f.id,
    templateLabel: f.template_label,
    factType: f.fact_type,
    detail: f.detail ?? "",
    verifiedAt: f.verified_at ?? null,
    createdAt: f.created_at,
    updatedAt: f.updated_at ?? null,
  };
}

function adaptImages(list: any[] | undefined): ImagePrediction[] {
  return (list ?? []).map((p) => ({
    fileId: p.file_id,
    url: p.file?.url ?? null,
    fileName: p.file?.file_name ?? "",
    topK: (p.top_k ?? []).map((t: any) => ({ label: t.label, labelName: t.label_name, score: t.score })),
  }));
}

function adaptEpisode(e: any): DoctorEpisode {
  return {
    id: e.id,
    bodySite: e.body_site,
    bodySiteLabel: e.body_site_label,
    status: e.status,
    summary: e.summary ?? "",
    urgency: e.urgency ?? null,
    redFlags: e.red_flags ?? [],
    hypotheses: (e.hypotheses ?? []).map((h: any) => ({
      rank: h.rank,
      diagnosisCode: h.diagnosis_code,
      diagnosisLabel: h.diagnosis_label,
      disease: h.disease,
      confidence: h.confidence,
      evidence: (h.evidence ?? []).map((e: any) => ({
        source: e.source ?? "",
        text: e.text ?? "",
        ref: e.ref?.document_id
          ? { documentId: e.ref.document_id, chunkId: e.ref.chunk_id ?? null, pageStart: e.ref.page_start ?? null, pageEnd: e.ref.page_end ?? null }
          : null,
      })),
      missing: h.missing ?? [],
    })),
    hypothesesLocked: e.hypotheses_locked,
    facts: (e.facts ?? []).map(adaptFact),
    imagePredictions: adaptImages(e.image_predictions),
    updatedAt: e.updated_at,
    disclaimer: e.disclaimer,
  };
}

function adaptDoctorItem(r: any): DoctorAppointment {
  return { ...adaptAppointment(r), patient: adaptPatient(r.patient), topHypothesis: r.top_hypothesis ?? null };
}

function adaptDetail(r: any): DoctorAppointmentDetail {
  return {
    ...adaptDoctorItem(r),
    episode: adaptEpisode(r.episode),
    longTermFacts: (r.long_term_facts ?? []).map(adaptFact),
    otherEpisodes: (r.other_episodes ?? []).map(adaptPatientEpisode),
  };
}

const enc = encodeURIComponent;

export const appointmentApi = {
  async listEpisodes(profileId: string): Promise<PatientEpisode[]> {
    return (await unwrap<any[]>(api.get(`/patient-profiles/${enc(profileId)}/episodes`))).map(adaptPatientEpisode);
  },
  async book(body: { profileId: string; episodeId: string; scheduledAt: string; reason: string }): Promise<Appointment> {
    const r = await unwrap<any>(
      api.post("/appointments", {
        patient_profile_id: body.profileId,
        episode_id: body.episodeId,
        scheduled_at: body.scheduledAt,
        reason: body.reason,
      })
    );
    return adaptAppointment(r);
  },
  async listMine(): Promise<Appointment[]> {
    return (await unwrap<any[]>(api.get("/appointments"))).map(adaptAppointment);
  },
  async cancelMine(id: string, reason: string): Promise<Appointment> {
    return adaptAppointment(await unwrap<any>(api.post(`/appointments/${enc(id)}/cancel`, { reason })));
  },

  async listDoctor(): Promise<DoctorAppointment[]> {
    return (await unwrap<any[]>(api.get("/doctor/appointments"))).map(adaptDoctorItem);
  },
  async detail(id: string): Promise<DoctorAppointmentDetail> {
    return adaptDetail(await unwrap<any>(api.get(`/doctor/appointments/${enc(id)}`)));
  },
  async action(id: string, action: "confirm" | "no-show" | "start"): Promise<DoctorAppointmentDetail> {
    return adaptDetail(await unwrap<any>(api.post(`/doctor/appointments/${enc(id)}/${action}`)));
  },
  async cancelDoctor(id: string, reason: string): Promise<DoctorAppointmentDetail> {
    return adaptDetail(await unwrap<any>(api.post(`/doctor/appointments/${enc(id)}/cancel`, { reason })));
  },
  async changeEpisode(id: string, episodeId: string): Promise<DoctorAppointmentDetail> {
    return adaptDetail(await unwrap<any>(api.post(`/doctor/appointments/${enc(id)}/change-episode`, { episode_id: episodeId })));
  },
  async encounterDraft(encounterId: string): Promise<EncounterDraft> {
    const r = await unwrap<any>(api.get(`/doctor/encounters/${enc(encounterId)}/finalize-draft`));
    return {
      ...adaptDraft(r),
      encounterId: r.encounter_id,
      appointmentId: r.appointment_id,
      episode: adaptEpisode(r.episode),
      images: adaptImages(r.images),
      diagnosisOptions: r.diagnosis_options ?? [],
    };
  },
  async finalizeEncounter(encounterId: string, body: FinalizeInput, diagnosisCode: string): Promise<FinalizeReport> {
    const r = await unwrap<any>(
      api.post(`/doctor/encounters/${enc(encounterId)}/finalize`, { ...toFinalizeBody(body), diagnosis_code: diagnosisCode })
    );
    return adaptFinalizeReport(r);
  },
};
