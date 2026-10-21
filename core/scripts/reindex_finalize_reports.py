"""Nạp lại mọi báo cáo kết luận vào Qdrant (cần sau khi đổi tên collection `derma_medical_cases` → `derma_finalize_reports`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.api.deps import get_finalize_report_index_service, get_postgres_client  # noqa: E402
from app.models.file import File  # noqa: E402
from app.models.finalize_report import FinalizeReport, PatientImage  # noqa: E402
from app.models.patient_profile import PatientProfile  # noqa: E402


def main() -> None:
    index = get_finalize_report_index_service()
    with get_postgres_client().sync_session_factory() as s:
        for report in s.scalars(select(FinalizeReport)):
            profile = s.get(PatientProfile, report.patient_profile_id)
            images = list(
                s.execute(
                    select(PatientImage, File)
                    .join(File, File.id == PatientImage.file_id)
                    .where(PatientImage.finalize_report_id == report.id)
                ).tuples()
            )
            index.index_report_sync(report, profile, images)
            print(f"đã nạp {report.id}")


if __name__ == "__main__":
    main()
