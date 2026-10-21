"""Khởi tạo dữ liệu cho môi trường mới"""
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # chạy được từ `core/` mà không cần cài package

from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_document_file_store, get_file_store_service, get_postgres_client  # noqa: E402
from app.config.security import hash_password  # noqa: E402
from app.models.admin import Admin  # noqa: E402
from app.models.doctor import Doctor  # noqa: E402
from app.models.document import Document, DocumentOverride, DocumentStage  # noqa: E402
from app.models.file import File  # noqa: E402
from app.models.finalize_report import FinalizeReport  # noqa: E402
from app.models.patient_profile import PatientProfile  # noqa: E402
from app.models.user import User  # noqa: E402

# id cố định: FE hard-code `user-1`; hồ sơ `pp-<user_id>-self` cùng quy ước với migration `align_schema_with_base`.
# Giá trị của `user-1` PHẢI khớp `USER_1` trong migration đó.
DEFAULT_PASSWORD_HASH = hash_password("123456")

USERS = [
    {"id": "user-1", "username": "user-1", "full_name": "Nguyễn Văn An", "dob": date(1995, 5, 20), "gender": "male", "password_hash": DEFAULT_PASSWORD_HASH},
    {"id": "doctor-1", "username": "doctor-1", "full_name": "BS. Trần Thị Bình", "dob": date(1982, 3, 14), "gender": "female", "password_hash": DEFAULT_PASSWORD_HASH},
    {"id": "admin-1", "username": "admin-1", "full_name": "Quản trị viên", "dob": date(1990, 1, 1), "gender": "male", "password_hash": DEFAULT_PASSWORD_HASH},
]
DOCTORS = [{"user_id": "doctor-1", "description": "Bác sĩ chuyên khoa Da liễu (dữ liệu mẫu)."}]
ADMINS = [{"user_id": "admin-1"}]
DOCUMENTS_SEED = Path(__file__).with_name("seed_documents.json")  # sinh bằng `export_documents_seed.py`
PROFILE_OWNERS = ["user-1"]  # tài khoản bệnh nhân cần hồ sơ "chính mình" để tạo hội thoại
# hồ sơ người nhà của `user-1` — để màn Lịch sử khám của bác sĩ có nhiều bệnh nhân khi demo
FAMILY_PROFILES = [
    {"id": "pp-user-1-spouse", "user_id": "user-1", "full_name": "Phạm Thu Hà", "dob": date(1981, 6, 2), "gender": "female",
     "relationship": "spouse"},
    {"id": "pp-user-1-child", "user_id": "user-1", "full_name": "Nguyễn Minh Khôi", "dob": date(2018, 4, 11), "gender": "male",
     "relationship": "child"},
    {"id": "pp-user-1-parent", "user_id": "user-1", "full_name": "Đỗ Lan Anh", "dob": date(1974, 9, 9), "gender": "female",
     "relationship": "parent", "medical_history": "Tăng huyết áp"},
]


def _snapshot(profile_id: str, reasoning: str, urgency: str, instructions: list[str], facts: list[tuple[str, str, str, str]]) -> dict:
    """`FinalizeReportSnapshot` mẫu; fact = (fact_type, label, detail, origin). Dữ liệu mẫu không có tin nhắn nguồn."""
    if profile_id == "pp-user-1-self":
        u = next(x for x in USERS if x["id"] == "user-1")
        p = {"full_name": u["full_name"], "dob": u["dob"], "gender": u["gender"], "relationship": "self",
             "allergies": "Penicillin", "medical_history": "Viêm da cơ địa mạn tính"}
    else:
        p = next(x for x in FAMILY_PROFILES if x["id"] == profile_id)
    return {
        "patient_profile": {
            "full_name": p["full_name"], "dob": p["dob"].isoformat(), "gender": p["gender"],
            "relationship": p.get("relationship", "self"), "phone": None,
            "allergies": p.get("allergies", ""), "medical_history": p.get("medical_history", ""),
        },
        "assessment": {"reasoning": reasoning, "urgency": urgency, "instructions": instructions},
        "clinical_facts": [
            {"fact_type": t, "label": label, "detail": detail, "origin": origin, "provenances": []}
            for t, label, detail, origin in facts
        ],
    }


