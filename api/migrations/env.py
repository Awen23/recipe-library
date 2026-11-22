"""Alembic runs this for every command, such as `alembic upgrade head`.

It connects to the app's database, the same way the app does, and applies the
migrations in `versions/`.
"""

import logging

from alembic import context

from recipes import storage

# Print each migration as it runs. Alembic's ini-file template sets this up, and
# its settings live in pyproject.toml instead.
logging.basicConfig(format="%(message)s")
logging.getLogger("alembic").setLevel(logging.INFO)

with storage.create_engine().connect() as connection:
    context.configure(
        connection=connection,
        # The tables as the code describes them, which `alembic revision
        # --autogenerate` compares with the database to write a migration.
        target_metadata=storage.metadata,
        # SQLite can't change most things about an existing table. Batch mode
        # copies the table into a new one with the change instead.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()
