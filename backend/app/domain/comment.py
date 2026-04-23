from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.base import Base
from app.domain.enums import CommentTargetType


class Comment(Base):
    __tablename__ = "comments"

    # Comments NOT blocked by protocol.status=LOCKED (SRS §1.17)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    protocol_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_type: Mapped[CommentTargetType] = mapped_column(
        Enum(CommentTargetType, name="comment_target_type_enum"),
        nullable=False,
    )
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # One level of threading only. Reject if parent comment itself has a parent_id set.
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("comments.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    parent: Mapped["Comment | None"] = relationship(remote_side="Comment.id")
