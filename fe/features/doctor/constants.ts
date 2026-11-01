import {
  Clock,
  CheckCircle2,
  CircleDot,
  Activity,
  Microscope,
  History,
  Pill,
  AlertTriangle,
  ImageIcon,
  HelpCircle,
  HandHelping,
  User,
  Calendar,
  HeartPulse,
  Sparkles,
  Stethoscope,
  Network,
  type LucideIcon,
} from "lucide-react";
import type { ClinicalFactType, ConsultationStatus, FactOrigin, Urgency } from "./types";

/** Cấu hình hiển thị theo loại Dữ kiện lâm sàng (bám sát bảng clinical_fact_templates trong DB) */
export interface FactTypeConfig {
  label: string;
  hint: string;
  icon: LucideIcon;
  colorClass: string;
}

export const FACT_TYPE_CONFIG: Record<ClinicalFactType, FactTypeConfig> = {
  symptom: {
    label: "Triệu chứng",
    hint: "Triệu chứng bệnh nhân mô tả: ngứa, đau, rát, thời gian xuất hiện...",
    icon: Activity,
    colorClass:
      "bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-400 border-blue-200 dark:border-blue-800/50",
  },
  lesion: {
    label: "Tổn thương",
    hint: "Đặc điểm tổn thương da: vị trí, hình dạng, màu sắc, kích thước.",
    icon: Microscope,
    colorClass:
      "bg-rose-100 text-rose-700 dark:bg-rose-950/50 dark:text-rose-400 border-rose-200 dark:border-rose-800/50",
  },
  history: {
    label: "Tiền sử",
    hint: "Tiền sử bệnh và diễn tiến của tình trạng hiện tại.",
    icon: History,
    colorClass:
      "bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-400 border-purple-200 dark:border-purple-800/50",
  },
  medication: {
    label: "Thuốc",
    hint: "Thuốc bệnh nhân đang dùng hoặc đã dùng.",
    icon: Pill,
    colorClass:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800/50",
  },
  allergy: {
    label: "Dị ứng",
    hint: "Dị ứng thuốc, thức ăn hoặc chất tiếp xúc đã ghi nhận.",
    icon: AlertTriangle,
    colorClass:
      "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400 border-amber-200 dark:border-amber-800/50",
  },
  image_finding: {
    label: "Ảnh (AI)",
    hint: "Nhận định AI từ ảnh bệnh nhân gửi. Chỉ là gợi ý, không phải chẩn đoán y khoa.",
    icon: ImageIcon,
    colorClass:
      "bg-indigo-100 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-400 border-indigo-200 dark:border-indigo-800/50",
  },
  other: {
    label: "Khác",
    hint: "Thông tin khác trích xuất từ hội thoại.",
    icon: HelpCircle,
    colorClass:
      "bg-gray-100 text-gray-700 dark:bg-gray-800/50 dark:text-gray-400 border-gray-200 dark:border-gray-700/50",
  },
};

/** Cấu hình hiển thị trạng thái phiên tư vấn (consultation_sessions.status) */
export interface StatusConfig {
  label: string;
  hint: string;
  dotClass: string;
  icon: LucideIcon;
  color: string;
  badgeClass: string;
}

export const STATUS_CONFIG: Record<ConsultationStatus, StatusConfig> = {
  pending: {
    label: "Chờ",
    hint: "Chờ nhận ca: bệnh nhân đã yêu cầu bác sĩ, chưa có bác sĩ tiếp nhận.",
    dotClass: "bg-amber-500",
    icon: Clock,
    color: "text-amber-500 dark:text-amber-400",
    badgeClass:
      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-400",
  },
  active: {
    label: "Đang",
    hint: "Đang tư vấn: bác sĩ đã nhận ca và đang trao đổi với bệnh nhân.",
    dotClass: "bg-emerald-500",
    icon: CircleDot,
    color: "text-emerald-500 dark:text-emerald-400",
    badgeClass:
      "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-400",
  },
  resolved: {
    label: "Xong",
    hint: "Đã hoàn thành: phiên đã đóng, chỉ xem lại.",
    dotClass: "bg-muted-foreground/40",
    icon: CheckCircle2,
    color: "text-muted-foreground",
    badgeClass: "border-border bg-muted text-muted-foreground",
  },
};

/** Cấu hình nút hành động tiếp quản / đóng phiên tư vấn */
export interface StatusActionConfig {
  label: string;
  hint: string;
  icon: LucideIcon;
  buttonClass: string;
  action: "accept" | "resolve" | null;
}

