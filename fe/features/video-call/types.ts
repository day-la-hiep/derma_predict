export type CallMode = "audio" | "video";
export type CallPhase = "idle" | "ringing_out" | "ringing_in" | "connecting" | "connected";

export interface ApiVideoCall {
  id: string;
  conversation_id: string;
  doctor_id: string;
  room_id: string;
  status: "pending" | "ongoing" | "ended";
  started_at: string | null;
  ended_at: string | null;
}

export type SignalKind = "offer" | "answer" | "candidate" | "media";

/** Event `call.*` của room SSE (snake_case, nguyên văn từ Core). */
export type CallEvent =
  | { type: "call.ringing"; mode: CallMode; call: ApiVideoCall }
  | { type: "call.accepted"; call: ApiVideoCall }
  | { type: "call.ended"; reason: "ended" | "rejected" | "cancelled" | "missed"; ended_by: string; call: ApiVideoCall }
  | { type: "call.signal"; call_id: string; from: string; kind: SignalKind; payload: Record<string, unknown> };

export interface IceServer {
  urls: string[];
  username?: string;
  credential?: string;
}
