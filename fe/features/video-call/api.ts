import { api } from "@/services/client";
import { endpoints } from "@/services/endpoints";
import type { ApiVideoCall, CallMode, IceServer, SignalKind } from "./types";

async function unwrap<T>(p: Promise<{ data: { data: T } }>): Promise<T> {
  return (await p).data.data;
}

export const videoCallApi = {
  iceServers: async () =>
    (await unwrap<{ ice_servers: IceServer[] }>(api.get(endpoints.iceConfig))).ice_servers,
  start: (conversationId: string, mode: CallMode) =>
    unwrap<ApiVideoCall>(api.post(endpoints.startCall(conversationId), { mode })),
  accept: (callId: string) => unwrap<ApiVideoCall>(api.post(endpoints.acceptCall(callId))),
  end: (callId: string, reason?: "missed") =>
    unwrap<ApiVideoCall>(api.post(endpoints.endCall(callId), reason ? { reason } : {})),
  signal: (callId: string, kind: SignalKind, payload: unknown) =>
    api.post(endpoints.signalCall(callId), { kind, payload }),
};
