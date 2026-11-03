import type { Gender, LongTermFactType, PatientProfileInput, ProfileRelationship } from "./types";

export const RELATIONSHIP_LABELS: Record<ProfileRelationship, string> = {
  self: "Bản thân",
  child: "Con",
  parent: "Bố/mẹ",
  spouse: "Vợ/chồng",
  other: "Khác",
};

export const GENDER_LABELS: Record<Gender, string> = { male: "Nam", female: "Nữ" };

export const EMPTY_PROFILE: PatientProfileInput = {
  full_name: "",
  dob: "",
  gender: "male",
  relationship: "other",
  phone: null,
  long_term_facts: [],
};

export const FACT_TYPE_LABELS: Record<LongTermFactType, string> = {
  allergy: "Dị ứng",
  history: "Tiền sử",
  medication: "Thuốc đang dùng",
};

export const HINTS = {
  delete: "Chỉ xoá được hồ sơ chưa có cuộc trò chuyện hay báo cáo kết luận, và không phải hồ sơ cuối cùng.",
  facts:
    "Dị ứng, bệnh đã/đang mắc, thuốc đang dùng. Gồm cả thông tin trợ lý ghi lại khi bạn trò chuyện; bác sĩ xem và xác nhận khi khám. Xoá một dòng là xoá khỏi hồ sơ.",
  reports: "Báo cáo kết luận do bác sĩ ghi sau mỗi lần khám. Bạn chỉ xem, không sửa được.",
};
