"""lịch hẹn (appointments) + lần khám (encounters); finalize_reports gắn encounter + diagnosis_code

Không drop pre_consultation_reports: luồng tư vấn cũ (phiên + video call) còn dùng tới.

Revision ID: 7cfaabf896c2
Revises: 5b2e8c41d7a9
Create Date: 2026-11-03 20:02:27.090628

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7cfaabf896c2'
down_revision: Union[str, Sequence[str], None] = '5b2e8c41d7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('appointments',
    sa.Column('id', sa.String(length=64), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('patient_profile_id', sa.String(length=64), nullable=False),
    sa.Column('episode_id', sa.String(length=64), nullable=False),
    sa.Column('doctor_id', sa.String(length=64), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.String(length=16), server_default='requested', nullable=False),
    sa.Column('reason', sa.Text(), server_default='', nullable=False),
    sa.Column('cancel_reason', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status <> 'cancelled' OR cancel_reason IS NOT NULL", name=op.f('ck_appointments_cancel_reason_when_cancelled')),
    sa.CheckConstraint("status IN ('requested', 'cancelled') OR doctor_id IS NOT NULL", name=op.f('ck_appointments_doctor_when_confirmed')),
    sa.CheckConstraint("status IN ('requested', 'confirmed', 'in_progress', 'done', 'cancelled', 'no_show')", name=op.f('ck_appointments_status_valid')),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.user_id'], name=op.f('fk_appointments_doctor_id_doctors'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['episode_id'], ['clinical_episodes.id'], name=op.f('fk_appointments_episode_id_clinical_episodes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['patient_profile_id'], ['patient_profiles.id'], name=op.f('fk_appointments_patient_profile_id_patient_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_appointments'))
    )
    op.create_index(op.f('ix_appointments_episode_id'), 'appointments', ['episode_id'], unique=False)
    op.create_index(op.f('ix_appointments_patient_profile_id'), 'appointments', ['patient_profile_id'], unique=False)
    op.create_index(op.f('ix_appointments_scheduled_at'), 'appointments', ['scheduled_at'], unique=False)
    op.create_index('uq_appointments_active_episode', 'appointments', ['episode_id'], unique=True, postgresql_where=sa.text("status IN ('requested', 'confirmed', 'in_progress')"), sqlite_where=sa.text("status IN ('requested', 'confirmed', 'in_progress')"))
    op.create_table('encounters',
    sa.Column('id', sa.String(length=64), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('appointment_id', sa.String(length=64), nullable=False),
    sa.Column('patient_profile_id', sa.String(length=64), nullable=False),
    sa.Column('doctor_id', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=8), server_default='open', nullable=False),
    sa.Column('opened_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status <> 'closed' OR closed_at IS NOT NULL", name=op.f('ck_encounters_closed_at_when_closed')),
    sa.CheckConstraint("status IN ('open', 'closed')", name=op.f('ck_encounters_status_valid')),
    sa.ForeignKeyConstraint(['appointment_id'], ['appointments.id'], name=op.f('fk_encounters_appointment_id_appointments'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['doctor_id'], ['doctors.user_id'], name=op.f('fk_encounters_doctor_id_doctors'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['patient_profile_id'], ['patient_profiles.id'], name=op.f('fk_encounters_patient_profile_id_patient_profiles'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_encounters')),
    sa.UniqueConstraint('appointment_id', name=op.f('uq_encounters_appointment_id'))
    )
    op.create_index(op.f('ix_encounters_patient_profile_id'), 'encounters', ['patient_profile_id'], unique=False)
    op.add_column('clinical_provenances', sa.Column('encounter_id', sa.String(length=64), nullable=True))
    op.create_foreign_key(op.f('fk_clinical_provenances_encounter_id_encounters'), 'clinical_provenances', 'encounters', ['encounter_id'], ['id'], ondelete='SET NULL')
    op.add_column('finalize_reports', sa.Column('encounter_id', sa.String(length=64), nullable=True))
    op.add_column('finalize_reports', sa.Column('diagnosis_code', sa.String(length=64), nullable=True))
    op.create_unique_constraint(op.f('uq_finalize_reports_encounter_id'), 'finalize_reports', ['encounter_id'])
    op.create_foreign_key(op.f('fk_finalize_reports_encounter_id_encounters'), 'finalize_reports', 'encounters', ['encounter_id'], ['id'], ondelete='SET NULL')
    op.create_check_constraint(op.f('ck_finalize_reports_code_when_encounter'), 'finalize_reports', 'encounter_id IS NULL OR diagnosis_code IS NOT NULL')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_finalize_reports_code_when_encounter'), 'finalize_reports', type_='check')
    op.drop_constraint(op.f('fk_finalize_reports_encounter_id_encounters'), 'finalize_reports', type_='foreignkey')
    op.drop_constraint(op.f('uq_finalize_reports_encounter_id'), 'finalize_reports', type_='unique')
    op.drop_column('finalize_reports', 'diagnosis_code')
    op.drop_column('finalize_reports', 'encounter_id')
    op.drop_constraint(op.f('fk_clinical_provenances_encounter_id_encounters'), 'clinical_provenances', type_='foreignkey')
    op.drop_column('clinical_provenances', 'encounter_id')
    op.drop_index(op.f('ix_encounters_patient_profile_id'), table_name='encounters')
    op.drop_table('encounters')
    op.drop_index('uq_appointments_active_episode', table_name='appointments', postgresql_where=sa.text("status IN ('requested', 'confirmed', 'in_progress')"), sqlite_where=sa.text("status IN ('requested', 'confirmed', 'in_progress')"))
    op.drop_index(op.f('ix_appointments_scheduled_at'), table_name='appointments')
    op.drop_index(op.f('ix_appointments_patient_profile_id'), table_name='appointments')
    op.drop_index(op.f('ix_appointments_episode_id'), table_name='appointments')
    op.drop_table('appointments')
