"""create the tables for recipes and ai answers

Revision ID: de5966ebfba0
Revises: 3ba22dc74f35
Create Date: 2026-11-22 12:18:10.297173
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these to put the migrations in order.
revision: str = "de5966ebfba0"
down_revision: str | Sequence[str] | None = "3ba22dc74f35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_responses",
        sa.Column("video_id", sa.String(), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("effort", sa.String(), nullable=False),
        sa.Column("answer", sa.JSON(), nullable=True),
        sa.Column("stop_reason", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name=op.f("fk_ai_responses_video_id_videos")
        ),
        sa.PrimaryKeyConstraint(
            "video_id",
            "prompt_version",
            "model",
            "effort",
            name=op.f("pk_ai_responses"),
        ),
    )
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("chapter_position", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("name_by", sa.String(), nullable=False),
        sa.Column("name_confidence", sa.Integer(), nullable=True),
        sa.Column("start_seconds", sa.Integer(), nullable=True),
        sa.Column("start_by", sa.String(), nullable=False),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "name_by IN ('code', 'ai', 'hand')", name=op.f("ck_recipes_name_by")
        ),
        sa.CheckConstraint(
            "start_by IN ('code', 'ai', 'hand')", name=op.f("ck_recipes_start_by")
        ),
        sa.ForeignKeyConstraint(
            ["video_id", "chapter_position"],
            ["chapters.video_id", "chapters.position"],
            name=op.f("fk_recipes_video_id_chapters"),
        ),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name=op.f("fk_recipes_video_id_videos")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recipes")),
        sa.UniqueConstraint("video_id", "position", name=op.f("uq_recipes_video_id")),
        sqlite_autoincrement=True,
    )


def downgrade() -> None:
    op.drop_table("recipes")
    op.drop_table("ai_responses")
