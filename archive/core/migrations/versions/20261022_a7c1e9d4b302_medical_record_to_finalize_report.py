"""medical_records -> finalize_reports (1 báo cáo / ca tư vấn)

Revision ID: a7c1e9d4b302
Revises: f385743f1afb
Create Date: 2026-10-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7c1e9d4b302'
down_revision: Union[str, Sequence[str], None] = 'f385743f1afb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tên cũ, tên mới) — đổi tên thay vì drop/create để giữ dữ liệu
CONSTRAINTS = [
    ('medical_records', 'pk_medical_records', 'pk_finalize_reports'),
    ('medical_records', 'fk_medical_records_doctor_id_doctors', 'fk_finalize_reports_doctor_id_doctors'),
    ('medical_records', 'fk_medical_records_patient_profile_id_patient_profiles',
     'fk_finalize_reports_patient_profile_id_patient_profiles'),
    ('medical_records', 'fk_medical_records_consultation_session_id_consultation_b217',
     'fk_finalize_reports_consultation_session_id_consultation_sessions'),
    ('patient_images', 'fk_patient_images_medical_record_id_medical_records',
     'fk_patient_images_finalize_report_id_finalize_reports'),
]
INDEXES = [
    ('ix_medical_records_patient_profile_id', 'ix_finalize_reports_patient_profile_id'),
    ('ix_patient_images_medical_record_id', 'ix_patient_images_finalize_report_id'),
]


def _new_table(table: str) -> str:
    return 'finalize_reports' if table == 'medical_records' else table


def upgrade() -> None:
    dup = op.get_bind().exec_driver_sql(
        "SELECT consultation_session_id FROM medical_records WHERE consultation_session_id IS NOT NULL "
        "GROUP BY consultation_session_id HAVING count(*) > 1 LIMIT 1"
    ).first()
    if dup:
        raise RuntimeError(f"Ca tư vấn {dup[0]} có nhiều hơn 1 bệnh án; gộp/xoá tay rồi chạy lại migration.")

    op.rename_table('medical_records', 'finalize_reports')
    op.alter_column('patient_images', 'medical_record_id', new_column_name='finalize_report_id')
    for table, old, new in CONSTRAINTS:
        op.execute(f'ALTER TABLE {_new_table(table)} RENAME CONSTRAINT {old} TO {new}')
    for old, new in INDEXES:
        op.execute(f'ALTER INDEX {old} RENAME TO {new}')
    op.drop_index('ix_medical_records_consultation_session_id', table_name='finalize_reports')
    op.create_index(op.f('ix_finalize_reports_consultation_session_id'), 'finalize_reports', ['consultation_session_id'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_finalize_reports_consultation_session_id'), table_name='finalize_reports')
    op.create_index('ix_medical_records_consultation_session_id', 'finalize_reports', ['consultation_session_id'], unique=False)
    for old, new in INDEXES:
        op.execute(f'ALTER INDEX {new} RENAME TO {old}')
    for table, old, new in reversed(CONSTRAINTS):
        op.execute(f'ALTER TABLE {_new_table(table)} RENAME CONSTRAINT {new} TO {old}')
    op.alter_column('patient_images', 'finalize_report_id', new_column_name='medical_record_id')
    op.rename_table('finalize_reports', 'medical_records')
