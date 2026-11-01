"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface DoctorPrefsState {
  /** ca tư vấn mở gần nhất: mở lại /doctor thì quay về đúng ca đó */
  lastSessionId: string | null;
  setLastSessionId: (id: string | null) => void;
}

// chỉ là lựa chọn UI theo trình duyệt; danh sách ca lấy từ server qua store
export const useDoctorPrefsStore = create<DoctorPrefsState>()(
  persist(
    (set) => ({
      lastSessionId: null,
      setLastSessionId: (lastSessionId) => set({ lastSessionId }),
    }),
    { name: "derma-doctor-prefs" }
  )
);
