"""DTO Input cho resource Patient Profile"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.common.constant import Gender, ProfileRelationship


class ProfileFactInput(BaseModel):
    """Fact dài hạn bệnh nhân tự khai; nhãn trùng (không phân biệt hoa thường) với fact có sẵn thì cập nhật fact đó."""

    fact_type: Literal["allergy", "history", "medication"]
    label: str = Field(min_length=1, max_length=255)
    detail: str = Field(default="", max_length=300)


class CreatePatientProfileInput(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    dob: date
    gender: Gender
    relationship: ProfileRelationship = ProfileRelationship.SELF
    phone: str | None = Field(default=None, max_length=32)
    long_term_facts: list[ProfileFactInput] = []


class UpdatePatientProfileInput(BaseModel):
    """PATCH: chỉ field được gửi mới đổi (`model_dump(exclude_unset=True)`)."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    dob: date | None = None
    gender: Gender | None = None
    relationship: ProfileRelationship | None = None
    phone: str | None = Field(default=None, max_length=32)
    # gửi thì thay toàn bộ fact dài hạn: mục không còn trong danh sách bị xoá (kể cả mục AI trích từ chat)
    long_term_facts: list[ProfileFactInput] | None = None
