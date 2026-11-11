"""đợt bệnh (clinical_episodes) + giả thuyết AI (ai_hypotheses); fact theo đợt qua clinical_facts.episode_id

Revision ID: 9d9ebfce7f5b
Revises: 07a23a2f124b
Create Date: 2026-11-03 14:00:00.000000

Fact symptom / lesion / other cũ không có vùng → gom vào một đợt `closed` "dữ liệu cũ" (vùng nhieu_vung) mỗi hồ sơ.
Fact image_finding cũ → other (kết quả ảnh nay ở clinical_episodes.image_predictions).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '9d9ebfce7f5b'
down_revision: Union[str, Sequence[str], None] = '07a23a2f124b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_SUMMARY = 'Dữ liệu cũ, ghi trước khi có đợt bệnh theo vùng.'
LONG_TERM = "('allergy', 'history', 'medication')"


def _dedupe_facts(scope: str) -> None:
    """Giữ fact mới nhất mỗi khoá trong phạm vi `scope`, dồn nhật ký của bản trùng về bản giữ lại."""
    op.execute(f"""
        CREATE TEMP TABLE _fact_keeper ON COMMIT DROP AS
        SELECT id, first_value(id) OVER (
            PARTITION BY {scope}, fact_type, lower(label) ORDER BY updated_at DESC, created_at DESC, id DESC
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
    op.execute("DROP TABLE _fact_keeper")


def upgrade() -> None:
    op.create_table('clinical_episodes',
    sa.Column('id', sa.String(length=64), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('patient_profile_id', sa.String(length=64), nullable=False),
    sa.Column('body_site', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='open', nullable=False),
    sa.Column('last_conversation_id', sa.String(length=64), nullable=True),
    sa.Column('summary', sa.Text(), server_default='', nullable=False),
    sa.Column('summary_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('urgency', sa.String(length=16), nullable=True),
    sa.Column('red_flags', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('image_predictions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('model_version', sa.String(length=64), server_default='', nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('open', 'in_exam') OR closed_at IS NOT NULL", name=op.f('ck_clinical_episodes_closed_at_when_closed')),
    sa.CheckConstraint("status IN ('open', 'in_exam', 'closed', 'expired')", name=op.f('ck_clinical_episodes_status_valid')),
    sa.ForeignKeyConstraint(['last_conversation_id'], ['conversations.id'], name=op.f('fk_clinical_episodes_last_conversation_id_conversations'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['patient_profile_id'], ['patient_profiles.id'], name=op.f('fk_clinical_episodes_patient_profile_id_patient_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_clinical_episodes'))
    )
    op.create_index(op.f('ix_clinical_episodes_patient_profile_id'), 'clinical_episodes', ['patient_profile_id'], unique=False)
    op.create_index('uq_clinical_episodes_active_site', 'clinical_episodes', ['patient_profile_id', 'body_site'], unique=True,
                    postgresql_where=sa.text("status IN ('open', 'in_exam')"))
    op.create_table('ai_hypotheses',
    sa.Column('id', sa.String(length=64), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('episode_id', sa.String(length=64), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('diagnosis_code', sa.String(length=64), nullable=False),
    sa.Column('disease', sa.String(length=255), nullable=False),
    sa.Column('confidence', sa.String(length=8), nullable=False),
    sa.Column('evidence', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.Column('missing', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    sa.CheckConstraint('rank >= 1', name=op.f('ck_ai_hypotheses_rank_positive')),
    sa.ForeignKeyConstraint(['episode_id'], ['clinical_episodes.id'], name=op.f('fk_ai_hypotheses_episode_id_clinical_episodes'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_ai_hypotheses'))
    )
    op.create_index('uq_ai_hypotheses_episode_rank', 'ai_hypotheses', ['episode_id', 'rank'], unique=True)

    op.add_column('clinical_facts', sa.Column('episode_id', sa.String(length=64), nullable=True))
    op.create_foreign_key(op.f('fk_clinical_facts_episode_id_clinical_episodes'), 'clinical_facts',
                          'clinical_episodes', ['episode_id'], ['id'], ondelete='CASCADE')
    op.create_index(op.f('ix_clinical_facts_episode_id'), 'clinical_facts', ['episode_id'], unique=False)

    # bỏ khoá cũ trước: đổi image_finding → other có thể trùng nhãn với fact other có sẵn, gộp ở dưới
    op.drop_index('uq_clinical_facts_profile_type_label', table_name='clinical_facts')
    # Fact theo đợt cũ không có vùng: gom vào một đợt đã đóng mỗi hồ sơ, để không lẫn vào đợt mới
    op.execute("UPDATE clinical_facts SET fact_type = 'other' WHERE fact_type = 'image_finding'")
    op.execute(f"""
        INSERT INTO clinical_episodes (patient_profile_id, body_site, status, summary, opened_at, updated_at, closed_at)
        SELECT patient_profile_id, 'nhieu_vung', 'closed', '{LEGACY_SUMMARY}', min(created_at), max(updated_at), now()
        FROM clinical_facts WHERE fact_type NOT IN {LONG_TERM}
        GROUP BY patient_profile_id
    """)
    op.execute(f"""
        UPDATE clinical_facts f SET episode_id = e.id
        FROM clinical_episodes e
        WHERE e.patient_profile_id = f.patient_profile_id AND e.summary = '{LEGACY_SUMMARY}'
          AND f.fact_type NOT IN {LONG_TERM}
    """)
    # image_finding → other có thể trùng nhãn với fact other có sẵn
    _dedupe_facts("coalesce(episode_id, patient_profile_id)")

    op.create_index('uq_clinical_facts_long_term', 'clinical_facts',
                    ['patient_profile_id', 'fact_type', sa.text('lower(label)')], unique=True,
                    postgresql_where=sa.text('episode_id IS NULL'))
    op.create_index('uq_clinical_facts_episode', 'clinical_facts',
                    ['episode_id', 'fact_type', sa.text('lower(label)')], unique=True,
                    postgresql_where=sa.text('episode_id IS NOT NULL'))
    op.create_check_constraint(op.f('ck_clinical_facts_fact_type_valid'), 'clinical_facts',
                               "fact_type IN ('symptom', 'lesion', 'history', 'medication', 'allergy', 'other')")
    op.create_check_constraint(op.f('ck_clinical_facts_long_term_no_episode'), 'clinical_facts',
                               f"(fact_type IN {LONG_TERM}) = (episode_id IS NULL)")


def downgrade() -> None:
    op.drop_constraint(op.f('ck_clinical_facts_long_term_no_episode'), 'clinical_facts', type_='check')
    op.drop_constraint(op.f('ck_clinical_facts_fact_type_valid'), 'clinical_facts', type_='check')
    op.drop_index('uq_clinical_facts_episode', table_name='clinical_facts')
    op.drop_index('uq_clinical_facts_long_term', table_name='clinical_facts')
    # về khoá cũ theo hồ sơ: cùng nhãn ở nhiều đợt phải gộp lại (một chiều)
    _dedupe_facts('patient_profile_id')
    op.create_index('uq_clinical_facts_profile_type_label', 'clinical_facts',
                    ['patient_profile_id', 'fact_type', sa.text('lower(label)')], unique=True)
    op.drop_index(op.f('ix_clinical_facts_episode_id'), table_name='clinical_facts')
    op.drop_constraint(op.f('fk_clinical_facts_episode_id_clinical_episodes'), 'clinical_facts', type_='foreignkey')
    op.drop_column('clinical_facts', 'episode_id')
    op.drop_index('uq_ai_hypotheses_episode_rank', table_name='ai_hypotheses')
    op.drop_table('ai_hypotheses')
    op.drop_index('uq_clinical_episodes_active_site', table_name='clinical_episodes')
    op.drop_index(op.f('ix_clinical_episodes_patient_profile_id'), table_name='clinical_episodes')
    op.drop_table('clinical_episodes')
