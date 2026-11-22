"""create the tables for fetched videos

Revision ID: 3ba22dc74f35
Revises:
Create Date: 2026-11-22 10:31:13.178768
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these to put the migrations in order.
revision: str = "3ba22dc74f35"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channels",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
    )
    op.create_table(
        "videos",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("thumbnail_url", sa.String(), nullable=False),
        sa.Column("embeddable", sa.Boolean(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["channels.id"], name=op.f("fk_videos_channel_id_channels")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_videos")),
    )
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_videos_channel_id"), ["channel_id"], unique=False
        )

    op.create_table(
        "chapters",
        sa.Column("video_id", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name=op.f("fk_chapters_video_id_videos")
        ),
        sa.PrimaryKeyConstraint("video_id", "position", name=op.f("pk_chapters")),
    )
    op.create_table(
        "creator_comments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("video_id", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["video_id"],
            ["videos.id"],
            name=op.f("fk_creator_comments_video_id_videos"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_creator_comments")),
    )
    with op.batch_alter_table("creator_comments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_creator_comments_video_id"), ["video_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("creator_comments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_creator_comments_video_id"))

    op.drop_table("creator_comments")
    op.drop_table("chapters")
    with op.batch_alter_table("videos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_videos_channel_id"))

    op.drop_table("videos")
    op.drop_table("channels")
