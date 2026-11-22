"""create the recipes table

Revision ID: ac4eb4587ed7
Revises: 3ba22dc74f35
Create Date: 2026-11-22 13:36:02.420283
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these to put the migrations in order.
revision: str = "ac4eb4587ed7"
down_revision: str | Sequence[str] | None = "3ba22dc74f35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
