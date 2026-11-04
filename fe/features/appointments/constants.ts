import type { AppointmentStatus } from "./types";

export const APPOINTMENT_STATUS: Record<AppointmentStatus, { label: string; hint: string; className: string }> = {
  requested: { label: "Chờ", hint: "Đã gửi yêu cầu, chờ bác sĩ xác nhận.", className: "bg-amber-100 text-amber-800 border-amber-200" },
  confirmed: { label: "Đã hẹn", hint: "Bác sĩ đã xác nhận lịch.", className: "bg-blue-100 text-blue-800 border-blue-200" },
  in_progress: { label: "Đang khám", hint: "Bác sĩ đã bắt đầu khám.", className: "bg-violet-100 text-violet-800 border-violet-200" },
  done: { label: "Xong", hint: "Đã có kết luận.", className: "bg-emerald-100 text-emerald-800 border-emerald-200" },
  cancelled: { label: "Huỷ", hint: "Lịch đã bị huỷ.", className: "bg-muted text-muted-foreground border-border" },
  no_show: { label: "Vắng", hint: "Bệnh nhân không đến.", className: "bg-red-100 text-red-800 border-red-200" },
};

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "2-digit", year: "numeric" });
}
