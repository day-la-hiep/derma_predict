"""clinical_facts thành bảng hiện trạng (gộp template), clinical_provenances thành nhật ký nguồn chỉ thêm

Revision ID: 07a23a2f124b
Revises: a7c1e9d4b302
Create Date: 2026-11-03 10:00:00.000000

Gộp fact trùng khoá (hồ sơ, loại, nhãn) là bước một chiều: downgrade không tách lại được.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '07a23a2f124b'
down_revision: Union[str, Sequence[str], None] = 'a7c1e9d4b302'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

QUOTE_MAX_CHARS = 500


def upgrade() -> None:
    # 1. Chép loại / nhãn / ontology từ template sang fact (template sinh tự do theo nhãn LLM, không phải danh mục)
    op.add_column('clinical_facts', sa.Column('fact_type', sa.String(length=32), nullable=True))
    op.add_column('clinical_facts', sa.Column('label', sa.String(length=255), nullable=True))
    op.add_column('clinical_facts', sa.Column('ontology_id', sa.String(length=128), nullable=True))
    op.add_column('clinical_facts', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('clinical_facts', sa.Column('verified_by_id', sa.String(length=64), nullable=True))
    op.add_column('clinical_facts', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("""
        UPDATE clinical_facts f
        SET fact_type = t.fact_type,
            label = btrim(regexp_replace(t.label, '\\s+', ' ', 'g')),
            ontology_id = t.ontology_id,
            updated_at = f.created_at
        FROM clinical_fact_templates t WHERE t.id = f.template_id
    """)

    # 2. Nhật ký nguồn: khoá riêng thay PK ghép, thêm loại nguồn / trích tin / giá trị ghi nhận
    op.add_column('clinical_provenances', sa.Column(
        'id', sa.String(length=64), server_default=sa.text('gen_random_uuid()'), nullable=False))
    op.drop_constraint(op.f('pk_clinical_provenances'), 'clinical_provenances', type_='primary')
    op.create_primary_key(op.f('pk_clinical_provenances'), 'clinical_provenances', ['id'])
    op.add_column('clinical_provenances', sa.Column('kind', sa.String(length=16), server_default='chat', nullable=False))
    op.add_column('clinical_provenances', sa.Column('quote', sa.Text(), server_default='', nullable=False))
    op.add_column('clinical_provenances', sa.Column('doctor_id', sa.String(length=64), nullable=True))
    op.add_column('clinical_provenances', sa.Column('detail', sa.Text(), server_default='', nullable=False))
    op.add_column('clinical_provenances', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.execute(f"""
        UPDATE clinical_provenances p
        SET quote = left(coalesce(m.content, ''), {QUOTE_MAX_CHARS}), created_at = m.created_at
        FROM messages m WHERE m.id = p.message_id
    """)
    op.execute("""
        UPDATE clinical_provenances p
        SET detail = f.detail, created_at = coalesce(p.created_at, f.created_at)
        FROM clinical_facts f WHERE f.id = p.fact_id
    """)
    op.alter_column('clinical_provenances', 'created_at', nullable=False)
    # xoá hội thoại không làm fact mất bằng chứng: nội dung đã chép vào quote
    op.alter_column('clinical_provenances', 'message_id', nullable=True)
    op.drop_constraint(op.f('fk_clinical_provenances_message_id_messages'), 'clinical_provenances', type_='foreignkey')
    op.create_foreign_key(op.f('fk_clinical_provenances_message_id_messages'), 'clinical_provenances',
                          'messages', ['message_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key(op.f('fk_clinical_provenances_doctor_id_doctors'), 'clinical_provenances',
                          'doctors', ['doctor_id'], ['user_id'], ondelete='SET NULL')
    op.create_check_constraint(op.f('ck_clinical_provenances_kind_valid'), 'clinical_provenances',
                               "kind IN ('chat', 'doctor')")
    op.create_index(op.f('ix_clinical_provenances_fact_id'), 'clinical_provenances', ['fact_id'], unique=False)
    op.create_index(op.f('ix_clinical_provenances_message_id'), 'clinical_provenances', ['message_id'], unique=False)

    # 3. Gộp fact trùng khoá (mỗi lần sinh báo cáo cũ đều INSERT mới): giữ bản mới nhất, dồn nhật ký của bản cũ vào
    op.drop_constraint(op.f('fk_clinical_facts_superseded_by_id_clinical_facts'), 'clinical_facts', type_='foreignkey')
    op.execute("""
        CREATE TEMP TABLE _fact_keeper ON COMMIT DROP AS
        SELECT id, first_value(id) OVER (
            PARTITION BY patient_profile_id, fact_type, lower(label) ORDER BY created_at DESC, id DESC
        ) AS keeper_id
        FROM clinical_facts
    """)
    op.execute("""
        UPDATE clinical_provenances p SET fact_id = k.keeper_id
        FROM _fact_keeper k WHERE k.id = p.fact_id AND k.id <> k.keeper_id
    """)
    op.execute("""
        DELETE FROM clinical_provenances p USING clinical_provenances q
        WHERE p.fact_id = q.fact_id AND p.message_id = q.message_id AND p.id > q.id
    """)
    op.execute("DELETE FROM clinical_facts f USING _fact_keeper k WHERE k.id = f.id AND k.id <> k.keeper_id")
    # migration sau chạy trong cùng transaction và tạo lại bảng tạm cùng tên
    op.execute("DROP TABLE _fact_keeper")

    # 4. Bỏ supersede và template
    op.drop_column('clinical_facts', 'superseded_by_id')
    op.drop_column('clinical_facts', 'status')
    op.drop_index(op.f('ix_clinical_facts_template_id'), table_name='clinical_facts')
    op.drop_constraint(op.f('fk_clinical_facts_template_id_clinical_fact_templates'), 'clinical_facts', type_='foreignkey')
    op.drop_column('clinical_facts', 'template_id')
    op.drop_table('clinical_fact_templates')

    op.alter_column('clinical_facts', 'fact_type', nullable=False)
    op.alter_column('clinical_facts', 'label', nullable=False)
    op.alter_column('clinical_facts', 'updated_at', nullable=False)
    op.create_foreign_key(op.f('fk_clinical_facts_verified_by_id_doctors'), 'clinical_facts',
                          'doctors', ['verified_by_id'], ['user_id'], ondelete='SET NULL')
    op.create_index('uq_clinical_facts_profile_type_label', 'clinical_facts',
                    ['patient_profile_id', 'fact_type', sa.text('lower(label)')], unique=True)


def downgrade() -> None:
    op.drop_index('uq_clinical_facts_profile_type_label', table_name='clinical_facts')
    op.drop_constraint(op.f('fk_clinical_facts_verified_by_id_doctors'), 'clinical_facts', type_='foreignkey')

    # template: mỗi nhãn một mẫu như migration c7d41e90a2b3
    op.create_table('clinical_fact_templates',
    sa.Column('id', sa.String(length=64), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('fact_type', sa.String(length=32), nullable=False),
    sa.Column('label', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('ontology_id', sa.String(length=128), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clinical_fact_templates')),
    sa.UniqueConstraint('label', name=op.f('uq_clinical_fact_templates_label'))
    )
    op.execute("""
        INSERT INTO clinical_fact_templates (fact_type, label, ontology_id)
        SELECT DISTINCT ON (label) fact_type, label, ontology_id FROM clinical_facts ORDER BY label, created_at
    """)
    op.add_column('clinical_facts', sa.Column('template_id', sa.String(length=64), nullable=True))
    op.execute("UPDATE clinical_facts f SET template_id = t.id FROM clinical_fact_templates t WHERE t.label = f.label")
    op.alter_column('clinical_facts', 'template_id', nullable=False)
    op.create_foreign_key(op.f('fk_clinical_facts_template_id_clinical_fact_templates'), 'clinical_facts',
                          'clinical_fact_templates', ['template_id'], ['id'], ondelete='RESTRICT')
    op.create_index(op.f('ix_clinical_facts_template_id'), 'clinical_facts', ['template_id'], unique=False)
    op.add_column('clinical_facts', sa.Column('status', sa.String(length=16), server_default='active', nullable=False))
    op.add_column('clinical_facts', sa.Column('superseded_by_id', sa.String(length=64), nullable=True))
    op.create_foreign_key(op.f('fk_clinical_facts_superseded_by_id_clinical_facts'), 'clinical_facts',
                          'clinical_facts', ['superseded_by_id'], ['id'], ondelete='SET NULL')

    # nhật ký về lại PK ghép: chỉ giữ dòng có tin nguồn, mỗi cặp (fact, tin) một dòng
    op.drop_index(op.f('ix_clinical_provenances_message_id'), table_name='clinical_provenances')
    op.drop_index(op.f('ix_clinical_provenances_fact_id'), table_name='clinical_provenances')
    op.drop_constraint(op.f('ck_clinical_provenances_kind_valid'), 'clinical_provenances', type_='check')
    op.drop_constraint(op.f('fk_clinical_provenances_doctor_id_doctors'), 'clinical_provenances', type_='foreignkey')
    op.drop_constraint(op.f('fk_clinical_provenances_message_id_messages'), 'clinical_provenances', type_='foreignkey')
    op.execute("DELETE FROM clinical_provenances WHERE message_id IS NULL")
    op.execute("""
        DELETE FROM clinical_provenances p USING clinical_provenances q
        WHERE p.fact_id = q.fact_id AND p.message_id = q.message_id AND p.id > q.id
    """)
    op.alter_column('clinical_provenances', 'message_id', nullable=False)
    op.create_foreign_key(op.f('fk_clinical_provenances_message_id_messages'), 'clinical_provenances',
                          'messages', ['message_id'], ['id'], ondelete='CASCADE')
    op.drop_column('clinical_provenances', 'created_at')
    op.drop_column('clinical_provenances', 'detail')
    op.drop_column('clinical_provenances', 'doctor_id')
    op.drop_column('clinical_provenances', 'quote')
    op.drop_column('clinical_provenances', 'kind')
    op.drop_constraint(op.f('pk_clinical_provenances'), 'clinical_provenances', type_='primary')
    op.drop_column('clinical_provenances', 'id')
    op.create_primary_key(op.f('pk_clinical_provenances'), 'clinical_provenances', ['fact_id', 'message_id'])

    op.drop_column('clinical_facts', 'updated_at')
    op.drop_column('clinical_facts', 'verified_by_id')
    op.drop_column('clinical_facts', 'verified_at')
    op.drop_column('clinical_facts', 'ontology_id')
    op.drop_column('clinical_facts', 'label')
    op.drop_column('clinical_facts', 'fact_type')
