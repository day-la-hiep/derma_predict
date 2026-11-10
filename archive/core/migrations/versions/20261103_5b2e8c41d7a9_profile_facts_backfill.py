"""dị ứng / tiền sử tự khai của hồ sơ → fact dài hạn; bỏ cột patient_profiles.allergies / medical_history

Revision ID: 5b2e8c41d7a9
Revises: 9d9ebfce7f5b
Create Date: 2026-11-03 18:00:00.000000

Chuỗi tự khai được tách theo dấu `;` `,` hoặc xuống dòng, mỗi mục một fact (nhãn trùng fact có sẵn thì bỏ qua),
kèm một dòng nhật ký `kind = 'profile'`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5b2e8c41d7a9'
down_revision: Union[str, Sequence[str], None] = '9d9ebfce7f5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill(column: str, fact_type: str, prefix: str) -> None:
    op.execute(f"""
        WITH src AS (
            SELECT DISTINCT ON (p.id, lower(left(trim(x), 255)))
                   p.id AS pid, left(trim(x), 255) AS label, p.{column} AS raw
            FROM patient_profiles p, regexp_split_to_table(p.{column}, '\\s*[;,\\n]+\\s*') AS x
            WHERE trim(x) <> ''
        ),
        ins AS (
            INSERT INTO clinical_facts (patient_profile_id, fact_type, label, detail, created_at, updated_at)
            SELECT pid, '{fact_type}', label, '', now(), now() FROM src
            ON CONFLICT (patient_profile_id, fact_type, lower(label)) WHERE episode_id IS NULL DO NOTHING
            RETURNING id, patient_profile_id, label
        )
        INSERT INTO clinical_provenances (fact_id, kind, quote, detail, created_at)
        SELECT ins.id, 'profile', left('{prefix}: ' || src.raw, 500), '', now()
        FROM ins JOIN src ON src.pid = ins.patient_profile_id AND src.label = ins.label
    """)


def upgrade() -> None:
    op.drop_constraint(op.f('ck_clinical_provenances_kind_valid'), 'clinical_provenances', type_='check')
    op.create_check_constraint(op.f('ck_clinical_provenances_kind_valid'), 'clinical_provenances',
                               "kind IN ('chat', 'doctor', 'profile')")
    _backfill('allergies', 'allergy', 'Dị ứng (tự khai ở hồ sơ)')
    _backfill('medical_history', 'history', 'Tiền sử (tự khai ở hồ sơ)')
    op.drop_column('patient_profiles', 'medical_history')
    op.drop_column('patient_profiles', 'allergies')


def downgrade() -> None:
    op.add_column('patient_profiles', sa.Column('allergies', sa.Text(), server_default='', nullable=False))
    op.add_column('patient_profiles', sa.Column('medical_history', sa.Text(), server_default='', nullable=False))
    # ghép lại từ fact dài hạn (cả mục AI trích từ chat); fact giữ nguyên
    for column, fact_type in (('allergies', 'allergy'), ('medical_history', 'history')):
        op.execute(f"""
            UPDATE patient_profiles p SET {column} = agg.text
            FROM (
                SELECT patient_profile_id, string_agg(label, '; ' ORDER BY created_at) AS text
                FROM clinical_facts WHERE episode_id IS NULL AND fact_type = '{fact_type}'
                GROUP BY patient_profile_id
            ) agg
            WHERE agg.patient_profile_id = p.id
        """)
    op.execute("DELETE FROM clinical_provenances WHERE kind = 'profile'")
    op.drop_constraint(op.f('ck_clinical_provenances_kind_valid'), 'clinical_provenances', type_='check')
    op.create_check_constraint(op.f('ck_clinical_provenances_kind_valid'), 'clinical_provenances',
                               "kind IN ('chat', 'doctor')")
