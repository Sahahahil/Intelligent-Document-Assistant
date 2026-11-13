"""Declarative base for all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Every table inherits from this. Alembic autogenerates against it."""
