"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { doctorApi } from "@/features/doctor";
import { errorMessage, followupApi, type UploadedImage } from "./api";

export const qk = {
  byEncounter: (encounterId: string) => ["followup", "encounter", encounterId] as const,
  doctorList: ["followup", "doctor"] as const,
  messages: (conversationId: string) => ["followup", "messages", conversationId] as const,
};

export function useFollowupChannel(encounterId: string | null) {
  return useQuery({
    queryKey: qk.byEncounter(encounterId ?? ""),
    queryFn: () => followupApi.byEncounter(encounterId!),
    enabled: !!encounterId,
  });
}

export function useDoctorFollowups() {
  return useQuery({ queryKey: qk.doctorList, queryFn: followupApi.listDoctor });
}

export function useFollowupMessages(conversationId: string) {
  return useQuery({ queryKey: qk.messages(conversationId), queryFn: () => doctorApi.getMessages(conversationId) });
}

export function useSendFollowupMessage(conversationId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { content: string; files: UploadedImage[] }) => followupApi.send(conversationId, v.content, v.files),
    // tải lại thay vì tự thêm tin: không phụ thuộc việc room có phát lại tin của chính người gửi
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.messages(conversationId) }),
    onError: (e) => toast.error(errorMessage(e)),
  });
}
