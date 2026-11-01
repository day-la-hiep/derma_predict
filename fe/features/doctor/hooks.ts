"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { doctorApi, errorMessage } from "./api";
import type { FinalizeInput } from "./types";

export const qk = {
  finalizeReports: (sessionId: string) => ["doctor", "finalize-reports", sessionId] as const,
  myReportsAll: ["doctor", "my-reports"] as const,
  myReports: (q: string) => ["doctor", "my-reports", q] as const,
  profileReports: (profileId: string) => ["doctor", "profile-reports", profileId] as const,
  finalizeDraft: (sessionId: string) => ["doctor", "finalize-draft", sessionId] as const,
  conversation: (conversationId: string) => ["doctor", "conversation", conversationId] as const,
  patientJourneyGraph: (patientId: string) => ["doctor", "patient-journey-graph", patientId] as const,
};

export function useSessionFinalizeReports(sessionId: string | null) {
  return useQuery({
    queryKey: qk.finalizeReports(sessionId ?? ""),
    queryFn: () => doctorApi.listFinalizeReports(sessionId!),
    enabled: !!sessionId,
  });
}

// Báo cáo kết luận mới phải hiện ở mọi nơi đang xem lịch sử
function useInvalidateReports() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: ["doctor", "finalize-reports"] });
    qc.invalidateQueries({ queryKey: qk.myReportsAll });
    qc.invalidateQueries({ queryKey: ["doctor", "profile-reports"] });
  };
}

export function useMyFinalizeReports(q: string) {
  return useQuery({
    queryKey: qk.myReports(q),
    queryFn: () => doctorApi.listMyFinalizeReports(q),
    placeholderData: (prev) => prev,
  });
}

export function useProfileFinalizeReports(profileId: string | null) {
  return useQuery({
    queryKey: qk.profileReports(profileId ?? ""),
    queryFn: () => doctorApi.listProfileFinalizeReports(profileId!),
    enabled: !!profileId,
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
  const invalidate = useInvalidateReports();
  return useMutation({
    mutationFn: (body: FinalizeInput) => doctorApi.finalizeSession(sessionId, body),
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
