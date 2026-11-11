"""Bounded context Dữ kiện lâm sàng: fact hiện trạng của người bệnh và nhật ký nguồn của nó."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.common.constant import ClinicalFactType, ProvenanceKind

if TYPE_CHECKING:
    from app.dto.base.conversation import Message
    from app.dto.base.identity import Doctor
    from app.dto.base.visit import Encounter


class ClinicalProvenance(BaseModel):
    """Một lần một nguồn ghi nhận giá trị của fact; chỉ thêm, không sửa — vừa là bằng chứng vừa là lịch sử thay đổi."""

    kind: ProvenanceKind
    message: Message | None = None  # tin gốc (kind = chat); None khi tin đã bị xoá
    quote: str = ""  # chép tin gốc lúc ghi để tin bị xoá vẫn đọc được
    encounter: Encounter | None = None  # lần khám bác sĩ ghi nhận (kind = doctor)
    doctor: Doctor | None = None
    detail: str = ""  # giá trị fact mà nguồn này ghi nhận tại thời điểm đó
    created_at: datetime | None = None


class ClinicalFact(BaseModel):
    """Tình trạng hiện tại, sửa tại chỗ; lịch sử nằm ở `provenances` và snapshot của kết luận đã chốt."""

    id: str
    # dài hạn (allergy/history/medication) nằm ở `PatientProfile.clinical_facts`, còn lại ở `ClinicalEpisode.facts`
    fact_type: ClinicalFactType
    label: str  # tên ngắn, vd "Ngứa", "Dị ứng penicillin"; duy nhất trong phạm vi chứa nó, không phân biệt hoa thường
    ontology_id: str | None = None  # id DermO / PrimeKG khi đã chuẩn hoá
    detail: str = ""  # giá trị hiện tại — thay thế chứ không nối thêm
    provenances: list[ClinicalProvenance] = []
    verified_at: datetime | None = None  # bác sĩ xác nhận lúc chốt; AI sửa lại thì về None
    verified_by: Doctor | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
