from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(MappedAsDataclass, DeclarativeBase):
    """Base class for SQLAlchemy 2.x mapped dataclasses."""

