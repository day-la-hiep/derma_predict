"use client";

import { useQuery } from "@tanstack/react-query";
import { doctorApi } from "./api";

export const qk = {
  myReportsAll: ["doctor", "my-reports"] as const,
  myReports: (q: string) => ["doctor", "my-reports", q] as const,
  profileReports: (profileId: string) => ["doctor", "profile-reports", profileId] as const,
  patientJourneyGraph: (patientId: string) => ["doctor", "patient-journey-graph", patientId] as const,
};

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

export function usePatientJourneyGraph(patientId: string | null) {
  return useQuery({
    queryKey: qk.patientJourneyGraph(patientId ?? ""),
    queryFn: () => doctorApi.getPatientJourneyGraph(patientId!),
    enabled: !!patientId,
  });
}
