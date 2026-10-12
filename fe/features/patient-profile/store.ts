"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ActiveProfileState {
  activeProfileId: string | null;
  setActiveProfileId: (id: string | null) => void;
}

// Chỉ là lựa chọn UI (hồ sơ cho hội thoại mới); danh sách hồ sơ lấy từ server qua `hooks.ts`
export const useActiveProfileStore = create<ActiveProfileState>()(
  persist(
    (set) => ({
      activeProfileId: null,
      setActiveProfileId: (activeProfileId) => set({ activeProfileId }),
    }),
    { name: "derma-active-profile" }
  )
);

export function getActiveProfileId(): string | null {
  return useActiveProfileStore.getState().activeProfileId;
}
