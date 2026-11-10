"""Trích thực thể y khoa từ câu hỏi (dịch sang tên PrimeKG tiếng Anh) cho nhánh KG và mở rộng query BM25"""

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agent.common.llm import get_model

_EXTRACT_SYSTEM = (
    "Trích xuất các thực thể y khoa DA LIỄU (tên bệnh, triệu chứng, thuốc) được nhắc "
    "tới trong câu hỏi của người dùng. Dịch mỗi thực thể sang tên tiếng Anh y khoa chuẩn "
    "(dữ liệu tra cứu gốc là tiếng Anh, vd 'nổi mề đay' -> 'urticaria', 'da tôi đỏ và "
    "ngứa' -> 2 thực thể 'erythema' và 'pruritus'). CHỈ trích xuất thực thể RÕ RÀNG có "
    "trong câu hỏi — không suy đoán, không bổ sung thực thể không được nhắc tới. Nếu câu "
    "hỏi không chứa thực thể y khoa nào, trả về danh sách rỗng. Với mỗi thực thể, điền thêm tên "
    "tiếng Việt chuẩn trong sách giáo khoa da liễu (`vi`) để khớp từ khoá ở sách tiếng Việt."
)


class ExtractedEntity(BaseModel):
    text: str = Field(
        description="Tên bệnh/triệu chứng/thuốc bằng tiếng Anh y khoa chuẩn, dịch từ "
        "câu hỏi gốc nếu cần"
    )
    vi: str = Field(default="", description="Tên tiếng Việt chuẩn của thực thể (rỗng nếu không có)")
    type: Literal["disease", "symptom", "drug", "other"]


class ExtractedEntities(BaseModel):
    entities: list[ExtractedEntity] = Field(
        default_factory=lambda: list[ExtractedEntity]()
    )


async def extract_entities(query: str) -> list[ExtractedEntity]:
    # `method="function_calling"` bắt buộc — mặc định (tự chọn theo model, thường ngả
    # về "json_schema" strict) làm proxy OpenRouter cho model hiện dùng
    # (`nvidia/nemotron-3-super-120b-a12b:free`, xem `app/config/settings.py::AGENT_MODEL`)
    # trả response rỗng/`choices=None`, khiến `openai` SDK crash lúc parse
    # (`TypeError: 'NoneType' object is not iterable`) — đã verify "function_calling"
    # chạy ổn định với model này.
    model = get_model().with_structured_output(
        ExtractedEntities, method="function_calling"
    )
    result = await model.ainvoke(
        [SystemMessage(content=_EXTRACT_SYSTEM), HumanMessage(content=query)]
    )
    assert isinstance(result, ExtractedEntities)
    return list(result.entities)
