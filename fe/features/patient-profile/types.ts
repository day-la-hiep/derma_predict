// Khớp `core/app/dto/response/patient_profile.py` (snake_case giữ nguyên, không qua adapter)
export type Gender = "male" | "female";
export type ProfileRelationship = "self" | "child" | "parent" | "spouse" | "other";

export interface PatientProfile {
  id: string;
  full_name: string;
  dob: string;
  gender: Gender;
  relationship: ProfileRelationship;
  phone: string | null;
  allergies: string;
  medical_history: string;
  created_at: string;
}

export type PatientProfileInput = Omit<PatientProfile, "id" | "created_at">;

export interface MedicalRecord {
  id: string;
  diagnosis: string;
  notes: string;
  doctor_name: string | null;
  created_at: string;
}
