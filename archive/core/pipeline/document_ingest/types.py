from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PipelineModel(BaseModel):
    # file JSON cũ trong MinIO có thể thừa/thiếu key: bỏ key lạ, field thiếu lấy mặc định
    model_config = ConfigDict(extra="ignore")


class PageRow(PipelineModel):
    """Một dòng của `pages.jsonl`: chữ của một trang PDF sau bước Đọc nội dung."""

    page: int = Field(description="Số trang trong file PDF, bắt đầu từ 1")
    page_printed: int = Field(description="Số trang in trên giấy; đọc từ chân trang, thiếu thì lấy page + page_offset của profile")
    header: str = Field(default="", description="Running header của trang (tên chương in đầu trang); rỗng nếu không có")
    text: str = Field(description="Chữ thân trang, mỗi dòng cách nhau bằng \\n; mục danh sách bắt đầu bằng '• '")
    noise: bool = Field(default=False, description="True = trang bị bỏ qua khi chia đoạn (do profile đánh dấu hoặc là mục từ cuối sách)")
    noise_reason: Literal["profile", "index"] | None = Field(default=None, description="Lý do noise: profile = nằm trong `noise_pages`, index = trang INDEX")
    noise_score: float = Field(default=0.0, description="Tỷ lệ ký tự rác của trang (0-1); trên 0.05 là OCR kém")


class DoclingBlock(PipelineModel):
    """Một khối chữ/hình Docling nhận dạng được trên trang."""

    page: int = Field(description="Số trang PDF chứa khối")
    label: str = Field(description="Loại khối: heading, text, list, caption, table, toc, page_header, page_footer, figure...")
    text: str = Field(default="", description="Chữ của khối; bảng là Markdown nhiều dòng; hình thì là chú thích")
    bbox: list[float] | None = Field(default=None, description="[trái, trên, phải, dưới] trên trang PDF; chỉ có với hình")
    image_key: str | None = Field(default=None, description="Đường dẫn ảnh đã lưu, tương đối so với thư mục tài liệu (figures/pNNNNN_NN.png); chỉ có với hình")


class FigureDraft(PipelineModel):
    """Hình minh hoạ do pipeline tìm ra; service đổi thành `DocumentFigure` (thêm `storage_key`) khi ghi `figures.json`."""

    figure_id: str = Field(description="`<document_id>:fNNNNN`, đánh số theo thứ tự trang")
    document_id: str = Field(description="Tài liệu chứa hình")
    page: int = Field(description="Số trang PDF chứa hình")
    seq: int = Field(description="Thứ tự hình trong tài liệu, từ 1")
    bbox: list[float] | None = Field(default=None, description="[trái, trên, phải, dưới] trên trang PDF")
    caption: str = Field(default="", description="Chú thích đi kèm hình trong sách")
    image_key: str = Field(description="Đường dẫn ảnh tương đối so với thư mục tài liệu")


class TocEntry(PipelineModel):
    """Một mục của mục lục (part / section / bệnh / mục con), theo thứ tự đọc."""

    id: str = Field(description="Mã mục tCCCC; mục người duyệt thêm có mã riêng")
    level: int = Field(ge=0, le=3, description="0 = part, 1 = section, 2 = mục có số trang (bệnh), 3 = mục con")
    kind: str = Field(description="Tên cấp tương ứng với level: part | section | topic | sub")
    title: str = Field(description="Tên mục, đã chuẩn hoá khoảng trắng")
    printed_page: int | None = Field(default=None, description="Số trang in ghi trong mục lục; None nếu mục không có số (part/section) hoặc số La Mã")
    toc_page: int | None = Field(default=None, description="Trang PDF của mục lục chứa mục này; None khi LLM đọc nhiều trang cùng lúc")
    suspect: bool = Field(default=False, description="True = số trang đáng ngờ (không tăng dần), người duyệt cần kiểm tra")
    suspect_reason: str = Field(default="", description="Lý do suspect, hiển thị cho người duyệt")
    edited: bool = Field(default=False, description="True = người duyệt đã sửa mục này")
    added: bool = Field(default=False, description="True = mục do người duyệt thêm, không có trong kết quả máy")
    pdf_page: int | None = Field(default=None, description="Trang PDF mà mục bắt đầu = printed_page + offset (hoặc trang đã neo); None khi chưa tính")
    anchor_line: int | None = Field(default=None, description="Chỉ số dòng trong trang PDF khớp tiêu đề mục; None khi chưa neo")
    anchored: bool = Field(default=False, description="True = đã tìm thấy dòng tiêu đề của mục trong thân sách")
    out_of_range: bool = Field(default=False, description="True = mục nằm ngoài các trang đang có (PDF chỉ là một phần sách)")
    parent_id: str | None = Field(default=None, description="Mã mục cha (mục có cấp thấp hơn gần nhất phía trên)")
    path: list[str] = Field(default_factory=list, description="Tên các mục từ gốc đến chính nó")


