"""DTO của API: envelope, request và response. Entity nghiệp vụ nằm ở `app/dto/base/`."""
from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from app.dto.base.shared import File


# -------------------- Envelope và file dùng chung


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Envelope chuẩn cho response 1 object/list"""

    data: T


class FileDto(File):
    """File trên wire"""

    url: str | None = None


# -------------------- Request: pipeline tài liệu


class RunStageInput(BaseModel):
    options: dict[str, Any] = {}
    force: bool = False  # bỏ qua kiểm tra bước phụ thuộc đã duyệt


class DocumentSettings(BaseModel):
    """Phần cấu hình của tài liệu sửa được trên giao diện; các tuỳ chọn khác lấy mặc định trong `Profile`."""

    title: str = Field(min_length=1)
    engine: Literal["pdftotext", "docling"]


class TocItem(BaseModel):
    """Sửa một mục của mục lục. Trường để trống = không đổi; `clear_page` = đặt số trang về rỗng."""

    id: str
    title: str | None = None
    level: int | None = Field(default=None, ge=0, le=3)
    page_printed: int | None = Field(default=None, ge=0)  # override lưu dưới khoá `printed_page` (khớp `toc.json`)
    clear_page: bool = False


class TocNew(BaseModel):
    title: str = Field(min_length=1)
    level: int = Field(default=2, ge=0, le=3)
    page_printed: int | None = Field(default=None, ge=0)
    after_id: str | None = None  # chèn sau mục này; trống = cuối danh sách


class TocUpdate(BaseModel):
    items: list[TocItem] = []
    deleted: list[str] = []  # mục máy đọc thì ẩn đi (lấy lại bằng cách chạy lại bước `toc`); mục thêm tay thì xoá hẳn
    added: list[TocNew] = []
    offset: int | None = None  # trang PDF = trang in + offset; đặt tay thì thắng độ lệch tự suy


class TripleUpdate(BaseModel):
    rejected: list[str] = []
    restored: list[str] = []  # hoàn tác loại


# -------------------- Request: danh mục loại thực thể / quan hệ của bước graph


class EntityTypeCreate(BaseModel):
    id: str
    label: str
    title: str = Field(min_length=1, max_length=100)
    hint: str = Field(min_length=1, max_length=300)
    case_sensitive: bool = False


class EntityTypeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    hint: str | None = Field(default=None, min_length=1, max_length=300)
    case_sensitive: bool | None = None


class RelationCreate(BaseModel):
    relation_type: str
    topic: Literal["disease", "drug"]
    object_type: str
    topic_is_head: bool = True
    title: str = Field(min_length=1, max_length=100)
    display: str = Field(default="", max_length=100)  # rỗng = dùng `title`
    hint: str = Field(min_length=1, max_length=300)
    entity_hint: str = Field(default="", max_length=300)
    enabled: bool = True


class RelationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    display: str | None = Field(default=None, min_length=1, max_length=100)
    hint: str | None = Field(default=None, min_length=1, max_length=300)
    entity_hint: str | None = Field(default=None, max_length=300)
    enabled: bool | None = None


# -------------------- Request: ca bệnh clinical gửi sang


class CaseImage(BaseModel):
    file_id: str
    storage_key: str
    file_name: str = ""
    body_site: str = ""
    description: str = ""
    confirmed_label: str | None = None


class CasePatient(BaseModel):
    gender: str = ""
    dob: date | None = None
    allergies: str = ""
    medical_history: str = ""


class CaseAssessment(BaseModel):
    reasoning: str = ""
    urgency: str = ""
    instructions: list[str] = []


class CaseFact(BaseModel):
    fact_type: str = "symptom"
    label: str = ""
    detail: str = ""


class CaseSnapshot(BaseModel):
    """Chỉ phần knowledge dùng của `FinalizeReportSnapshot`; trường khác clinical gửi thêm sẽ bị bỏ qua."""

    patient_profile: CasePatient
    assessment: CaseAssessment
    clinical_facts: list[CaseFact] = []


class CaseInput(BaseModel):
    """Báo cáo kết luận đã chốt do clinical gửi sang để index Qdrant (ca tham khảo) và đồng bộ đồ thị bệnh nhân."""

    report_id: str
    patient_profile_id: str
    doctor_id: str | None = None
    encounter_id: str | None = None
    consultation_session_id: str | None = None
    diagnosis: str
    notes: str = ""
    is_reference_case: bool = False
    created_at: datetime
    snapshot: CaseSnapshot
    images: list[CaseImage] = []

    @property
    def visit_id(self) -> str:
        """Id nút phiên trong đồ thị: lần khám, hoặc phiên tư vấn của dữ liệu cũ."""
        return self.encounter_id or self.consultation_session_id or self.report_id


# -------------------- Response: pipeline tài liệu


class StageOutput(BaseModel):
    """Trạng thái một bước xử lý của tài liệu (dữ liệu `document_stages` + hằng `STAGES`)."""

    stage_id: str
    title: str
    deps: list[str]
    uses_llm: bool
    state: str
    started_at: str | None = None
    finished_at: str | None = None
    approved_at: str | None = None
    progress: dict[str, Any] | None = None  # {done, total, message}
    summary: dict[str, Any] | None = None
    error: str | None = None
    options: dict[str, Any] = {}
    blocked_by: list[str] = []  # bước phụ thuộc chưa approved -> chưa được chạy


class DocumentSummary(BaseModel):
    id: str
    title: str
    created_at: str | None = None
    pdf_pages: int | None = None
    file_size: int | None = None
    states: dict[str, str]


class DocumentOutput(BaseModel):
    id: str
    title: str
    created_at: str | None = None
    source_file: FileDto | None = None  # None = chưa có PDF gốc
    pdf_pages: int | None = None
    stages: list[StageOutput]
    running_stage: str | None = None  # tối đa một bước chạy mỗi tài liệu; tính từ `stages`


class TocEntryOutput(BaseModel):
    """Một mục mục lục"""

    id: str
    level: int
    kind: str
    title: str
    page_printed: int | None = None
    toc_page: int | None = None
    suspect: bool = False
    suspect_reason: str | None = None
    edited: bool = False
    added: bool = False
    parent_id: str | None = None
    path: list[str] = []
    page: int | None = None  # trang PDF
    anchor_line: int | None = None
    anchored: bool = False
    out_of_range: bool = False


class TocOutput(BaseModel):
    """Mục lục đầy đủ của một tài liệu — nguồn: `toc.json` (`mapping.py::build_toc`)."""

    toc_pages: list[int]
    pages_source: str
    entries: list[TocEntryOutput]
    offset: int | None = None
    offset_info: dict[str, Any] = {}
    total_pages: int
    anchored: int
    warnings: list[str] = []


class ChunkOutput(BaseModel):
    """Một chunk — nguồn: `pipeline/document_ingest/stages/step3_chunks.py::build_chunks` (`chunks.jsonl`)."""

    chunk_id: str
    seq: int
    text: str
    context_text: str
    part: str = ""
    section: str = ""
    topic: str = ""
    subtopic: str = ""
    toc_path: list[str] = []
    toc_node_ids: list[str] = []
    figure_ids: list[str] = []
    level: int
    pages_hint: list[int]
    boundary: bool
    suspect: bool
    page_start: int
    page_end: int
    page_printed_start: int
    page_printed_end: int
    tokens: int
    chars: int
    review_reason: str | None = None


class SourcePageOutput(BaseModel):
    """Một trang nguồn — nguồn: `pipeline/document_ingest/stages/step1_ingest.py::_row` (`pages.jsonl`)."""

    page: int
    page_printed: int
    header: str
    text: str
    noise: bool
    noise_reason: str | None = None
    noise_score: float


class FigureOutput(BaseModel):
    """Một ảnh trong sách — nguồn: `pipeline/document_ingest/stages/step1_ingest.py::_figure_rows` (`figures.json`)."""

    figure_id: str
    document_id: str
    page: int
    seq: int
    bbox: list[float] | None = None
    caption: str = ""


class FigureListOutput(BaseModel):
    items: list[FigureOutput]
    total: int
    page: int
    page_size: int


class ChunkListOutput(BaseModel):
    items: list[ChunkOutput]
    total: int
    page: int
    page_size: int
    counts: dict[str, Any] = {}


class GraphNodeRefOutput(BaseModel):
    """Field khớp `GraphNodeRef`."""

    kg: str
    type: str
    text: str
    en: str = ""
    node_id: str | None = None
    name: str = ""
    link_method: str = ""


class TripleOutput(BaseModel):
    """Một quan hệ trích từ sách — nguồn: `pipeline/document_ingest/stages/step5_graph.py` (`triples.jsonl`)."""

    triple_id: str
    slot: str
    relation: str
    subject: GraphNodeRefOutput
    object: GraphNodeRefOutput
    evidence: str
    chunk_ids: list[str]
    pages: list[int]
    status: str


class TripleListOutput(BaseModel):
    items: list[TripleOutput]
    total: int
    page: int
    page_size: int
    counts: dict[str, Any] = {}


# -------------------- Response: đồ thị hành trình bệnh nhân


class GraphNodeOutput(BaseModel):
    id: str = Field(..., description="ID định danh duy nhất của Node")
    label: str = Field(..., description="Nhãn chính của Node (Patient, ConsultationSession, Symptom, v.v.)")
    name: str = Field(..., description="Tên hiển thị trực quan trên đồ thị")
    properties: dict[str, Any] = Field(default_factory=dict, description="Các thuộc tính chi tiết của Node")


class GraphEdgeOutput(BaseModel):
    id: str = Field(..., description="ID định danh duy nhất của quan hệ")
    source: str = Field(..., description="ID của Node nguồn")
    target: str = Field(..., description="ID của Node đích")
    type: str = Field(..., description="Loại quan hệ (HAD_SESSION, NEXT, REPORTED_SYMPTOM, v.v.)")
    properties: dict[str, Any] = Field(default_factory=dict, description="Thuộc tính của cạnh (nếu có)")


class PatientJourneyGraphOutput(BaseModel):
    patient_id: str = Field(..., description="ID của hồ sơ bệnh nhân")
    nodes: list[GraphNodeOutput] = Field(default_factory=list, description="Danh sách các Node trong đồ thị")
    edges: list[GraphEdgeOutput] = Field(default_factory=list, description="Danh sách các Cạnh liên kết")
