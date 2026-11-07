def build_report_text(
    self,
    report: FinalizeReport,
    profile: PatientProfile | None = None,
    images: list[tuple[Any, Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Tổng hợp thông tin ca bệnh lâm sàng (đã ẩn danh họ tên, sđt) thành văn bản để embedding và payload."""
    snapshot = report.snapshot or {}
    # ... (ghép giới tính, tuổi, tiền sử, dị ứng, dữ kiện lâm sàng, nhận định, dặn dò, nhãn ảnh thành các dòng văn bản)
    text = "\n".join(lines)

    payload: dict[str, Any] = {
        "case_id": report.id,
        "diagnosis": report.diagnosis,
        "notes": report.notes or "",
        "gender": gender,
        "age": age,
        "allergies": allergies,
        "medical_history": medical_history,
        "clinical_facts": facts,
        "reasoning": reasoning,
        "urgency": urgency,
        "instructions": instructions,
        "is_reference_case": bool(report.is_reference_case),
        "text": text,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "images": image_infos,
    }
    return text, payload
