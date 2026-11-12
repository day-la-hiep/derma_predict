class ExtractedFact(BaseModel):
    template_label: str = Field(description="Ten ngan cua du kien (toi da 8 tu)")
    fact_type: FactType            # symptom, lesion, history, medication, allergy, other
    detail: str = Field(description="Chi tiet theo loi nguoi benh (toi da 25 tu)")
    body_site: str = Field(default="", description="Vung da; rong neu chua ro hoac la history/medication/allergy")
    source_messages: list[int] = Field(default_factory=list)


class ExtractedFacts(BaseModel):
    facts: list[ExtractedFact] = Field(default_factory=list)


def validate_facts_evidence(raw_facts, messages_content):
    valid_facts = []
    total_messages = len(messages_content)
    for rf in raw_facts:
        source_indices = rf.get("source_messages") or []
        valid_indices = [i for i in source_indices
                        if isinstance(i, int) and 1 <= i <= total_messages]
        if valid_indices:
            source_text = " ".join(messages_content[i - 1] for i in valid_indices)
            source_tokens = tokenize(source_text)
            fact_tokens = tokenize(f"{rf.get('template_label','')} {rf.get('detail','')}")
            if fact_tokens and source_tokens and len(fact_tokens & source_tokens) == 0:
                logger.warning("Fact khong khop tu khoa voi tin nhan nguon")
        rf["source_messages"] = valid_indices
        rf["detail"] = str(rf.get("detail", "")).strip()[:DETAIL_MAX_CHARS]
        valid_facts.append(rf)
    return valid_facts
