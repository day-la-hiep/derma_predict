"use client";

import { create } from "zustand";
import { toast } from "sonner";
import { getCurrentUserId } from "@/services/client";
import { errorMessage } from "@/features/doctor/api";
import { videoCallApi } from "./api";
import { onCallEvent } from "./callBus";
import type { ApiVideoCall, CallEvent, CallMode, CallPhase, SignalKind } from "./types";

const RING_TIMEOUT_MS = 30_000;
const FALLBACK_ICE: RTCIceServer[] = [{ urls: ["stun:stun.l.google.com:19302"] }];

// Đối tượng WebRTC không đưa vào state Zustand: chúng thay đổi liên tục và không cần render lại UI.
let pc: RTCPeerConnection | null = null;
let local: MediaStream | null = null;
let remote: MediaStream | null = null;
let videoSender: RTCRtpSender | null = null;
let ringTimer: ReturnType<typeof setTimeout> | null = null;
// signal đi qua nhiều POST riêng nên phải gửi tuần tự (offer trước candidate) và đệm candidate tới sớm hơn offer
let sendQueue: Promise<unknown> = Promise.resolve();
let pendingCandidates: RTCIceCandidateInit[] = [];
// perfect negotiation: bên nhận cuộc gọi nhường (polite) khi hai bên cùng gửi offer
let polite = false;
let makingOffer = false;
let ignoreOffer = false;

interface RemoteMedia {
  audio: boolean;
  video: boolean;
}

interface CallState {
  phase: CallPhase;
  call: ApiVideoCall | null;
  mode: CallMode;
  localStream: MediaStream | null;
  remoteStream: MediaStream | null;
  micOn: boolean;
  camOn: boolean;
  /** thu nhỏ cửa sổ cuộc gọi để thao tác phần khác của trang */
  minimized: boolean;
  remoteMedia: RemoteMedia;
  startCall: (conversationId: string, mode: CallMode) => Promise<void>;
  acceptCall: () => Promise<void>;
  endCall: (reason?: "missed") => Promise<void>;
  setMinimized: (minimized: boolean) => void;
  toggleMic: () => void;
  toggleCamera: () => Promise<void>;
}

const IDLE: Pick<CallState, "phase" | "call" | "mode" | "localStream" | "remoteStream" | "micOn" | "camOn" | "remoteMedia" | "minimized"> = {
  phase: "idle",
  call: null,
  mode: "audio",
  localStream: null,
  remoteStream: null,
  micOn: true,
  camOn: false,
  minimized: false,
  remoteMedia: { audio: true, video: false },
};


async function getMedia(video: boolean): Promise<{ stream: MediaStream; video: boolean }> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Trình duyệt không hỗ trợ gọi (cần HTTPS hoặc localhost).");
  }
  try {
    return { stream: await navigator.mediaDevices.getUserMedia({ audio: true, video }), video };
  } catch (e) {
    if (!video) throw e;
    toast.warning("Không mở được camera, chuyển sang gọi thoại.");
    return { stream: await navigator.mediaDevices.getUserMedia({ audio: true }), video: false };
  }
}

function clearRingTimer() {
  if (ringTimer) clearTimeout(ringTimer);
  ringTimer = null;
}

function teardown() {
  clearRingTimer();
  pc?.close();
  pc = null;
  local?.getTracks().forEach((t) => t.stop());
  local = null;
  remote = null;
  videoSender = null;
  makingOffer = false;
  ignoreOffer = false;
  pendingCandidates = [];
  sendQueue = Promise.resolve();
}

