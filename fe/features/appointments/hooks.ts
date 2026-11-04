"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import type { FinalizeInput } from "@/features/doctor";
import { appointmentApi, errorMessage } from "./api";

export const qk = {
  episodes: (profileId: string) => ["appointments", "episodes", profileId] as const,
  mine: ["appointments", "mine"] as const,
  doctorList: ["appointments", "doctor"] as const,
  detail: (id: string) => ["appointments", "detail", id] as const,
  draft: (encounterId: string) => ["appointments", "draft", encounterId] as const,
};

function useRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["appointments"] });
}

export function usePatientEpisodes(profileId: string | null) {
  return useQuery({
    queryKey: qk.episodes(profileId ?? ""),
    queryFn: () => appointmentApi.listEpisodes(profileId!),
    enabled: !!profileId,
  });
}

export function useMyAppointments() {
  return useQuery({ queryKey: qk.mine, queryFn: appointmentApi.listMine });
}

export function useBookAppointment() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: appointmentApi.book,
    onSuccess: () => {
      toast.success("Đã gửi yêu cầu đặt lịch");
      refresh();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

export function useCancelMyAppointment() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => appointmentApi.cancelMine(id, reason),
    onSuccess: refresh,
    onError: (e) => toast.error(errorMessage(e)),
  });
}

export function useDoctorAppointments() {
  return useQuery({ queryKey: qk.doctorList, queryFn: appointmentApi.listDoctor });
}

export function useDoctorAppointment(id: string | null) {
  return useQuery({ queryKey: qk.detail(id ?? ""), queryFn: () => appointmentApi.detail(id!), enabled: !!id });
}

type Act =
  | { kind: "confirm" | "no-show" | "start" }
  | { kind: "cancel"; reason: string }
  | { kind: "change"; episodeId: string };

export function useAppointmentAction(id: string) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (a: Act) =>
      a.kind === "cancel"
        ? appointmentApi.cancelDoctor(id, a.reason)
        : a.kind === "change"
          ? appointmentApi.changeEpisode(id, a.episodeId)
          : appointmentApi.action(id, a.kind),
    onSuccess: refresh,
    onError: (e) => toast.error(errorMessage(e)),
  });
}

export function useEncounterDraft(encounterId: string | null) {
  return useQuery({
    queryKey: qk.draft(encounterId ?? ""),
    queryFn: () => appointmentApi.encounterDraft(encounterId!),
    enabled: !!encounterId,
    staleTime: 0,
    gcTime: 0,
  });
}

export function useFinalizeEncounter(encounterId: string) {
  const qc = useQueryClient();
  const refresh = useRefresh();
  return useMutation({
    mutationFn: (v: { body: FinalizeInput; diagnosisCode: string }) =>
      appointmentApi.finalizeEncounter(encounterId, v.body, v.diagnosisCode),
    onSuccess: () => {
      refresh();
      qc.invalidateQueries({ queryKey: ["doctor"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
