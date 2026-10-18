"use client";

import { useState } from "react";
import { useChatStore } from "../store";
import { ChatSidebar } from "./ChatSidebar";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { QuestionModal } from "./QuestionModal";
import { ProfileView } from "@/features/patient-profile/components/ProfileView";
import { SidebarProvider } from "@/components/ui/sidebar";

type MainView = "chat" | "profile";

export function ChatPage() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  // "profile": khu nội dung chính hiện màn Hồ sơ thay cho khung chat (không phải modal)
  const [view, setView] = useState<MainView>("chat");

  const activeId = useChatStore((s) => s.activeId);
  const messages = useChatStore(
    (s) => (activeId ? s.messagesByConversation[activeId] : undefined)
  );
  const loadingMessages = useChatStore((s) => s.loadingMessages);
  const selectConversation = useChatStore((s) => s.selectConversation);
  const startNewChat = useChatStore((s) => s.startNewChat);

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
            setView("profile");
            setSidebarOpen(false);
          }}
          onNewChat={() => {
            setView("chat");
            startNewChat();
          }}
          onSelectConversation={(id) => {
            setView("chat");
            void selectConversation(id);
          }}
        />

        <div className="flex min-w-0 flex-1 flex-col bg-background">
          {view === "profile" ? (
            <ProfileView onBack={() => setView("chat")} />
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
