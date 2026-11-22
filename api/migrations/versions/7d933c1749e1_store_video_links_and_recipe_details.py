"""store video links and recipe details

Revision ID: 7d933c1749e1
Revises: ac4eb4587ed7
Create Date: 2026-11-22 14:30:14.990569
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these to put the migrations in order.
revision: str = "7d933c1749e1"
down_revision: str | Sequence[str] | None = "ac4eb4587ed7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_links",
        sa.Column("video_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("link_text", sa.String(), nullable=False),
        sa.Column("final_url", sa.String(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("recipe", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["video_id"], ["videos.id"], name=op.f("fk_video_links_video_id_videos")
        ),
        sa.PrimaryKeyConstraint("video_id", "url", name=op.f("pk_video_links")),
    )
    with op.batch_alter_table("recipes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ingredients", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("method", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("source_url", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("details_by", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("details_confidence", sa.Integer(), nullable=True)
        )
        # Autogenerate doesn't notice check constraints, so these are written by hand.
        batch_op.create_check_constraint(
            op.f("ck_recipes_details_by"), "details_by IN ('code', 'ai', 'hand')"
        )
        batch_op.create_check_constraint(
            op.f("ck_recipes_source"), "source IN ('link', 'description', 'comment')"
        )


def downgrade() -> None:
    with op.batch_alter_table("recipes", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_recipes_source"), type_="check")
        batch_op.drop_constraint(op.f("ck_recipes_details_by"), type_="check")
        batch_op.drop_column("details_confidence")
        batch_op.drop_column("details_by")
        batch_op.drop_column("source_url")
        batch_op.drop_column("source")
        batch_op.drop_column("method")
        batch_op.drop_column("ingredients")

    op.drop_table("video_links")
