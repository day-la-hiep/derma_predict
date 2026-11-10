"""Bounded context Định danh: tài khoản (`User`, `Doctor`, `Admin`) và hồ sơ bệnh nhân (`PatientProfile`)."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from pydantic import BaseModel, model_validator

from app.common.constant import LONG_TERM_FACT_TYPES, Gender, ProfileRelationship

if TYPE_CHECKING:
    # import chéo context chỉ để type-check; vòng tham chiếu được rebuild một lần trong `app/dto/base/__init__.py`
    from app.dto.base.clinical import ClinicalFact
    from app.dto.base.episode import ClinicalEpisode
    from app.dto.base.finalize_report import FinalizeReport


class User(BaseModel):
    id: str
    username: str
    full_name: str
    dob: date
    gender: Gender
    password_hash: str | None = None  # None: tài khoản chưa đặt mật khẩu (dữ liệu mẫu), chưa đăng nhập được
    patient_profiles: list[PatientProfile]


class Doctor(User):
    description: str


class Admin(User):
    pass


class PatientProfile(BaseModel):
    id: str
    full_name: str
    dob: date
    gender: Gender
    relationship: ProfileRelationship = ProfileRelationship.SELF
    phone: str | None = None
    finalize_reports: list[FinalizeReport] = []
    # chỉ fact dài hạn (dị ứng, tiền sử, thuốc) — thay cột tự khai allergies / medical_history cũ; triệu chứng nằm theo đợt
    clinical_facts: list[ClinicalFact] = []
    episodes: list[ClinicalEpisode] = []

    @model_validator(mode="after")
    def validate_long_term_facts(self):
        if any(f.fact_type not in LONG_TERM_FACT_TYPES for f in self.clinical_facts):
            raise ValueError("only long-term facts (allergy/history/medication) belong to the profile; others go to an episode")
        return self
