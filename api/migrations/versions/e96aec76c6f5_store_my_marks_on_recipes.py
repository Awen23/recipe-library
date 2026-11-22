"""store my marks on recipes

Revision ID: e96aec76c6f5
Revises: 7d933c1749e1
Create Date: 2026-11-22 19:13:37.948599
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these to put the migrations in order.
revision: str = "e96aec76c6f5"
down_revision: str | Sequence[str] | None = "7d933c1749e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_marks",
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("interest", sa.String(), nullable=True),
        sa.Column("verdict", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "interest IN ('want_to_cook', 'curious', 'not_for_me')",
            name=op.f("ck_recipe_marks_interest"),
        ),
        sa.CheckConstraint(
            "verdict IN ('regularly', 'once_in_a_while', 'special_occasion', "
            "'not_again')",
            name=op.f("ck_recipe_marks_verdict"),
        ),
        sa.ForeignKeyConstraint(
            ["recipe_id"],
            ["recipes.id"],
            name=op.f("fk_recipe_marks_recipe_id_recipes"),
        ),
        sa.PrimaryKeyConstraint("recipe_id", name=op.f("pk_recipe_marks")),
    )


def downgrade() -> None:
    op.drop_table("recipe_marks")