export const STATUS_ACTION_CONFIG: Record<ConsultationStatus, StatusActionConfig> = {
  pending: {
    label: "Nhận ca",
    hint: "Nhận ca tư vấn: bác sĩ tiếp quản cuộc trò chuyện từ AI và có thể nhắn trực tiếp cho bệnh nhân.",
    icon: HandHelping,
    buttonClass:
      "bg-gradient-to-r from-brand to-brand-secondary text-brand-foreground hover:shadow-accent",
    action: "accept",
  },
  active: {
    label: "Đóng ca",
    hint: "Đóng phiên tư vấn: mở form chốt báo cáo kết luận (điền sẵn dữ kiện của ca), chốt xong ca chuyển sang chế độ chỉ xem.",
    icon: CheckCircle2,
    buttonClass:
      "bg-gradient-to-r from-emerald-500 to-emerald-600 text-white hover:shadow-lg",
    action: "resolve",
  },
  resolved: {
    label: "Đã đóng",
    hint: "Phiên tư vấn đã hoàn tất.",
    icon: CheckCircle2,
    buttonClass: "",
    action: null,
  },
};

/** Các lựa chọn lọc ca tư vấn trên thanh sidebar */
export const FILTER_OPTIONS: { value: ConsultationStatus | "all"; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "pending", label: "Chờ" },
  { value: "active", label: "Đang" },
  { value: "resolved", label: "Xong" },
];

/** Mức khẩn cấp bác sĩ chốt cho báo cáo kết luận */
export const URGENCY_CONFIG: Record<Urgency, { label: string; hint: string; badgeClass: string }> = {
  emergency: {
    label: "Khẩn",
    hint: "Cần khám trực tiếp ngay.",
    badgeClass: "border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/50 dark:text-red-400",
  },
  few_days: {
    label: "Vài ngày",
    hint: "Nên khám trực tiếp trong vài ngày tới.",
    badgeClass:
      "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/50 dark:text-amber-400",
  },
  monitor: {
    label: "Theo dõi",
    hint: "Theo dõi tại nhà, tái khám khi có thay đổi.",
    badgeClass: "border-border bg-muted text-muted-foreground",
  },
};

export const URGENCY_ORDER: Urgency[] = ["emergency", "few_days", "monitor"];

/** Nguồn gốc dữ kiện trong phiếu đã chốt */
export const FACT_ORIGIN_CONFIG: Record<FactOrigin, { label: string; hint: string; badgeClass: string }> = {
  patient_reported: {
    label: "Bệnh nhân khai",
    hint: "Bệnh nhân tự kể trong hội thoại.",
    badgeClass: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/60 dark:bg-blue-950/50 dark:text-blue-400",
  },
  ai_inferred: {
    label: "AI suy ra",
    hint: "AI suy ra (vd từ ảnh) — chỉ là giả thuyết, không phải chẩn đoán y khoa.",
    badgeClass:
      "border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/50 dark:text-indigo-400",
  },
  doctor_observed: {
    label: "Bác sĩ ghi nhận",
    hint: "Bác sĩ ghi nhận khi khám, không có tin nhắn gốc.",
    badgeClass:
      "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/50 dark:text-emerald-400",
  },
  doctor_corrected: {
    label: "Bác sĩ sửa",
    hint: "Bác sĩ sửa lại dữ kiện có sẵn; nguồn là tin gốc của dữ kiện ban đầu.",
    badgeClass:
      "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900/60 dark:bg-violet-950/50 dark:text-violet-400",
  },
};

/** Lọc theo thời gian ở màn Lịch sử khám (ngày; null = tất cả) */
export const TIME_FILTERS: { days: number | null; label: string }[] = [
  { days: 7, label: "7 ngày" },
  { days: 30, label: "30 ngày" },
  { days: 90, label: "90 ngày" },
  { days: null, label: "Tất cả" },
];

/* ────────── Patient Journey Graph Config ────────── */

export interface JourneyNodeConfig {
  label: string;
  hint: string;
  icon: LucideIcon;
  badgeClass: string;
  colorClass: string;
  dotColor: string;
}

export const DEFAULT_JOURNEY_NODE_CONFIG: JourneyNodeConfig = {
  label: "Thực thể",
  hint: "Nút dữ liệu trên đồ thị tri thức",
  icon: CircleDot,
  badgeClass: "border-border bg-muted text-muted-foreground",
  colorClass: "border-border bg-muted text-muted-foreground",
  dotColor: "#64748b",
};

