from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Table, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.base import Base
from app.domain.enums import ContactRole


protocol_contacts = Table(
    "protocol_contacts",
    Base.metadata,
    Column(
        "protocol_id",
        Uuid(as_uuid=True),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "contact_id",
        Uuid(as_uuid=True),
        ForeignKey("project_contacts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class ProjectContact(Base):
    __tablename__ = "project_contacts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    affiliation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[ContactRole] = mapped_column(
        Enum(ContactRole, name="contact_role_enum"),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # null -> informative only (display in export, no access grant). non-null -> grants read+comment on protocols where role=RESPONSIBLE (SRS §3.5)
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    protocols: Mapped[list["Protocol"]] = relationship(
        secondary="protocol_contacts",
        back_populates="contacts",
    )