# báo cáo kết luận mẫu (đã chốt) cho màn "Kết luận" của bệnh nhân và màn "Lịch sử khám" của bác sĩ
FINALIZE_REPORTS = [
    {
        "id": "mr-user-1-1",
        "patient_profile_id": "pp-user-1-self",
        "doctor_id": "doctor-1",
        "diagnosis": "Viêm da cơ địa (chàm thể tạng) mức độ nhẹ",
        "notes": "Ngứa nhiều về đêm, mảng da khô ở khuỷu tay. Dưỡng ẩm 2 lần/ngày, tránh xà phòng mạnh; tái khám sau 4 tuần.",
        "created_at": datetime(2026, 8, 3, 9, 30, tzinfo=UTC),
        "snapshot": _snapshot(
            "pp-user-1-self",
            "Mảng da khô, ngứa nhiều về đêm ở nếp gấp khuỷu, tiền sử cơ địa — phù hợp chàm thể tạng mức nhẹ.",
            "monitor",
            ["Dưỡng ẩm 2 lần/ngày.", "Tránh xà phòng mạnh, tắm nước ấm.", "Tái khám sau 4 tuần."],
            [
                ("symptom", "Ngứa", "Ngứa nhiều về đêm", "patient_reported"),
                ("lesion", "Da khô bong vảy", "Mảng da khô ở nếp gấp khuỷu tay hai bên", "doctor_observed"),
            ],
        ),
    },
    {
        "id": "mr-user-1-2",
        "patient_profile_id": "pp-user-1-self",
        "doctor_id": "doctor-1",
        "diagnosis": "Viêm da cơ địa — tái khám, cải thiện",
        "notes": "Giảm ngứa, da bớt khô. Tiếp tục dưỡng ẩm, hẹn tái khám khi có đợt bùng phát.",
        "created_at": datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        "snapshot": _snapshot(
            "pp-user-1-self",
            "Sau 4 tuần dưỡng ẩm, tổn thương thu nhỏ, ngứa giảm rõ — đáp ứng tốt.",
            "monitor",
            ["Tiếp tục dưỡng ẩm hằng ngày.", "Tái khám khi có đợt bùng phát."],
            [("symptom", "Ngứa", "Giảm rõ so với lần khám trước", "doctor_corrected")],
        ),
    },
    {
        "id": "mr-user-1-3",
        "patient_profile_id": "pp-user-1-self",
        "doctor_id": "doctor-1",
        "diagnosis": "Nghi vảy nến mảng",
        "notes": "Cần khám trực tiếp tại da liễu để xác định; có thể cần soi tươi cạo vảy để loại trừ nấm da.",
        "created_at": datetime(2026, 10, 12, 13, 52, tzinfo=UTC),
        "snapshot": _snapshot(
            "pp-user-1-self",
            "Mảng đỏ giới hạn rõ, vảy trắng bạc ở mặt duỗi khuỷu và gối, phân bố đối xứng, kéo dài 3 tháng.",
            "few_days",
            ["Chăm sóc tạm thời: dưỡng ẩm thường xuyên, tránh cào gãi.", "Không tự bôi thuốc corticoid mạnh kéo dài.",
             "Đi khám sớm nếu tổn thương lan nhanh, kèm sốt hoặc đau khớp nhiều."],
            [
                ("lesion", "Mảng đỏ có vảy", "Ranh giới rõ, vảy trắng bạc, dễ bong", "patient_reported"),
                ("lesion", "Vị trí tổn thương", "Khuỷu tay và đầu gối, đối xứng hai bên", "patient_reported"),
                ("history", "Thời gian khởi phát", "Khoảng 3 tháng", "patient_reported"),
                ("lesion", "Dấu hiệu Auspitz", "Dương tính khi cạo vảy", "doctor_observed"),
            ],
        ),
    },
    {
        "id": "mr-user-1-4",
        "patient_profile_id": "pp-user-1-spouse",
        "doctor_id": "doctor-1",
        "diagnosis": "Nghi nấm da thân",
        "notes": "Bôi thuốc kháng nấm tại chỗ 2 tuần, giữ vùng da khô thoáng.",
        "created_at": datetime(2026, 10, 11, 9, 15, tzinfo=UTC),
        "snapshot": _snapshot(
            "pp-user-1-spouse",
            "Mảng đỏ hình vòng, bờ nổi gồ có vảy, lành ở giữa, ngứa nhiều khi ra mồ hôi.",
            "few_days",
            ["Giữ vùng da khô, mặc đồ thoáng.", "Không dùng chung khăn tắm."],
            [
                ("lesion", "Mảng đỏ hình vòng", "Bờ gồ, có vảy, lành ở giữa — vùng hông trái", "doctor_corrected"),
                ("symptom", "Ngứa", "Tăng khi ra mồ hôi", "patient_reported"),
            ],
        ),
    },
    {
        "id": "mr-user-1-5",
        "patient_profile_id": "pp-user-1-child",
        "doctor_id": "doctor-1",
        "diagnosis": "Nghi mề đay cấp",
        "notes": "Theo dõi tại nhà, ghi lại thức ăn trong 24 giờ trước khi nổi.",
        "created_at": datetime(2026, 10, 9, 19, 40, tzinfo=UTC),
        "snapshot": _snapshot(
            "pp-user-1-child",
            "Sẩn phù rải rác, tự hết trong vài giờ, không khó thở, không phù môi — mề đay cấp chưa có dấu hiệu nặng.",
            "monitor",
            ["Theo dõi tại nhà.", "Đưa đi cấp cứu ngay nếu khó thở, phù môi hoặc mí mắt."],
            [
                ("lesion", "Sẩn phù", "Rải rác thân mình, tự hết trong vài giờ", "patient_reported"),
                ("other", "Phân loại ảnh", "Mô hình gợi ý mề đay", "ai_inferred"),
            ],
        ),
    },
    {
        "id": "mr-user-1-6",
        "patient_profile_id": "pp-user-1-parent",
        "doctor_id": "doctor-1",
        "diagnosis": "Nghi ung thư biểu mô tế bào đáy",
        "notes": "Chuyển khám da liễu trực tiếp và sinh thiết trong tuần.",
        "created_at": datetime(2026, 10, 8, 8, 20, tzinfo=UTC),
        "snapshot": _snapshot(
            "pp-user-1-parent",
            "Nốt bóng như ngọc trai, giãn mạch trên bề mặt, loét trung tâm, chảy máu khi chạm, lớn dần 6 tháng ở vùng mũi.",
            "emergency",
            ["Khám da liễu trực tiếp và sinh thiết sớm.", "Che nắng, tránh tự đắp thuốc lên tổn thương."],
            [
                ("lesion", "Nốt bóng có loét", "Cánh mũi phải, ~8 mm, loét trung tâm", "doctor_observed"),
                ("history", "Tiến triển", "Lớn dần trong 6 tháng, dễ chảy máu", "patient_reported"),
            ],
        ),
    },
]


