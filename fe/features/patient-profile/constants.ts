import type { Gender, PatientProfileInput, ProfileRelationship } from "./types";

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
  allergies: "",
  medical_history: "",
};

export const HINTS = {
  delete: "Chỉ xoá được hồ sơ chưa có cuộc trò chuyện hay bệnh án, và không phải hồ sơ cuối cùng.",
  allergies: "Dị ứng thuốc, thức ăn… do bạn tự khai.",
  history: "Bệnh đã/đang mắc, phẫu thuật, bệnh mạn tính… do bạn tự khai.",
  records: "Bệnh án do bác sĩ ghi sau mỗi lần khám. Bạn chỉ xem, không sửa được.",
};