class TocMeta(PipelineModel):
    warnings: list[str] = Field(default_factory=list, description="Cảnh báo khi đọc mục lục (trang lỗi, số trang đáng ngờ)")
    reason: str = Field(default="", description="Lý do LLM chọn các trang mục lục, hoặc 'do bạn nhập'")


class TocAuto(PipelineModel):
    """`toc.auto.json`: kết quả máy đọc mục lục, chưa áp override của người duyệt."""

    toc_pages: list[int] = Field(description="Các trang PDF là mục lục")
    pages_source: str = Field(default="", description="Ai chọn trang mục lục: llm | user")
    entries: list[TocEntry] = Field(description="Các mục theo thứ tự đọc")
    meta: TocMeta = Field(default_factory=TocMeta, description="Cảnh báo và lý do")


class TocDoc(PipelineModel):
    """`toc.json`: mục lục sau khi áp override, tính độ lệch trang và neo vào thân sách."""

    toc_pages: list[int] = Field(description="Các trang PDF là mục lục (bị bỏ khi chia đoạn)")
    pages_source: str = Field(default="", description="Ai chọn trang mục lục: llm | user")
    entries: list[TocEntry] = Field(description="Các mục đã có cây cha/con, trang PDF và neo")
    offset: int | None = Field(default=None, description="Số trang PDF = số trang in + offset; None = chưa xác định được")
    offset_info: dict[str, Any] = Field(default_factory=dict, description="Cách tính offset: source (auto | user), số phiếu bầu, số mục khớp")
    total_pages: int = Field(default=0, description="Số trang đang có trong tài liệu; 0 = chưa biết")
    anchored: int = Field(default=0, description="Số mục đã neo được vào dòng tiêu đề")
    warnings: list[str] = Field(default_factory=list, description="Cảnh báo cho người duyệt (chưa có offset, số trang đáng ngờ...)")


class TocNode(PipelineModel):
    """Một mục của mục lục dưới dạng điểm bắt đầu trong thân sách, dùng để chia đoạn."""

    id: str = Field(description="Mã mục (cùng `TocEntry.id`)")
    title: str = Field(description="Tên mục")
    level: int = Field(description="Cấp mục 0-3")
    kind: str = Field(description="part | section | topic | sub")
    page: int = Field(description="Trang PDF nơi mục bắt đầu")
    line: int = Field(description="Dòng bắt đầu trong trang; -1 = chỉ biết trang, chưa neo được dòng")
    anchored: bool = Field(description="True = `line` là dòng tiêu đề thật")
    printed_page: int | None = Field(description="Số trang in của mục")
    suspect: bool = Field(description="True = mục cần kiểm tra")
    parent_id: str | None = Field(default=None, description="Mã mục cha trong danh sách còn lại")
    path: list[str] = Field(default_factory=list, description="Tên các mục từ gốc đến chính nó")
    page_hint: list[int] = Field(default_factory=list, description="[trang đầu, trang cuối] của mục theo mục lục")


class ChunkUnit(PipelineModel):
    """Một khối chữ nhỏ nhất khi chia đoạn: tiêu đề mục hoặc một đoạn chữ thuộc mục."""

    node: TocNode = Field(description="Mục chứa khối chữ")
    page: int = Field(description="Trang PDF của khối")
    text: str = Field(description="Chữ của khối; tiêu đề mục có tiền tố '#' theo cấp")
    heading: bool = Field(description="True = khối là tiêu đề mục")
