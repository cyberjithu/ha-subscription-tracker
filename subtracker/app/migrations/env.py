from logging.config import fileConfig

from alembic import context
from sqlmodel import SQLModel

from app import models  # noqa: F401  registers tables on SQLModel.metadata
from app.db import engine

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

with engine.connect() as connection:
    # batch mode lets SQLite alter tables by copy-and-move
    context.configure(connection=connection, target_metadata=SQLModel.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
