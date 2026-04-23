from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import Text
from sqlalchemy.types import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class ProtocolItemMixin:
    """Shared annotation mixin (SRS §1.0 v2.8). extra_info is JSONB, not string. PATCH on any field invalidates html_export_cache."""

    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extra_info: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
