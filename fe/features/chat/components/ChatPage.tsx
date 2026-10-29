"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { useChatStore } from "../store";
import { chatPaths, parseChatRoute } from "../routes";
import { ChatSidebar } from "./ChatSidebar";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { QuestionModal } from "./QuestionModal";
import { ProfileView } from "@/features/patient-profile/components/ProfileView";
import { useActiveProfile, useProfiles } from "@/features/patient-profile/hooks";
import { useActiveProfileStore } from "@/features/patient-profile/store";
import { SidebarProvider } from "@/components/ui/sidebar";

export function ChatPage() {
  const router = useRouter();
  const routeKey = usePathname();
  const route = parseChatRoute(routeKey);
  const view = route.kind === "profiles" ? "profile" : "chat";

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const activeId = useChatStore((s) => s.activeId);
  const initialized = useChatStore((s) => s.initialized);
  const messages = useChatStore(
    (s) => (activeId ? s.messagesByConversation[activeId] : undefined)
  );
  const loadingMessages = useChatStore((s) => s.loadingMessages);
  const selectConversation = useChatStore((s) => s.selectConversation);
  const startNewChat = useChatStore((s) => s.startNewChat);

  const { isLoading: profilesLoading } = useProfiles();
  const { profiles, activeProfile, setActiveProfileId } = useActiveProfile();
  const rememberConversation = useActiveProfileStore((s) => s.rememberConversation);

  const profilesReady = !profilesLoading && (profiles.length === 0 || !!activeProfile);

  // /chats chỉ là cổng vào: tới đoạn chat đã nhớ của hồ sơ đang chọn, không có thì trang "mới" của hồ sơ đó
  // (cũng bổ sung hồ sơ cho /chats/new thiếu hồ sơ)
  useEffect(() => {
    const needsProfile = route.kind === "new" && !route.profileId;
    if ((route.kind !== "entry" && !needsProfile) || !initialized || !profilesReady) return;
    if (!activeProfile) {
      router.replace(chatPaths.profiles); // chưa có hồ sơ nào: tạo hồ sơ trước
      return;
    }
    if (needsProfile) {
      router.replace(chatPaths.new(activeProfile.id));
      return;
    }
    const { conversations } = useChatStore.getState();
    const remembered = useActiveProfileStore.getState().lastConversationByProfile[activeProfile.id];
    const target = conversations.find((c) => c.id === remembered && (!c.patientProfileId || c.patientProfileId === activeProfile.id));
    router.replace(target ? chatPaths.conversation(target.id) : chatPaths.new(activeProfile.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy lại khi đổi route / dữ liệu nền sẵn sàng
  }, [routeKey, initialized, profilesReady, activeProfile?.id]);

  // URL -> store: "new" mang hồ sơ trên URL; hội thoại mang hồ sơ của chính nó. Mở đúng hội thoại / trạng thái "mới", nhớ đoạn chat cho hồ sơ
  useEffect(() => {
    if (!initialized || !profilesReady) return;
    const state = useChatStore.getState();
    if (route.kind === "new") {
      if (!route.profileId) return; // đã có effect bổ sung hồ sơ ở trên
      if (!profiles.some((p) => p.id === route.profileId)) {
        router.replace(chatPaths.entry); // hồ sơ trên URL không còn / không thuộc tài khoản này
        return;
      }
      if (useActiveProfileStore.getState().activeProfileId !== route.profileId) setActiveProfileId(route.profileId);
      if (state.activeId !== null) startNewChat();
      return;
    }
    if (route.kind !== "conversation") return;
    const conversation = state.conversations.find((c) => c.id === route.id);
    if (!conversation) {
      // id không còn / không thuộc tài khoản này: về cổng vào để chọn lại
      router.replace(chatPaths.entry);
      return;
    }
    if (conversation.patientProfileId) {
      if (useActiveProfileStore.getState().activeProfileId !== conversation.patientProfileId) setActiveProfileId(conversation.patientProfileId);
      rememberConversation(conversation.patientProfileId, conversation.id);
    }
    if (state.activeId !== route.id) void selectConversation(route.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy lại khi đổi route / dữ liệu nền sẵn sàng
  }, [routeKey, initialized, profilesReady]);

  // store -> URL: gửi tin đầu tiên ở "hội thoại mới" tạo record thật (activeId từ rỗng thành có), thay /chats/new/<hồ sơ> bằng /chats/<id> (không thêm lịch sử)
  const prevActiveId = useRef(activeId);
  useEffect(() => {
    const was = prevActiveId.current;
    prevActiveId.current = activeId;
    if (route.kind === "new" && was === null && activeId) router.replace(chatPaths.conversation(activeId));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ phản ứng khi activeId đổi
  }, [activeId]);

  // hội thoại mới dùng hồ sơ trên URL, không có thì hồ sơ đang chọn
  const newChatProfileId = (route.kind === "new" && route.profileId) || activeProfile?.id;
  const goNew = (profileId?: string) => router.push(profileId ? chatPaths.new(profileId) : chatPaths.entry);

  // đang mở hội thoại theo URL mà store chưa chuyển sang (lần tải đầu, hoặc vừa bấm): chưa vẽ nội dung cũ
  const syncing = route.kind === "entry" || (route.kind === "conversation" && activeId !== route.id);

  return (
    <SidebarProvider open={!sidebarCollapsed} onOpenChange={(open) => setSidebarCollapsed(!open)} className="min-h-dvh flex-row">
      <div className="flex h-dvh w-full overflow-hidden bg-background">
        <ChatSidebar
          open={sidebarOpen}
          collapsed={sidebarCollapsed}
          activeView={view}
          onClose={() => setSidebarOpen(false)}
          onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
          onOpenProfile={() => {
            router.push(chatPaths.profiles);
            setSidebarOpen(false);
          }}
          onNewChat={() => goNew(newChatProfileId)}
          onSelectConversation={(id) => router.push(chatPaths.conversation(id))}
          onSwitchProfile={(profileId) => goNew(profileId)}
        />

        <div className="flex min-w-0 flex-1 flex-col bg-background">
          {view === "profile" ? (
            <ProfileView onBack={() => router.push(chatPaths.entry)} />
          ) : syncing ? (
            <div className="flex-1" aria-busy="true" />
          ) : (
            <>
              <ChatHeader onOpenSidebar={() => setSidebarOpen(true)} />
              <main className="flex flex-1 flex-col overflow-hidden bg-background">
                <div className="flex flex-1 flex-col overflow-y-auto bg-background">
                  <MessageList
                    conversationId={activeId ?? ""}
                    messages={messages ?? []}
                    loading={loadingMessages}
                  />
                </div>
                <div className="relative bg-background">
                  {activeId && <QuestionModal conversationId={activeId} />}
                  <ChatInput
                    conversationId={activeId ?? undefined}
                    onOpenSidebar={() => setSidebarOpen(true)}
                  />
                </div>
              </main>
            </>
          )}
        </div>
      </div>
    </SidebarProvider>
  );
}
