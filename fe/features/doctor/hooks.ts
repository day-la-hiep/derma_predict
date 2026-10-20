"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { doctorApi, errorMessage } from "./api";
import type { FinalizeInput } from "./types";

export const qk = {
  medicalRecords: (sessionId: string) => ["doctor", "medical-records", sessionId] as const,
  myRecordsAll: ["doctor", "my-records"] as const,
  myRecords: (q: string) => ["doctor", "my-records", q] as const,
  profileRecords: (profileId: string) => ["doctor", "profile-records", profileId] as const,
  patientSearch: (q: string) => ["doctor", "patient-search", q] as const,
  finalizeDraft: (sessionId: string) => ["doctor", "finalize-draft", sessionId] as const,
  conversation: (conversationId: string) => ["doctor", "conversation", conversationId] as const,
  patientJourneyGraph: (patientId: string) => ["doctor", "patient-journey-graph", patientId] as const,
};

export function useSessionMedicalRecords(sessionId: string | null) {
  return useQuery({
    queryKey: qk.medicalRecords(sessionId ?? ""),
    queryFn: () => doctorApi.listMedicalRecords(sessionId!),
    enabled: !!sessionId,
  });
}

// Bệnh án mới (từ ca tư vấn hay khám trực tiếp) phải hiện ở mọi nơi đang xem lịch sử
function useInvalidateRecords() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["doctor", "medical-records"] });
    qc.invalidateQueries({ queryKey: qk.myRecordsAll });
    qc.invalidateQueries({ queryKey: ["doctor", "profile-records"] });
  };
}

export function useMyMedicalRecords(q: string) {
  return useQuery({
    queryKey: qk.myRecords(q),
    queryFn: () => doctorApi.listMyMedicalRecords(q),
    placeholderData: (prev) => prev,
  });
}

export function useProfileMedicalRecords(profileId: string | null) {
  return useQuery({
    queryKey: qk.profileRecords(profileId ?? ""),
    queryFn: () => doctorApi.listProfileMedicalRecords(profileId!),
    enabled: !!profileId,
  });
}

export function usePatientSearch(q: string, enabled: boolean) {
  return useQuery({
    queryKey: qk.patientSearch(q),
    queryFn: () => doctorApi.searchPatientProfiles(q),
    enabled,
    placeholderData: (prev) => prev,
  });
}

export function useFinalizeDraft(sessionId: string | null) {
  return useQuery({
    queryKey: qk.finalizeDraft(sessionId ?? ""),
    queryFn: () => doctorApi.getFinalizeDraft(sessionId!),
    enabled: !!sessionId,
    // dữ kiện có thể vừa đổi trong ca; mỗi lần mở form lấy bản mới
    staleTime: 0,
    gcTime: 0,
  });
}

export function useFinalizeSession(sessionId: string) {
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: (body: FinalizeInput) => doctorApi.finalizeSession(sessionId, body),
    onSuccess: invalidate,
    onError: (e) => toast.error(errorMessage(e)),
  });
}

export function useCreateMedicalRecordForProfile() {
  const invalidate = useInvalidateRecords();
  return useMutation({
    mutationFn: ({ patientProfileId, body }: { patientProfileId: string; body: FinalizeInput }) =>
      doctorApi.createMedicalRecordForProfile(patientProfileId, body),
    onSuccess: invalidate,
    onError: (e) => toast.error(errorMessage(e)),
  });
}

export function useConversationMessages(conversationId: string | null) {
  return useQuery({
    queryKey: qk.conversation(conversationId ?? ""),
    queryFn: () => doctorApi.getMessages(conversationId!),
    enabled: !!conversationId,
  });
}

export function usePatientJourneyGraph(patientId: string | null) {
  return useQuery({
    queryKey: qk.patientJourneyGraph(patientId ?? ""),
    queryFn: () => doctorApi.getPatientJourneyGraph(patientId!),
    enabled: !!patientId,
  });
}