export const JOURNEY_NODE_CONFIG: Record<string, JourneyNodeConfig> = {
  Patient: {
    label: "Bệnh nhân",
    hint: "Hồ sơ bệnh nhân là nút trung tâm của đồ thị",
    icon: User,
    badgeClass: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-900/60 dark:bg-sky-950/50 dark:text-sky-400",
    colorClass: "border-sky-400/40 bg-sky-500/10 text-sky-600 dark:text-sky-400",
    dotColor: "#0284c7",
  },
  ConsultationSession: {
    label: "Phiên tư vấn",
    hint: "Phiên tư vấn giữa bệnh nhân, AI và bác sĩ",
    icon: Calendar,
    badgeClass: "border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-900/60 dark:bg-indigo-950/50 dark:text-indigo-400",
    colorClass: "border-indigo-400/40 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
    dotColor: "#6366f1",
  },
  Symptom: {
    label: "Triệu chứng",
    hint: "Dữ kiện triệu chứng ghi nhận trong phiên",
    icon: Activity,
    badgeClass: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/50 dark:text-amber-400",
    colorClass: "border-amber-400/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
    dotColor: "#d97706",
  },
  Lesion: {
    label: "Tổn thương da",
    hint: "Dữ kiện tổn thương da ghi nhận trong phiên",
    icon: Microscope,
    badgeClass: "border-pink-200 bg-pink-50 text-pink-700 dark:border-pink-900/60 dark:bg-pink-950/50 dark:text-pink-400",
    colorClass: "border-pink-400/40 bg-pink-500/10 text-pink-600 dark:text-pink-400",
    dotColor: "#db2777",
  },
  ClinicalFact: {
    label: "Dữ kiện lâm sàng",
    hint: "Dữ kiện ghi nhận từ phiên tư vấn",
    icon: Activity,
    badgeClass: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/50 dark:text-amber-400",
    colorClass: "border-amber-400/40 bg-amber-500/10 text-amber-600 dark:text-amber-400",
    dotColor: "#d97706",
  },
  Condition: {
    label: "Chẩn đoán",
    hint: "Bệnh lý / Tình trạng được bác sĩ chẩn đoán sau khám",
    icon: HeartPulse,
    badgeClass: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/50 dark:text-rose-400",
    colorClass: "border-rose-400/40 bg-rose-500/10 text-rose-600 dark:text-rose-400",
    dotColor: "#e11d48",
  },
  SuspectedCondition: {
    label: "Chẩn đoán nghi ngờ",
    hint: "Bệnh lý / Tình trạng được bác sĩ chẩn đoán sau phiên",
    icon: HeartPulse,
    badgeClass: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/50 dark:text-rose-400",
    colorClass: "border-rose-400/40 bg-rose-500/10 text-rose-600 dark:text-rose-400",
    dotColor: "#e11d48",
  },
  Advice: {
    label: "Dặn dò",
    hint: "Lời dặn, đơn thuốc và hướng dẫn điều trị của bác sĩ",
    icon: Sparkles,
    badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/50 dark:text-emerald-400",
    colorClass: "border-emerald-400/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
    dotColor: "#059669",
  },
  Doctor: {
    label: "Bác sĩ",
    hint: "Bác sĩ phụ trách và chốt báo cáo kết luận cho phiên",
    icon: Stethoscope,
    badgeClass: "border-purple-200 bg-purple-50 text-purple-700 dark:border-purple-900/60 dark:bg-purple-950/50 dark:text-purple-400",
    colorClass: "border-purple-400/40 bg-purple-500/10 text-purple-600 dark:text-purple-400",
    dotColor: "#9333ea",
  },
  DermoTerm: {
    label: "Ontology DermO",
    hint: "Thuật ngữ chuẩn hoá trong Ontology da liễu DermO",
    icon: Network,
    badgeClass: "border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-900/60 dark:bg-teal-950/50 dark:text-teal-400",
    colorClass: "border-teal-400/40 bg-teal-500/10 text-teal-600 dark:text-teal-400",
    dotColor: "#0d9488",
  },
  PatientImage: {
    label: "Ảnh bệnh",
    hint: "Hình ảnh tổn thương da bệnh nhân gửi hoặc bác sĩ đính kèm",
    icon: ImageIcon,
    badgeClass: "border-cyan-200 bg-cyan-50 text-cyan-700 dark:border-cyan-900/60 dark:bg-cyan-950/50 dark:text-cyan-400",
    colorClass: "border-cyan-400/40 bg-cyan-500/10 text-cyan-600 dark:text-cyan-400",
    dotColor: "#06b6d4",
  },
};

export const JOURNEY_EDGE_CONFIG: Record<string, { label: string; strokeColor: string; dashed?: boolean }> = {
  HAD_SESSION: { label: "Phiên tư vấn", strokeColor: "#0284c7" },
  NEXT: { label: "Tiếp theo", strokeColor: "#6366f1", dashed: true },
  HAS_SYMPTOM: { label: "Triệu chứng", strokeColor: "#d97706" },
  REPORTED_FACT: { label: "Dữ kiện", strokeColor: "#d97706" },
  MAPS_TO: { label: "Chuẩn hoá DermO", strokeColor: "#0d9488", dashed: true },
  CONDUCTED_BY: { label: "Bác sĩ", strokeColor: "#9333ea" },
  HAS_CONDITION: { label: "Chẩn đoán", strokeColor: "#e11d48" },
  SUSPECTED_CONDITION: { label: "Chẩn đoán", strokeColor: "#e11d48" },
  RECEIVED_ADVICE: { label: "Dặn dò", strokeColor: "#059669" },
  RECOMMENDED_ADVICE: { label: "Dặn dò", strokeColor: "#059669" },
  HAS_IMAGE: { label: "Ảnh chụp", strokeColor: "#06b6d4" },
  EVIDENCES: { label: "Bằng chứng", strokeColor: "#8b5cf6", dashed: true },
  CONFIRMED_AS: { label: "Xác nhận nhãn", strokeColor: "#f43f5e" },
  FOLLOWS: { label: "Tiến triển", strokeColor: "#10b981", dashed: true },
};
