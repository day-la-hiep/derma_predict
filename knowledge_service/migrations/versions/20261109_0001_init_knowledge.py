"""Khởi tạo DB knowledge: tài liệu, bước pipeline, override, file, danh mục đồ thị

Viết tay (không autogenerate). Không có khoá ngoại sang service khác: `documents.uploaded_by_id` là id mềm tới identity.

Revision ID: 0001_init_knowledge
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_init_knowledge"
down_revision = None
branch_labels = None
depends_on = None

JSON_TYPE = postgresql.JSONB()
UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.String(64), primary_key=True, server_default=UUID_DEFAULT),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(64), primary_key=True, server_default=UUID_DEFAULT),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("type", sa.String(16), nullable=False, server_default="book"),
        sa.Column("source_file_id", sa.String(64), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ingested_file_id", sa.String(64), sa.ForeignKey("files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pdf_pages", sa.Integer(), nullable=True),
        sa.Column("uploaded_by_id", sa.String(64), nullable=True),
        sa.Column("profile", JSON_TYPE, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "document_stages",
        sa.Column("id", sa.String(64), primary_key=True, server_default=UUID_DEFAULT),
        sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_id", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("options", JSON_TYPE, nullable=True),
        sa.Column("progress", JSON_TYPE, nullable=True),
        sa.Column("summary", JSON_TYPE, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_id", "stage_id"),
    )
    op.create_table(
        "document_overrides",
        sa.Column(
            "document_stage_id", sa.String(64), sa.ForeignKey("document_stages.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("data", JSON_TYPE, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "graph_entity_types",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("label", sa.String(40), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("hint", sa.Text(), nullable=False),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("label"),
    )
    op.create_table(
        "graph_relations",
        sa.Column("id", sa.String(64), primary_key=True, server_default=UUID_DEFAULT),
        sa.Column("slot_id", sa.String(50), nullable=False),
        sa.Column("relation_type", sa.String(50), nullable=False),
        sa.Column("topic", sa.String(16), nullable=False),
        sa.Column("object_type", sa.String(40), nullable=False),
        sa.Column("topic_is_head", sa.Boolean(), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("display", sa.String(100), nullable=False),
        sa.Column("hint", sa.Text(), nullable=False),
        sa.Column("entity_hint", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("slot_id"),
        sa.UniqueConstraint("relation_type"),
    )


def downgrade() -> None:
    for table in ("graph_relations", "graph_entity_types", "document_overrides", "document_stages", "documents", "files"):
        op.drop_table(table)
