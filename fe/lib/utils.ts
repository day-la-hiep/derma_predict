import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  const hours = Math.floor(diffMs / 3_600_000);
  const days = Math.floor(diffMs / 86_400_000);

  if (minutes < 1) return "vừa xong";
  if (minutes < 60) return `${minutes} phút`;
  if (hours < 24) return `${hours} giờ`;
  if (days < 7) return `${days} ngày`;

  return formatDate(date);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Ngày luôn dạng dd/MM/yyyy (toLocaleDateString("vi-VN") bỏ số 0 đầu: 1/2/2026); rỗng nếu không hợp lệ */
export function formatDate(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(d.getTime())) return "";
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`;
}

/** Giờ + ngày: HH:mm dd/MM/yyyy */
export function formatDateTime(input: string | Date | null | undefined): string {
  if (!input) return "";
  const d = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(d.getTime())) return "";
  return `${pad(d.getHours())}:${pad(d.getMinutes())} ${formatDate(d)}`;
}

/** Giữ lại class màu chữ (kể cả dark:) của một bộ class badge; bỏ nền và viền để hiện dạng chữ thường */
export function textOnly(classes: string): string {
  return classes.split(/\s+/).filter((c) => /^(dark:)?text-/.test(c)).join(" ");
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(
    units.length - 1,
    Math.floor(Math.log(bytes) / Math.log(1024))
  );
  return `${parseFloat((bytes / 1024 ** i).toFixed(1))} ${units[i]}`;
}
