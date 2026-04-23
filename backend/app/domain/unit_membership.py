from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base
from app.domain.enums import UnitRole


class UnitMembership(Base):
    __tablename__ = "unit_memberships"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    unit_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("units.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[UnitRole] = mapped_column(
        Enum(UnitRole, name="unit_role_enum"),
        nullable=False,
    )
    granted_by: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
