def split_node_id(node_id: str) -> tuple[str, str]:
    """`"effect/phenotype:123"` → `("effect/phenotype", "123")`; DermO `"dermo:DERMO:1"` → `("dermo", "DERMO:1")`."""
    kind, _, raw = node_id.partition(":")
    return kind, raw


def to_node_ref(node_id: str) -> dict[str, str] | None:
    """Dạng `{type, id}` cho endpoint knowledge; node DermO không thuộc PrimeKG nên None."""
    kind, raw = split_node_id(node_id)
    return {"type": kind, "id": raw} if raw and kind in ("effect/phenotype", "disease", "drug", "exposure") else None


def to_mondo(disease_id: str) -> str | None:
    """Node bệnh PrimeKG nguồn MONDO có id là số MONDO; node gộp nhiều bệnh (id có `_`) thì không đổi được."""
    kind, raw = split_node_id(disease_id)
    return f"MONDO:{int(raw):07d}" if kind == "disease" and raw.isdigit() else None
