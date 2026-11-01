"use client";

import { useEffect } from "react";
import { endpoints } from "@/services/endpoints";
import { subscribeSse } from "@/services/sse";
import { dispatchCallEvent } from "../callBus";
import { CallOverlay } from "./CallOverlay";

/** Gắn một lần ở cấp app (sau đăng nhập): nghe SSE cuộc gọi của tài khoản và hiện UI cuộc gọi ở mọi trang. */
export function CallLayer() {
  useEffect(() => subscribeSse(endpoints.callsStream, { onData: dispatchCallEvent }), []);
  return <CallOverlay />;
}