def _restore_documents(s: Session) -> list[str]:
    """Khôi phục record tài liệu RAG đã có; chỉ DB — file MinIO và point Qdrant nằm ngoài Postgres nên không bị reset theo."""
    if not DOCUMENTS_SEED.exists():
        return []
    data = json.loads(DOCUMENTS_SEED.read_text(encoding="utf-8"))

    def _dt(row: dict) -> dict:
        return {k: datetime.fromisoformat(v) if k.endswith("_at") and isinstance(v, str) else v for k, v in row.items()}

    created: list[str] = []
    for d in data["documents"]:
        existing = s.get(Document, d["id"])
        if existing is not None:
            # Seed là nguồn đúng của cấu hình xử lý: ghi đè để sửa profile cũ (key thừa làm `Profile` validate lỗi).
            if existing.profile != d["profile"]:
                existing.profile = d["profile"]
                created.append(f"document {d['id']} (cập nhật profile)")
            continue
        for f in data["files"]:
            if f["id"] in (d["source_file_id"], d["ingested_file_id"]) and s.get(File, f["id"]) is None:
                s.add(File(**_dt(f)))
        s.flush()  # files phải có trước khi documents trỏ FK tới
        row = _dt(d)
        if row["uploaded_by_id"] and s.get(Doctor, row["uploaded_by_id"]) is None:
            row["uploaded_by_id"] = None
        s.add(Document(**row))
        s.flush()
        stage_ids = set()
        for st in data["document_stages"]:
            if st["document_id"] == d["id"]:
                s.add(DocumentStage(**_dt(st)))
                stage_ids.add(st["id"])
        s.flush()
        for o in data["document_overrides"]:
            if o["document_stage_id"] in stage_ids:
                s.add(DocumentOverride(**_dt(o)))
        created.append(f"document {d['id']}")
    s.commit()
    return created


