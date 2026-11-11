export type FollowupStatus = "open" | "read_only";

export interface FollowupChannel {
  conversationId: string;
  encounterId: string;
  status: FollowupStatus;
  followupUntil: string | null;
  doctorId: string | null;
  doctorName: string | null;
  // chỉ có ở danh sách của bác sĩ
  patientName: string | null;
  patientProfileId: string | null;
  lastMessageAt: string | null;
}
