import axios from "axios";
import { api } from "@/services/client";
import type { MedicalRecord, PatientProfile, PatientProfileInput } from "./types";

/** Thông báo lỗi hiển thị cho người dùng: ưu tiên `detail` của FastAPI. */
export function errorMessage(e: unknown): string {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
    if (!e.response) return "Không kết nối được máy chủ.";
    return `Lỗi ${e.response.status}`;
  }
  return e instanceof Error ? e.message : "Đã có lỗi xảy ra.";
}

async function unwrap<T>(p: Promise<{ data: { data: T } }>): Promise<T> {
  return (await p).data.data;
}

const root = "/patient-profiles";
const one = (id: string) => `${root}/${encodeURIComponent(id)}`;

export const profileApi = {
  list: () => unwrap<PatientProfile[]>(api.get(root)),
  create: (body: PatientProfileInput) => unwrap<PatientProfile>(api.post(root, body)),
  update: (id: string, body: Partial<PatientProfileInput>) => unwrap<PatientProfile>(api.patch(one(id), body)),
  remove: async (id: string) => {
    await api.delete(one(id));
  },
  medicalRecords: (id: string) => unwrap<MedicalRecord[]>(api.get(`${one(id)}/medical-records`)),
};
