"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useDoctorStore } from "../store";
import { useDoctorPrefsStore } from "../prefs";
import { doctorPaths, parseDoctorRoute } from "../routes";
import { SessionList } from "./SessionList";
import { ChatViewer } from "./ChatViewer";
import { ReportPanel } from "./ReportPanel";

export function DoctorConsultationPage() {
  const router = useRouter();
  const routeKey = usePathname();
  const route = parseDoctorRoute(routeKey);

  const init = useDoctorStore((s) => s.init);
  const dispose = useDoctorStore((s) => s.dispose);
  const loaded = useDoctorStore((s) => s.loaded);

  useEffect(() => {
    void init();
    return dispose;
  }, [init, dispose]);

  // /doctor chỉ là cổng vào: mở ca đã nhớ, không có thì ca đầu theo bộ lọc
  useEffect(() => {
    if (route.kind !== "entry" || !loaded) return;
    const { sessions, statusFilter } = useDoctorStore.getState();
    const remembered = useDoctorPrefsStore.getState().lastSessionId;
    const target =
      sessions.find((s) => s.id === remembered) ??
      sessions.find((s) => statusFilter === "all" || s.status === statusFilter) ??
      sessions[0];
    if (target) router.replace(doctorPaths.session(target.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy lại khi đổi route / danh sách sẵn sàng
  }, [routeKey, loaded]);

  // URL -> store: mở đúng ca (và room của nó), nhớ ca này
  useEffect(() => {
    if (route.kind !== "session" || !loaded) return;
    const state = useDoctorStore.getState();
    if (!state.sessions.some((s) => s.id === route.id)) {
      router.replace(doctorPaths.entry); // ca không còn / không thuộc bác sĩ này
      return;
    }
    useDoctorPrefsStore.getState().setLastSessionId(route.id);
    if (state.activeSessionId !== route.id) void state.selectSession(route.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy lại khi đổi route / danh sách sẵn sàng
  }, [routeKey, loaded]);

  return (
    <div className="flex h-full w-full overflow-hidden bg-background">
      {/* Left Panel — Session List */}
      <aside className="hidden w-72 shrink-0 flex-col border-r border-border bg-sidebar/70 backdrop-blur-md xl:flex 2xl:w-80">
        <SessionList />
      </aside>

      {/* Center Panel — Chat Viewer */}
      <div className="flex min-w-0 flex-1 flex-col border-r border-border bg-background">
        <ChatViewer />
      </div>

      {/* Right Panel — AI Report */}
      <aside className="hidden w-80 shrink-0 flex-col bg-sidebar/50 backdrop-blur-md xl:flex 2xl:w-96">
        <ReportPanel />
      </aside>
    </div>
  );
}
