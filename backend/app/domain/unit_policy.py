from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base


class UnitPolicy(Base):
    __tablename__ = "unit_policies"

    # null unit_id = system-wide DefaultUnitPolicy baseline
    unit_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("units.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=True,
    )
    operator_can_delete_protocol: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    operator_can_move_protocol: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    operator_can_lock_protocol: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    operator_can_change_visibility: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    operator_can_export_pdf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reader_can_export_pdf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reader_can_comment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
