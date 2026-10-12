"""DTO Input cho resource Patient Profile"""

from datetime import date

from pydantic import BaseModel, Field

from app.common.constant import Gender, ProfileRelationship


class CreatePatientProfileInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    dob: date
    gender: Gender
    relationship: ProfileRelationship = ProfileRelationship.SELF
    phone: str | None = Field(default=None, max_length=32)
    allergies: str = ""
    medical_history: str = ""


class UpdatePatientProfileInput(BaseModel):
    """PATCH: chỉ field được gửi mới đổi (`model_dump(exclude_unset=True)`)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    dob: date | None = None
    gender: Gender | None = None
    relationship: ProfileRelationship | None = None
    phone: str | None = Field(default=None, max_length=32)
    allergies: str | None = None
    medical_history: str | None = None
