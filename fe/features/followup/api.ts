import axios from "axios";
import { errorMessage } from "@/features/doctor";
import { api } from "@/services/client";
import type { FollowupChannel } from "./types";

export { errorMessage };

export interface UploadedImage {
  storageKey: string;
  fileName: string;
  contentType: string | null;
  size: number | null;
}

/* eslint-disable @typescript-eslint/no-explicit-any */

async function unwrap<T>(p: Promise<{ data: any }>): Promise<T> {
  const res = (await p).data;
  return (res && typeof res === "object" && "data" in res ? res.data : res) as T;
}

function adaptChannel(r: any): FollowupChannel {
  return {
    conversationId: r.conversation_id,
    encounterId: r.encounter_id,
    status: r.status === "open" ? "open" : "read_only",
    followupUntil: r.followup_until ?? null,
    doctorId: r.doctor_id ?? null,
    doctorName: r.doctor_name ?? null,
    patientName: r.patient_name ?? null,
    patientProfileId: r.patient_profile_id ?? null,
    lastMessageAt: r.last_message_at ?? null,
  };
}

export const followupApi = {
  // 404 = lần khám chưa có kênh (không phải lỗi): trả null để UI báo "chưa có"
  async byEncounter(encounterId: string): Promise<FollowupChannel | null> {
    try {
      return adaptChannel(await unwrap<any>(api.get(`/followup-channels/by-encounter/${encodeURIComponent(encounterId)}`)));
    } catch (e) {
      if (axios.isAxiosError(e) && e.response?.status === 404) return null;
      throw e;
    }
  },

  async listDoctor(): Promise<FollowupChannel[]> {
    const raw = await unwrap<any[]>(api.get("/doctor/followup-channels"));
    return Array.isArray(raw) ? raw.map(adaptChannel) : [];
  },

  // POST /uploads trả thẳng FileDto (không bọc `data`); chỉ nhận ảnh JPG/PNG/WebP ≤ 10MB
  async upload(file: File): Promise<UploadedImage> {
    const form = new FormData();
    form.append("file", file);
    // `Content-Type: undefined` để axios tự đặt boundary multipart (client mặc định fix cứng application/json)
    const { data } = await api.post("/uploads", form, { headers: { "Content-Type": undefined } });
    return { storageKey: data.storage_key, fileName: data.file_name, contentType: data.content_type ?? null, size: data.size ?? null };
  },

  async send(conversationId: string, content: string, files: UploadedImage[] = []): Promise<void> {
    await api.post(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      client_message_id: crypto.randomUUID(),
      content,
      attached_files: files.map((f) => ({ storage_key: f.storageKey })),
    });
  },
};