export const useCallStore = create<CallState>((set, get) => {
  function send(kind: SignalKind, payload: unknown) {
    const call = get().call;
    if (!call) return;
    sendQueue = sendQueue
      .then(() => videoCallApi.signal(call.id, kind, payload))
      .catch((e) => console.warn("[call] gửi signal lỗi", e));
  }

  function sendMedia() {
    send("media", { audio: get().micOn, video: get().camOn });
  }

  function finish(message?: string) {
    teardown();
    set({ ...IDLE });
    if (message) toast.info(message);
  }

  async function setupPeer() {
    let servers: RTCIceServer[] = FALLBACK_ICE;
    try {
      servers = await videoCallApi.iceServers();
    } catch {
      toast.warning("Không lấy được cấu hình mạng, thử kết nối trực tiếp.");
    }
    const peer = new RTCPeerConnection({ iceServers: servers });
    pc = peer;
    remote = new MediaStream();
    set({ remoteStream: remote });

    peer.ontrack = ({ track }) => {
      if (remote && !remote.getTracks().includes(track)) remote.addTrack(track);
      set({ remoteStream: remote });
    };
    peer.onicecandidate = ({ candidate }) => {
      if (candidate) send("candidate", candidate.toJSON());
    };
    peer.onnegotiationneeded = async () => {
      try {
        makingOffer = true;
        await peer.setLocalDescription();
        send("offer", peer.localDescription?.toJSON());
      } catch (e) {
        console.warn("[call] tạo offer lỗi", e);
      } finally {
        makingOffer = false;
      }
    };
    peer.onconnectionstatechange = () => {
      if (peer !== pc) return;
      if (peer.connectionState === "connected" && get().phase === "connecting") {
        set({ phase: "connected" });
        sendMedia();
      } else if (peer.connectionState === "failed") {
        toast.error("Mất kết nối cuộc gọi. Có thể cần máy chủ TURN nếu hai bên khác mạng.");
        void get().endCall();
      }
    };

    // thêm track sau cùng: addTrack kích hoạt negotiationneeded nên mọi handler phải gắn trước
    local?.getTracks().forEach((track) => {
      const sender = peer.addTrack(track, local!);
      if (track.kind === "video") videoSender = sender;
    });
  }

  async function handleSignal(ev: Extract<CallEvent, { type: "call.signal" }>) {
    const call = get().call;
    if (!call || ev.call_id !== call.id || ev.from === getCurrentUserId()) return;

    if (ev.kind === "media") {
      set({ remoteMedia: ev.payload as unknown as RemoteMedia });
      return;
    }
    if (!pc) return;
    try {
      if (ev.kind === "candidate") {
        if (!pc.remoteDescription) {
          pendingCandidates.push(ev.payload as RTCIceCandidateInit);
          return;
        }
        try {
          await pc.addIceCandidate(ev.payload as RTCIceCandidateInit);
        } catch (e) {
          if (!ignoreOffer) throw e;
        }
        return;
      }
      const description = ev.payload as unknown as RTCSessionDescriptionInit;
      const collision = description.type === "offer" && (makingOffer || pc.signalingState !== "stable");
      ignoreOffer = !polite && collision;
      if (ignoreOffer) return;
      await pc.setRemoteDescription(description);
      for (const c of pendingCandidates.splice(0)) await pc.addIceCandidate(c).catch(() => undefined);
      if (description.type === "offer") {
        await pc.setLocalDescription();
        send("answer", pc.localDescription?.toJSON());
      }
    } catch (e) {
      console.warn("[call] xử lý signal lỗi", e);
    }
  }

  onCallEvent((ev) => {
    const me = getCurrentUserId();
    const { phase, call } = get();

    if (ev.type === "call.ringing") {
      if (ev.call.doctor_id === me || phase !== "idle") return;
      polite = true;
      set({ phase: "ringing_in", call: ev.call, mode: ev.mode });
    } else if (ev.type === "call.accepted") {
      if (phase !== "ringing_out" || ev.call.id !== call?.id) return;
      clearRingTimer();
      polite = false;
      set({ phase: "connecting", call: ev.call });
      void setupPeer();
    } else if (ev.type === "call.ended") {
      if (ev.call.id !== call?.id) return;
      const byMe = ev.ended_by === me;
      const text: Record<string, string> = {
        ended: "Cuộc gọi đã kết thúc.",
        rejected: byMe ? "Đã từ chối cuộc gọi." : "Bệnh nhân đã từ chối cuộc gọi.",
        cancelled: byMe ? "Đã huỷ cuộc gọi." : "Bác sĩ đã huỷ cuộc gọi.",
        missed: byMe ? "Không ai bắt máy." : "Bạn đã lỡ cuộc gọi.",
      };
      finish(text[ev.reason]);
    } else if (ev.type === "call.signal") {
      void handleSignal(ev);
    }
  });

  return {
    ...IDLE,

    async startCall(conversationId, mode) {
      if (get().phase !== "idle") return;
      try {
        const media = await getMedia(mode === "video");
        local = media.stream;
        set({ localStream: local, mode: media.video ? "video" : "audio", camOn: media.video, micOn: true });
        const call = await videoCallApi.start(conversationId, media.video ? "video" : "audio");
        set({ phase: "ringing_out", call });
        ringTimer = setTimeout(() => void get().endCall("missed"), RING_TIMEOUT_MS);
      } catch (e) {
        teardown();
        set({ ...IDLE });
        toast.error(errorMessage(e));
      }
    },

    async acceptCall() {
      const { call, mode } = get();
      if (!call || get().phase !== "ringing_in") return;
      try {
        const media = await getMedia(mode === "video");
        local = media.stream;
        set({ localStream: local, camOn: media.video, micOn: true, phase: "connecting" });
        // PC phải sẵn sàng trước khi bên gọi thấy "accepted" để không lỡ offer
        await setupPeer();
        await videoCallApi.accept(call.id);
      } catch (e) {
        toast.error(errorMessage(e));
        await get().endCall();
      }
    },

    async endCall(reason) {
      const call = get().call;
      if (call) {
        try {
          await videoCallApi.end(call.id, reason);
        } catch (e) {
          console.warn("[call] kết thúc lỗi", e);
        }
      }
      // event call.ended có thể đến sau; dọn ngay để UI không treo khi mất mạng
      finish();
    },

    setMinimized(minimized) {
      set({ minimized });
    },

    toggleMic() {
      const next = !get().micOn;
      local?.getAudioTracks().forEach((t) => (t.enabled = next));
      set({ micOn: next });
      sendMedia();
    },

    async toggleCamera() {
      if (!local) return;
      if (get().camOn) {
        // dừng hẳn track để tắt đèn camera; replaceTrack(null) giữ sender nên bật lại không cần đàm phán lại
        local.getVideoTracks().forEach((t) => {
          t.stop();
          local?.removeTrack(t);
        });
        await videoSender?.replaceTrack(null);
        set({ camOn: false, localStream: new MediaStream(local.getTracks()) });
      } else {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ video: true });
          const track = stream.getVideoTracks()[0];
          local.addTrack(track);
          if (videoSender) await videoSender.replaceTrack(track);
          else if (pc) videoSender = pc.addTrack(track, local); // nâng cấp thoại → video: đàm phán lại
          set({ camOn: true, localStream: new MediaStream(local.getTracks()) });
        } catch (e) {
          toast.error(errorMessage(e));
          return;
        }
      }
      sendMedia();
    },
  };
});
