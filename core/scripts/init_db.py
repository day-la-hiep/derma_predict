"""Khởi tạo dữ liệu cho môi trường mới"""
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # chạy được từ `core/` mà không cần cài package

from alembic.config import Config  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.api.deps import get_document_file_store, get_file_store_service, get_postgres_client  # noqa: E402
from app.config.security import hash_password  # noqa: E402
from app.models.admin import Admin  # noqa: E402
from app.models.clinical import ClinicalFact, ClinicalProvenance  # noqa: E402
from app.models.doctor import Doctor  # noqa: E402
from app.models.episode import AiHypothesis, ClinicalEpisode  # noqa: E402
from app.models.document import Document, DocumentOverride, DocumentStage  # noqa: E402
from app.models.file import File  # noqa: E402
from app.models.finalize_report import FinalizeReport  # noqa: E402
from app.models.patient_profile import PatientProfile  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.visit import Appointment, Encounter  # noqa: E402

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
     "relationship": "parent"},
]
# dị ứng / tiền sử mẫu là fact dài hạn (bệnh nhân tự khai) để màn hồ sơ và thẻ bệnh nhân của bác sĩ có dữ liệu khi demo
LONG_TERM_FACTS = [
    ("pp-user-1-self", "allergy", "Penicillin"),
    ("pp-user-1-self", "history", "Viêm da cơ địa mạn tính"),
    ("pp-user-1-parent", "history", "Tăng huyết áp"),
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


def _days(n: float) -> datetime:
    return datetime.now(UTC) + timedelta(days=n)


# Đợt bệnh mẫu cho luồng đặt lịch → khám → chốt (ca demo):
#   ep-self-face   mở, có giả thuyết, chưa có lịch   → bệnh nhân đặt lịch được
#   ep-self-foot   mở, chưa có giả thuyết            → KHÔNG đặt được (ca F)
#   ep-spouse-body mở, lịch đã xác nhận ngày mai     → bác sĩ bấm "Bắt đầu khám"
#   ep-child-arm   mở, lịch đang chờ xác nhận        → bác sĩ xác nhận / đổi đợt / huỷ
#   ep-parent-face đã chốt (đã khám, có kết luận)    → xem lịch sử, chỉ số top-1
EPISODES = [
    {"id": "ep-self-face", "patient_profile_id": "pp-user-1-self", "body_site": "dau_mat", "status": "open",
     "opened_at": _days(-3), "updated_at": _days(-1)},
    {"id": "ep-self-foot", "patient_profile_id": "pp-user-1-self", "body_site": "ban_chan", "status": "open",
     "opened_at": _days(-1), "updated_at": _days(-1)},
    {"id": "ep-spouse-body", "patient_profile_id": "pp-user-1-spouse", "body_site": "than_truoc", "status": "open",
     "opened_at": _days(-5), "updated_at": _days(-2)},
    {"id": "ep-child-arm", "patient_profile_id": "pp-user-1-child", "body_site": "tay", "status": "open",
     "opened_at": _days(-2), "updated_at": _days(-1)},
    {"id": "ep-parent-face", "patient_profile_id": "pp-user-1-parent", "body_site": "dau_mat", "status": "closed",
     "opened_at": _days(-20), "updated_at": _days(-12), "closed_at": _days(-12)},
]
# (episode, hạng, mã, tên bệnh, độ tin cậy, điều còn thiếu)
HYPOTHESES = [
    ("ep-self-face", 1, "Eczema", "Viêm da cơ địa", "cao", ["Tiền sử gia đình dị ứng"]),
    ("ep-self-face", 2, "Rosacea", "Trứng cá đỏ", "thấp", ["Có đỏ mặt khi nóng / uống rượu không"]),
    ("ep-spouse-body", 1, "Tinea", "Nấm da thân", "cao", ["Soi tươi cạo vảy"]),
    ("ep-spouse-body", 2, "Eczema", "Chàm đồng tiền", "vừa", []),
    ("ep-child-arm", 1, "DrugEruption", "Dị ứng thuốc / phát ban", "vừa", ["Thuốc đã dùng 48 giờ qua"]),
    ("ep-child-arm", 2, "Infestations_Bites", "Côn trùng đốt", "thấp", []),
    ("ep-parent-face", 1, "Actinic_Keratosis", "Dày sừng ánh sáng", "vừa", ["Sinh thiết"]),
    ("ep-parent-face", 2, "SkinCancer", "Ung thư da", "thấp", []),
]
# (episode, loại, nhãn, chi tiết, trích lời bệnh nhân)
EPISODE_FACTS = [
    ("ep-self-face", "symptom", "Ngứa", "Ngứa má hai bên, nhiều về đêm", "Em bị ngứa hai bên má, đêm ngứa nhiều hơn"),
    ("ep-self-face", "lesion", "Da đỏ khô", "Má hai bên, bong vảy mịn", "Da má đỏ, khô và bong vảy"),
    ("ep-self-foot", "symptom", "Ngứa kẽ chân", "", "Kẽ ngón chân ngứa mấy hôm nay"),
    ("ep-spouse-body", "lesion", "Mảng đỏ hình vòng", "Hông trái, bờ gồ có vảy", "Có mảng tròn đỏ ở hông, giữa lành"),
    ("ep-spouse-body", "symptom", "Ngứa", "Tăng khi ra mồ hôi", "Ra mồ hôi là ngứa hơn"),
    ("ep-child-arm", "lesion", "Sẩn phù", "Hai cẳng tay, nổi sau bữa trưa", "Bé nổi mẩn đỏ ở tay sau khi ăn"),
    ("ep-parent-face", "lesion", "Mảng sần thô", "Gò má phải, ~1 cm", "Có mảng thô ráp ở má"),
    ("ep-parent-face", "symptom", "Ngứa nhẹ", "", "Thỉnh thoảng hơi ngứa"),
]
# (id lịch, đợt, trạng thái, bác sĩ, lệch ngày, lý do)
APPOINTMENTS = [
    ("ap-spouse-body", "ep-spouse-body", "confirmed", "doctor-1", 1, "Mảng đỏ ở hông không hết"),
    ("ap-child-arm", "ep-child-arm", "requested", None, 2, "Bé nổi mẩn sau khi ăn"),
    ("ap-parent-face", "ep-parent-face", "done", "doctor-1", -14, "Mảng thô ở má"),
]


def _seed_visits(s: Session) -> list[str]:
    created: list[str] = []
    now = datetime.now(UTC)
    for e in EPISODES:
        if s.get(ClinicalEpisode, e["id"]) is None:
            s.add(ClinicalEpisode(**e))
            created.append(f"episode {e['id']}")
    s.flush()
    for ep, rank, code, disease, conf, missing in HYPOTHESES:
        hid = f"h-{ep}-{rank}"
        if s.get(AiHypothesis, hid) is None:
            s.add(AiHypothesis(id=hid, episode_id=ep, rank=rank, diagnosis_code=code, disease=disease, confidence=conf,
                               evidence=[{"source": "guideline", "text": f"Mô tả phù hợp {disease}"}], missing=missing))
            created.append(f"hypothesis {hid}")
    for i, (ep, ftype, label, detail, quote) in enumerate(EPISODE_FACTS):
        fid = f"f-{ep}-{i}"
        if s.get(ClinicalFact, fid) is None:
            profile_id = next(e["patient_profile_id"] for e in EPISODES if e["id"] == ep)
            s.add(ClinicalFact(id=fid, patient_profile_id=profile_id, episode_id=ep, fact_type=ftype, label=label,
                               detail=detail, created_at=now, updated_at=now))
            s.flush()
            s.add(ClinicalProvenance(fact_id=fid, kind="chat", quote=quote, detail=detail, created_at=now))
            created.append(f"fact {fid}")
    s.flush()
    for aid, ep, status, doctor, offset, reason in APPOINTMENTS:
        if s.get(Appointment, aid) is None:
            profile_id = next(e["patient_profile_id"] for e in EPISODES if e["id"] == ep)
            s.add(Appointment(id=aid, patient_profile_id=profile_id, episode_id=ep, doctor_id=doctor,
                              scheduled_at=_days(offset), status=status, reason=reason, created_at=_days(offset - 1)))
            created.append(f"appointment {aid}")
    s.flush()
    # lần khám đã chốt của đợt `ep-parent-face`: kết luận khác giả thuyết top-1 để chỉ số top-3 có ca "trượt top-1, trúng top-3"
    if s.get(Encounter, "enc-parent-face") is None:
        s.add(Encounter(id="enc-parent-face", appointment_id="ap-parent-face", patient_profile_id="pp-user-1-parent",
                        doctor_id="doctor-1", status="closed", opened_at=_days(-12), closed_at=_days(-12)))
        s.flush()
        snap = _snapshot(
            "pp-user-1-parent",
            "Mảng sần thô, dính, trên nền da tổn thương do nắng ở gò má — nghi dày sừng ánh sáng, cần theo dõi.",
            "few_days",
            ["Bôi kem chống nắng mỗi ngày.", "Tái khám sau 3 tháng, sinh thiết nếu mảng dày lên hoặc loét."],
            [
                ("lesion", "Mảng sần thô", "Gò má phải, ~1 cm, dính", "doctor_corrected"),
                ("symptom", "Ngứa nhẹ", "", "patient_reported"),
            ],
        )
        snap["removed_facts"] = []
        s.add(FinalizeReport(
            id="mr-parent-face", patient_profile_id="pp-user-1-parent", doctor_id="doctor-1", encounter_id="enc-parent-face",
            diagnosis="Dày sừng ánh sáng", diagnosis_code="Actinic_Keratosis", is_reference_case=True,
            notes="Chống nắng, tái khám sau 3 tháng.", created_at=_days(-12), snapshot=snap,
        ))
        # fact của đợt đã chốt được bác sĩ xác nhận
        for fid in ("f-ep-parent-face-6", "f-ep-parent-face-7"):
            fact = s.get(ClinicalFact, fid)
            if fact is not None:
                fact.verified_at, fact.verified_by_id = _days(-12), "doctor-1"
                s.add(ClinicalProvenance(fact_id=fid, kind="doctor", doctor_id="doctor-1", encounter_id="enc-parent-face",
                                         quote=fact.label, detail=fact.detail, created_at=_days(-12)))
        created.append("encounter enc-parent-face + finalize_report mr-parent-face")
    s.commit()
    return created


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
            s.add(PatientProfile(id=pid, user_id=owner, full_name=u["full_name"], dob=u["dob"], gender=u["gender"]))
            created.append(f"patient_profile {pid}")
    for p in FAMILY_PROFILES:
        if s.get(PatientProfile, p["id"]) is None:
            s.add(PatientProfile(**p))
            created.append(f"patient_profile {p['id']}")
    s.flush()
    now = datetime.now(UTC)
    for pid, fact_type, label in LONG_TERM_FACTS:
        exists = s.scalar(select(ClinicalFact.id).where(
            ClinicalFact.patient_profile_id == pid, ClinicalFact.episode_id.is_(None),
            ClinicalFact.fact_type == fact_type, func.lower(ClinicalFact.label) == label.lower(),
        ))
        if exists is None:
            fact = ClinicalFact(patient_profile_id=pid, fact_type=fact_type, label=label, detail="", created_at=now, updated_at=now)
            s.add(fact)
            s.flush()
            s.add(ClinicalProvenance(fact_id=fact.id, kind="profile", quote=label, created_at=now))
            created.append(f"clinical_fact {pid}/{fact_type}/{label}")
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
        created = _seed(s) + _seed_visits(s) + _restore_documents(s)
    print("Đã tạo: " + ", ".join(created) if created else "Dữ liệu mẫu đã có sẵn, không tạo thêm.")


if __name__ == "__main__":
    main()
