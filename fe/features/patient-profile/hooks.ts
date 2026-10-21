"use client";

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { errorMessage, profileApi } from "./api";
import { useActiveProfileStore } from "./store";
import type { PatientProfileInput } from "./types";

export const qk = {
  profiles: ["patient-profiles"] as const,
  reports: (id: string) => ["patient-profiles", id, "finalize-reports"] as const,
};

export function useProfiles() {
  return useQuery({ queryKey: qk.profiles, queryFn: profileApi.list });
}

export function useFinalizeReports(profileId: string | null) {
  return useQuery({
    queryKey: qk.reports(profileId ?? ""),
    queryFn: () => profileApi.finalizeReports(profileId!),
    enabled: !!profileId,
  });
}

/** Hồ sơ đang chọn; tự về hồ sơ đầu tiên khi id đã lưu không còn (đã xoá, hoặc của tài khoản khác). */
export function useActiveProfile() {
  const { data: profiles } = useProfiles();
  const activeProfileId = useActiveProfileStore((s) => s.activeProfileId);
  const setActiveProfileId = useActiveProfileStore((s) => s.setActiveProfileId);

  useEffect(() => {
    if (!profiles?.length) return;
    if (!profiles.some((p) => p.id === activeProfileId)) setActiveProfileId(profiles[0].id);
  }, [profiles, activeProfileId, setActiveProfileId]);

  return {
    profiles: profiles ?? [],
    activeProfile: profiles?.find((p) => p.id === activeProfileId) ?? null,
    setActiveProfileId,
  };
}

export function useProfileActions() {
  const qc = useQueryClient();
  const onSuccess = () => qc.invalidateQueries({ queryKey: qk.profiles });
  const onError = (e: unknown) => toast.error(errorMessage(e));
  const create = useMutation({ mutationFn: (body: PatientProfileInput) => profileApi.create(body), onSuccess, onError });
  const update = useMutation({
    mutationFn: (v: { id: string; body: Partial<PatientProfileInput> }) => profileApi.update(v.id, v.body),
    onSuccess,
    onError,
  });
  const remove = useMutation({ mutationFn: (id: string) => profileApi.remove(id), onSuccess, onError });
  return { create, update, remove };
}
