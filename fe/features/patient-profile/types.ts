// Khớp `core/app/dto/response/patient_profile.py` (snake_case giữ nguyên, không qua adapter)
export type Gender = "male" | "female";
export type ProfileRelationship = "self" | "child" | "parent" | "spouse" | "other";

export type LongTermFactType = "allergy" | "history" | "medication";

// Fact dài hạn của hồ sơ: bệnh nhân tự khai hoặc AI trích từ chat; bác sĩ xác nhận lúc chốt (`verified_at`)
export interface ProfileFact {
  id: string;
  fact_type: LongTermFactType;
  label: string;
  detail: string;
  verified_at: string | null;
}

export type ProfileFactInput = Pick<ProfileFact, "fact_type" | "label" | "detail">;

export interface PatientProfile {
  id: string;
  full_name: string;
  dob: string;
  gender: Gender;
  relationship: ProfileRelationship;
  phone: string | null;
  long_term_facts: ProfileFact[];
  created_at: string;
}

// gửi `long_term_facts` là thay toàn bộ danh sách: mục bỏ khỏi form bị xoá
export type PatientProfileInput = Omit<PatientProfile, "id" | "created_at" | "long_term_facts"> & {
  long_term_facts: ProfileFactInput[];
};

export interface FinalizeReport {
  id: string;
  diagnosis: string;
  notes: string;
  doctor_name: string | null;
  created_at: string;
}
