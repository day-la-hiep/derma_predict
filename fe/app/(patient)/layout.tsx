import { ChatPage } from "@/features/chat/components/ChatPage";

// nhóm (patient) không vào URL; layout giữ nguyên khi đổi giữa /chats/* và /profile nên sidebar và SSE không bị dựng lại
export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <ChatPage />
    </>
  );
}
