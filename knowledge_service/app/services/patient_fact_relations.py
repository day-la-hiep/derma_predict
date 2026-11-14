from app.services.patient_fact_graph_service import DRUG, EXPOSURE, HISTORY, MORPHOLOGY, SYMPTOM, TRIGGER

# Quan hệ của fact bệnh nhân → loại cạnh PrimeKG dùng để mở rộng từ nút đã khớp (một chỗ duy nhất, test ở tests/test_patient_graph_context.py)
POSITIVE_PHENOTYPE = "DISEASE_PHENOTYPE_POSITIVE"
NEGATIVE_PHENOTYPE = "DISEASE_PHENOTYPE_NEGATIVE"


def get_expansion_relations(relation: str, present: bool = True) -> tuple[str, ...]:
    """Loại cạnh PrimeKG để đi tiếp từ nút của fact; fact phủ định ("không ngứa") đi cạnh `…NEGATIVE`; rỗng = không mở rộng."""
    if relation in (SYMPTOM, MORPHOLOGY):
        return (POSITIVE_PHENOTYPE,) if present else (NEGATIVE_PHENOTYPE,)
    if relation == DRUG:
        return ("INDICATION", "DRUG_EFFECT", "CONTRAINDICATION")
    if relation == HISTORY:
        return ("DISEASE_DISEASE",)
    if relation in (EXPOSURE, TRIGGER):
        return ("EXPOSURE_DISEASE",)
    return ()
