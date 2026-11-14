from datetime import date, datetime

from pydantic import BaseModel, Field


class PatientFactInput(BaseModel):
    # 1 triệu chứng · 2 tổn thương (hình thái) · 3 đặc điểm (thuộc tính đơn trị, gồm vị trí) · 4 yếu tố tác động · 5 tiền sử / thuốc
    category: int = Field(ge=1, le=5)
    label: str = Field(min_length=1)  # lời người bệnh gọi tên triệu chứng / thuốc / bệnh, hoặc giá trị chữ của thuộc tính
    detail: str = ""  # chi tiết chữ tự do (mức độ, thời điểm trong ngày...), không phải khoá
    name: str = ""  # tên thuộc tính của nhóm 3: location | distribution | arrangement | course | tên tự do (màu, kích thước, tên xét nghiệm...)
    object_type: str = ""  # loại nút PrimeKG/DermO (`effect/phenotype`, `disease`, `drug`, `exposure`, `dermo`); rỗng = giá trị chữ
    kg_node_id: str | None = None
    link_method: str = "none"
    present: bool = True  # false = người bệnh nói không có ("không ngứa")
    resolved: bool = False  # người bệnh nói đã hết
    kind: str = ""  # tổn thương: primary | secondary; thuốc: taking | allergy
    effect: str = ""  # nhóm 4: trigger | aggravate | relieve; để trống = phơi nhiễm (hoá chất, nghề nghiệp, thú nuôi...)
    of: str = ""  # tiền sử: self | family
    lesion_id: str | None = None  # id có sẵn, hoặc id mới do agent tự sinh (chưa có thì tạo, thuộc bệnh nhân này)
    lesion_key: str | None = None  # khoá tạm cho tổn thương mới trong cùng yêu cầu
    site_text: str = ""
    scope: str = "skin"  # skin | mucosa | nail | hair | organ; `body` = thuộc người bệnh, không gắn tổn thương (sốt, xét nghiệm)
    onset_text: str = ""
    source_message_id: str | None = None
    observed_at: datetime | None = None


class PatientFactsApplyInput(BaseModel):
    patient_id: str = Field(min_length=1)
    facts: list[PatientFactInput]


class AppliedLesion(BaseModel):
    key: str
    id: str


class SkippedFact(BaseModel):
    index: int
    reason: str


class PatientFactsApplyOutput(BaseModel):
    applied: int
    skipped: list[SkippedFact]
    lesions: list[AppliedLesion]


class PatientLesionOutput(BaseModel):
    id: str
    site_text: str
    scope: str


class PatientFactOutput(BaseModel):
    id: str = ""  # id ổn định của cạnh: form chốt của bác sĩ trỏ tới fact nguồn bằng id này
    fact_type: str = "other"  # symptom | lesion | history | medication | allergy | other (suy từ nhóm khám, cho UI và snapshot)
    lesion_id: str | None
    category: int | None
    relation: str
    label: str  # lời người bệnh; nút đã khớp có tên chuẩn ở `kg_name`
    kg_name: str = ""
    detail: str = ""
    object_type: str
    kg_node_id: str | None
    present: bool | None
    status: str
    name: str = ""
    kind: str = ""
    effect: str = ""
    of: str = ""
    onset_text: str = ""
    onset_at: date | None = None
    observed_at: str | None = None
    last_confirmed_at: str | None = None
    stale: bool
    source_message_id: str | None = None
    link_method: str = "none"


class PatientFactsOutput(BaseModel):
    lesions: list[PatientLesionOutput]
    facts: list[PatientFactOutput]


class MatchedFact(BaseModel):
    label: str
    kg_name: str
    object_type: str
    present: bool
    relation: str


class CandidateDisease(BaseModel):
    name: str
    score: float
    why: list[str]
    absent: list[str]  # triệu chứng bệnh nhân nói KHÔNG có mà bệnh này thường có (đã trừ điểm)


class DiscriminatingQuestion(BaseModel):
    phenotype: str
    present_in: list[str]
    absent_in: list[str]


class BookEvidence(BaseModel):
    disease: str
    relation: str
    object: str
    evidence: str
    pages: list[int]
    document_id: str | None = None


class PatientGraphContextOutput(BaseModel):
    matched: list[MatchedFact]
    unmatched: list[str]  # fact chưa khớp nút đồ thị nên không tham gia mở rộng
    candidates: list[CandidateDisease]
    questions: list[DiscriminatingQuestion]
    drug_notes: list[str]
    book_evidence: list[BookEvidence]
    notes: list[str]


class ProfileFactItem(BaseModel):
    fact_type: str = Field(pattern="^(allergy|history|medication)$")
    label: str = Field(min_length=1, max_length=255)
    detail: str = Field(default="", max_length=300)


class ProfileFactsReplaceInput(BaseModel):
    facts: list[ProfileFactItem] = Field(default_factory=list)