def _check_migrated() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with get_postgres_client().sync_session_factory() as s:
        current = MigrationContext.configure(s.connection()).get_current_revision()
    if current != head:
        sys.exit(f"Database đang ở revision {current}, cần {head}. Chạy trước: cd core && uv run alembic upgrade head")


def _seed(s: Session) -> list[str]:
    created: list[str] = []
    for u in USERS:
        user_row = s.get(User, u["id"])
        if user_row is None:
            s.add(User(**u))
            created.append(f"user {u['id']}")
        elif user_row.password_hash is None and "password_hash" in u:
            user_row.password_hash = u["password_hash"]
            created.append(f"password for {u['id']}")
    s.flush()  # bảng con trỏ FK tới users
    for d in DOCTORS:
        if s.get(Doctor, d["user_id"]) is None:
            s.add(Doctor(**d))
            created.append(f"doctor {d['user_id']}")
    for a in ADMINS:
        if s.get(Admin, a["user_id"]) is None:
            s.add(Admin(**a))
            created.append(f"admin {a['user_id']}")
    for owner in PROFILE_OWNERS:
        pid = f"pp-{owner}-self"
        if s.get(PatientProfile, pid) is None:
            u = next(x for x in USERS if x["id"] == owner)
            # dị ứng/tiền sử mẫu để màn hồ sơ (bệnh nhân) và màn tư vấn (bác sĩ) có dữ liệu thật khi demo
            s.add(PatientProfile(
                id=pid, user_id=owner, full_name=u["full_name"], dob=u["dob"], gender=u["gender"],
                allergies="Penicillin" if owner == "user-1" else "",
                medical_history="Viêm da cơ địa mạn tính" if owner == "user-1" else "",
            ))
            created.append(f"patient_profile {pid}")
    for p in FAMILY_PROFILES:
        if s.get(PatientProfile, p["id"]) is None:
            s.add(PatientProfile(**p))
            created.append(f"patient_profile {p['id']}")
    s.flush()
    for r in FINALIZE_REPORTS:
        existing = s.get(FinalizeReport, r["id"])
        if existing is None:
            s.add(FinalizeReport(**r))
            created.append(f"finalize_report {r['id']}")
        elif existing.snapshot is None:
            # báo cáo kết luận mẫu tạo trước khi có cột snapshot: bổ sung, không đụng nội dung khác
            existing.snapshot = r["snapshot"]
            created.append(f"finalize_report {r['id']} (bổ sung snapshot)")
    s.commit()
    return created


def main() -> None:
    _check_migrated()
    for store in (get_file_store_service(), get_document_file_store()):
        store.ensure_bucket()
    with get_postgres_client().sync_session_factory() as s:
        created = _seed(s) + _restore_documents(s)
    print("Đã tạo: " + ", ".join(created) if created else "Dữ liệu mẫu đã có sẵn, không tạo thêm.")


if __name__ == "__main__":
    main()
