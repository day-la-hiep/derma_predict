def index_report_sync(
    self,
    report: FinalizeReport,
    profile: PatientProfile | None = None,
    images: list[tuple[Any, Any]] | None = None,
) -> None:
    """Đồng bộ một ca bệnh vào Qdrant (dùng trong script hoặc thread đồng bộ)."""
    self.ensure_collection()
    text, payload = self.build_report_text(report, profile, images=images)
    vectors, _, _ = self._embedding.embed([text])
    dense_vec = vectors[0]
    sparse_vec = encode_document(text, "mixed")

    point = PointStruct(
        id=self.point_id(report.id),
        vector={"": dense_vec, SPARSE_NAME: sparse_vec},
        payload=payload,
    )
    self._qdrant.upsert_points_sync(self._collection, [point])
