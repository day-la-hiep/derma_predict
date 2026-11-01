"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ActiveProfileState {
  activeProfileId: string | null;
  setActiveProfileId: (id: string | null) => void;
  /** hội thoại mở gần nhất của từng hồ sơ: mở lại `/chats` hoặc đổi hồ sơ thì quay về đúng đoạn chat đó */
  lastConversationByProfile: Record<string, string>;
  rememberConversation: (profileId: string, conversationId: string) => void;
}

// Chỉ là lựa chọn UI (hồ sơ cho hội thoại mới); danh sách hồ sơ lấy từ server qua `hooks.ts`
export const useActiveProfileStore = create<ActiveProfileState>()(
  persist(
    (set) => ({
      activeProfileId: null,
      setActiveProfileId: (activeProfileId) => set({ activeProfileId }),
      lastConversationByProfile: {},
      rememberConversation: (profileId, conversationId) =>
        set((s) =>
          s.lastConversationByProfile[profileId] === conversationId
            ? s
            : { lastConversationByProfile: { ...s.lastConversationByProfile, [profileId]: conversationId } }
        ),
    }),
    { name: "derma-active-profile" }
  )
);

export function getActiveProfileId(): string | null {
  return useActiveProfileStore.getState().activeProfileId;
}
