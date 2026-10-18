"""Schema graph được phép trích từ tài liệu"""
from dataclasses import dataclass
from typing import Literal

# Thêm loại thực thể / quan hệ mới: khai báo ở đây (prompt, khớp, nạp Neo4j và UI đều đọc từ bảng này).
# Quan hệ phải là loại đã có trong PrimeKG/DermO để template của agent (`kg_templates.py`) dùng được ngay.

KG = Literal["primekg", "dermo", "doc"]


@dataclass(frozen=True)
class EntityType:
    id: str  # giá trị `type` của nút `:Entity` (PrimeKG) hoặc "dermo"
    kg: KG
    label: str  # label phụ trong Neo4j (theo `load_primekg.py::to_label`)
    title: str
    hint: str  # mô tả cho LLM
    case_sensitive: bool = False  # ký hiệu gen (FLG, KRT5) so nguyên chữ


ENTITY_TYPES: dict[str, EntityType] = {e.id: e for e in [
    EntityType("disease", "primekg", "Disease", "Bệnh", "tên bệnh tiếng Anh y khoa chuẩn (MONDO)"),
    EntityType("effect/phenotype", "primekg", "EffectPhenotype", "Triệu chứng / dấu hiệu",
               "tên triệu chứng/dấu hiệu/tổn thương tiếng Anh theo HPO, vd 'pruritus', 'vesicle', 'erythema'"),
    EntityType("drug", "primekg", "Drug", "Thuốc", "tên hoạt chất tiếng Anh (DrugBank), vd 'mupirocin', không ghi dạng bào chế"),
    EntityType("exposure", "primekg", "Exposure", "Tác nhân tiếp xúc", "hoá chất/chất tiếp xúc tiếng Anh (CTD), vd 'nickel'"),
    EntityType("gene/protein", "primekg", "GeneProtein", "Gen / protein", "ký hiệu gen HGNC, vd 'FLG', 'KRT14'", case_sensitive=True),
    EntityType("dermo", "dermo", "DermoTerm", "Thuật ngữ DermO", "tên bệnh da liễu tiếng Anh theo DermO"),
]}


@dataclass(frozen=True)
class Relation:
    kg: KG
    type: str  # relationship type trong Neo4j
    display: str  # `display_relation` (giữ đúng như dữ liệu gốc)
    object_type: str  # loại thực thể của đầu còn lại (khác chủ đề của mục)
    topic_is_head: bool  # chiều cạnh: chủ đề -> đầu kia (True) hay đầu kia -> chủ đề


@dataclass(frozen=True)
class Slot:
    id: str  # khoá JSON LLM trả về
    topic: str  # loại chủ đề của mục sách mà ô này áp dụng ("disease" | "drug")
    hint: str
    relations: tuple[Relation, ...]  # một ô có thể ra cạnh ở cả PrimeKG lẫn DermO
    entity_hint: str = ""  # thay mô tả mặc định của loại thực thể khi ô cần cách ghi riêng


SLOTS: list[Slot] = [
    Slot("phenotypes_present", "disease", "triệu chứng, dấu hiệu, tổn thương CÓ ở bệnh",
         (Relation("primekg", "DISEASE_PHENOTYPE_POSITIVE", "phenotype present", "effect/phenotype", True),)),
    Slot("phenotypes_absent", "disease", "triệu chứng sách nói rõ KHÔNG có ở bệnh (vd 'không ngứa', 'không để lại sẹo')",
         (Relation("primekg", "DISEASE_PHENOTYPE_NEGATIVE", "phenotype absent", "effect/phenotype", True),),
         entity_hint="tên triệu chứng theo HPO KHÔNG kèm phủ định, vd 'không sốt' -> 'fever', 'không để lại sẹo' -> 'scarring'"),
    Slot("subtypes", "disease", "thể bệnh / dạng con của bệnh này (vd 'chốc bọng nước' là một thể của 'chốc')",
         (Relation("primekg", "DISEASE_DISEASE", "parent-child", "disease", True),
          Relation("dermo", "IS_A", "is a", "dermo", False))),
    Slot("drugs_indicated", "disease", "thuốc (hoạt chất) dùng điều trị bệnh; không ghi biện pháp không phải thuốc",
         (Relation("primekg", "INDICATION", "indication", "drug", False),)),
    Slot("drugs_off_label", "disease", "thuốc sách ghi rõ là dùng ngoài chỉ định cho bệnh",
         (Relation("primekg", "OFF_LABEL_USE", "off-label use", "drug", False),)),
    Slot("drugs_contraindicated", "disease", "thuốc chống chỉ định hoặc làm nặng bệnh",
         (Relation("primekg", "CONTRAINDICATION", "contraindication", "drug", False),)),
    Slot("exposures", "disease", "hoá chất / chất tiếp xúc gây hoặc làm nặng bệnh (vd nickel, chromate)",
         (Relation("primekg", "EXPOSURE_DISEASE", "linked to", "exposure", False),)),
    Slot("genes", "disease", "gen / protein liên quan (đột biến, cơ chế), ghi ký hiệu gen",
         (Relation("primekg", "DISEASE_PROTEIN", "associated with", "gene/protein", False),)),
    Slot("complications", "disease", "biến chứng / hậu quả bệnh gây ra",
         (Relation("dermo", "RESULTS_IN", "results in", "dermo", True),)),
    Slot("associated_diseases", "disease", "bệnh hay đi kèm / liên quan (không phải chẩn đoán phân biệt)",
         (Relation("dermo", "ASSOCIATED_WITH", "associated with", "dermo", True),)),
    Slot("side_effects", "drug", "tác dụng phụ / tác dụng không mong muốn của thuốc",
         (Relation("primekg", "DRUG_EFFECT", "side effect", "effect/phenotype", True),)),
    Slot("indications", "drug", "bệnh mà thuốc này được chỉ định",
         (Relation("primekg", "INDICATION", "indication", "disease", True),)),
    Slot("contraindications", "drug", "bệnh / tình trạng chống chỉ định dùng thuốc này",
         (Relation("primekg", "CONTRAINDICATION", "contraindication", "disease", True),)),
]
SLOT_BY_ID = {s.id: s for s in SLOTS}
TOPIC_TYPES = ("disease", "drug")

# Chủ đề loại X khớp vào những namespace nào (bệnh cần cả MONDO lẫn DermO vì ô của nó ra cạnh ở cả hai)
TOPIC_ENTITY_TYPES: dict[str, tuple[str, ...]] = {"disease": ("disease", "dermo"), "drug": ("drug",)}

# Thông tin sách có nhưng PrimeKG/DermO không có quan hệ tương ứng: chỉ thống kê, không nạp
UNMAPPED_KINDS = ("location", "risk_factor", "red_flag", "differential", "non_drug_treatment", "other")


def relation_types() -> list[str]:
    return sorted({r.type for s in SLOTS for r in s.relations})


def relation(kg: str, type_: str) -> Relation | None:
    return next((r for s in SLOTS for r in s.relations if r.kg == kg and r.type == type_), None)
