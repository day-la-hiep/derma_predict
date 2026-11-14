from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage

from app.infra.llm import get_model

_SYSTEM = """Dịch nhãn dữ kiện lâm sàng da liễu tiếng Việt sang tên tiếng Anh y khoa chuẩn để tra trong đồ thị tri thức. Chỉ gọi hàm, không viết văn bản.

Theo loại của từng nhãn:
* effect/phenotype: tên triệu chứng / dấu hiệu / tổn thương theo HPO, chữ thường, vd 'ngứa' → 'pruritus', 'mụn nước' → 'vesicle', 'ban đỏ' → 'erythema', 'sốt' → 'fever'.
* disease: tên bệnh y khoa chuẩn (MONDO), vd 'chàm' → 'eczema', 'vảy nến' → 'psoriasis'.
* drug: tên hoạt chất generic tiếng Anh (DrugBank), vd 'panadol' → 'acetaminophen', không ghi dạng bào chế hay hàm lượng.
* exposure: tên hoá chất / chất tiếp xúc tiếng Anh (CTD), vd 'niken' → 'nickel'.
* dermo: tên bệnh da liễu theo DermO.
Không chắc chắn hoặc nhãn không phải thuật ngữ y khoa thì để `en` rỗng. Không suy diễn thêm nghĩa."""


class _Translation(BaseModel):
    label: str = Field(description="Nhãn đúng nguyên văn như đầu vào")
    en: str = Field(default="", description="Tên tiếng Anh chuẩn; rỗng nếu không chắc")


class _Translations(BaseModel):
    items: list[_Translation] = Field(default_factory=lambda: list[_Translation]())


_CHOOSE_SYSTEM = """Chọn nút đồ thị tri thức có CÙNG NGHĨA y khoa với nhãn dữ kiện của người bệnh. Chỉ gọi hàm, không viết văn bản.

Mỗi mục có số thứ tự `item` (từ 1) kèm danh sách ứng viên đánh số từ 0. Trả MỖI mục một dòng: `index` là số của ứng viên đúng nghĩa, -1 nếu không ứng viên nào đúng nghĩa. Chỉ chọn khi cùng khái niệm (vd 'mụn nước' ↔ 'Skin vesicle', 'loét da' ↔ 'Skin ulcer', 'chàm' ↔ 'atopic eczema', 'penicillin' ↔ 'Benzylpenicillin'); ứng viên chỉ là trường hợp hẹp hơn, rộng hơn hoặc ở cơ quan khác (vd 'Oral ulcer' cho 'trợt da', 'Pulmonary bulla' cho 'bọng nước') thì -1. Không suy diễn."""


class _Choice(BaseModel):
    item: int = Field(description="Số thứ tự của mục như đầu vào (từ 1)")
    index: int = Field(default=-1, description="Số ứng viên đúng nghĩa; -1 nếu không có")


class _Choices(BaseModel):
    items: list[_Choice] = Field(default_factory=lambda: list[_Choice]())


async def choose_candidates(items: list[tuple[str, str, list[str]]]) -> dict[int, int]:
    """Một lần gọi LLM cho cả lô; trả {vị trí mục trong `items` (từ 0): số ứng viên} chỉ gồm mục có ứng viên đúng nghĩa."""
    blocks = "\n".join(
        f"item {n}: {label} (loại: {object_type})\n" + "\n".join(f"    {i}: {name}" for i, name in enumerate(names))
        for n, (label, object_type, names) in enumerate(items, 1)
    )
    model = get_model().with_structured_output(_Choices, method="function_calling")
    result = await model.ainvoke([SystemMessage(content=_CHOOSE_SYSTEM), HumanMessage(content=f"Các mục và ứng viên:\n{blocks}")])
    assert isinstance(result, _Choices)
    return {c.item - 1: c.index for c in result.items if 1 <= c.item <= len(items) and 0 <= c.index < len(items[c.item - 1][2])}


async def translate_labels(items: list[tuple[str, str]]) -> dict[str, str]:
    """Một lần gọi LLM cho cả lô nhãn; trả {nhãn: tên tiếng Anh} chỉ gồm nhãn dịch được."""
    lines = "\n".join(f"- {label} (loại: {object_type})" for label, object_type in items)
    model = get_model().with_structured_output(_Translations, method="function_calling")
    result = await model.ainvoke([SystemMessage(content=_SYSTEM), HumanMessage(content=f"Nhãn cần dịch:\n{lines}")])
    assert isinstance(result, _Translations)
    wanted = {label for label, _ in items}
    return {t.label: t.en.strip().lower() for t in result.items if t.label in wanted and t.en.strip()}
