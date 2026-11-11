"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { usePathname, useRouter } from "next/navigation";
import { CallLayer } from "@/features/video-call";
import { AUTH_STATE_EVENT, areaOfPath, getAccessToken, homePathOf, isLoginPath, loginPathOf } from "@/services/client";

// `next` chỉ nhận đường dẫn nội bộ cùng khu, tránh bị lợi dụng để chuyển hướng ra ngoài
function safeNext(raw: string | null, area: ReturnType<typeof areaOfPath>): string | null {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || isLoginPath(raw.split("?")[0])) return null;
  return areaOfPath(raw) === area ? raw : null;
}

export function AccessGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const area = areaOfPath(pathname);
  const onLoginPage = isLoginPath(pathname);

  const isClient = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );

  // phiên của khu hiện tại; `storage` bắt thay đổi từ tab khác cùng khu, AUTH_STATE_EVENT bắt thay đổi trong tab này
  const subscribe = useCallback((onChange: () => void) => {
    window.addEventListener(AUTH_STATE_EVENT, onChange);
    window.addEventListener("storage", onChange);
    return () => {
      window.removeEventListener(AUTH_STATE_EVENT, onChange);
      window.removeEventListener("storage", onChange);
    };
  }, []);
  const hasToken = useSyncExternalStore(
    subscribe,
    () => Boolean(getAccessToken(area)),
    () => false
  );

  useEffect(() => {
    if (!isClient) return;
    if (!hasToken && !onLoginPage) {
      const here = window.location.pathname + window.location.search;
      router.replace(`${loginPathOf(area)}?next=${encodeURIComponent(here)}`);
    } else if (hasToken && onLoginPage) {
      router.replace(safeNext(new URLSearchParams(window.location.search).get("next"), area) ?? homePathOf(area));
    }
  }, [isClient, hasToken, onLoginPage, area, router]);

  if (!isClient) return null;
  if (onLoginPage) return hasToken ? null : <>{children}</>;
  if (!hasToken) return null;

  return (
    <>
      {children}
      <CallLayer />
    </>
  );
}
