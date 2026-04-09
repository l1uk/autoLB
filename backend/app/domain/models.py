from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Sequence,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, TypeDecorator

from app.domain.base import Base
from app.domain.enums import (
    AccessPolicyScopeType,
    AcquisitionStatus,
    CalibrationAlgorithm,
    DataServiceClientStatus,
    DataServiceTaskStatus,
    DerivativeType,
    FileEventDecision,
    PictureType,
    ProcessingStatus,
    ProtocolStatus,
    UserRole,
)


# acquisition_status transitions are MANUAL ONLY per RF-19.
# No ORM event, trigger, or task may set this field.

jsonb_type = JSON().with_variant(JSONB(), "postgresql")


class UUIDArrayType(TypeDecorator[list[UUID]]):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Uuid(as_uuid=True)))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return [str(item) for item in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return [UUID(item) for item in value]


uuid_array_type = UUIDArrayType()


class CalibrationConfig(Base):
    __tablename__ = "calibration_configs"
    __required_fields__ = ("picture_type", "calibration_algorithm")

    picture_type: Mapped[PictureType] = mapped_column(
        Enum(PictureType, name="picture_type_enum"),
        primary_key=True,
    )
    calibration_algorithm: Mapped[CalibrationAlgorithm] = mapped_column(
        Enum(CalibrationAlgorithm, name="calibration_algorithm_enum"),
        nullable=False,
    )

    microscope_pictures: Mapped[list["MicroscopePicture"]] = relationship(
        back_populates="calibration_config"
    )


class AccessPolicy(Base):
    __tablename__ = "access_policies"
    __required_fields__ = ("scope_type", "allowed_ids", "owner_id")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    scope_type: Mapped[AccessPolicyScopeType] = mapped_column(
        Enum(AccessPolicyScopeType, name="access_policy_scope_type_enum"),
        nullable=False,
    )
    group_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    allowed_ids: Mapped[list[UUID]] = mapped_column(uuid_array_type, nullable=False, default=list)
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    samples: Mapped[list["Sample"]] = relationship(back_populates="access_policy")
    protocols: Mapped[list["Protocol"]] = relationship(back_populates="access_policy")


class Sample(Base):
    __tablename__ = "samples"
    __required_fields__ = ("full_name", "last_name", "access_policy_id")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("samples.id", ondelete="SET NULL"),
        nullable=True,
    )
    access_policy_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)

    parent: Mapped["Sample | None"] = relationship(remote_side="Sample.id", back_populates="children")
    children: Mapped[list["Sample"]] = relationship(back_populates="parent")
    access_policy: Mapped["AccessPolicy"] = relationship(back_populates="samples")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="sample")
    optical_images: Mapped[list["OpticalImage"]] = relationship(back_populates="sample")
    navigation_images: Mapped[list["NavigationImage"]] = relationship(back_populates="sample")
    videos: Mapped[list["Video"]] = relationship(back_populates="sample")


class Protocol(Base):
    __tablename__ = "protocols"
    __required_fields__ = (
        "protocol_number",
        "status",
        "acquisition_status",
        "access_policy_id",
        "yaml_customization",
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    protocol_number: Mapped[int] = mapped_column(
        Integer,
        Sequence("protocol_number_seq"),
        nullable=False,
        unique=True,
        comment="Application-managed sequence value.",
    )
    status: Mapped[ProtocolStatus] = mapped_column(
        Enum(ProtocolStatus, name="protocol_status_enum"),
        nullable=False,
    )
    acquisition_status: Mapped[AcquisitionStatus] = mapped_column(
        Enum(AcquisitionStatus, name="acquisition_status_enum"),
        nullable=False,
    )
    access_policy_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("access_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    yaml_customization: Mapped[dict[str, Any]] = mapped_column(jsonb_type, nullable=False, default=dict)
    html_export_cache: Mapped[str | None] = mapped_column(Text, nullable=True)

    access_policy: Mapped["AccessPolicy"] = relationship(back_populates="protocols")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="protocol")
    optical_images: Mapped[list["OpticalImage"]] = relationship(back_populates="protocol")
    navigation_images: Mapped[list["NavigationImage"]] = relationship(back_populates="protocol")
    videos: Mapped[list["Video"]] = relationship(back_populates="protocol")


class MicroscopePicture(Base):
    __tablename__ = "microscope_pictures"
    __required_fields__ = (
        "params",
        "processing_status",
        "has_metadata",
        "calibration_config_picture_type",
    )

    id: Mapped[int] = mapped_column(
        Integer,
        Sequence("microscope_picture_id_seq"),
        primary_key=True,
        autoincrement=True,
    )
    params: Mapped[dict[str, Any]] = mapped_column(jsonb_type, nullable=False, default=dict)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus, name="processing_status_enum"),
        nullable=False,
    )
    has_metadata: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    calibration_config_picture_type: Mapped[PictureType] = mapped_column(
        Enum(PictureType, name="picture_type_enum"),
        ForeignKey("calibration_configs.picture_type", ondelete="RESTRICT"),
        nullable=False,
    )

    calibration_config: Mapped["CalibrationConfig"] = relationship(back_populates="microscope_pictures")
    derivatives: Mapped[list["ImageDerivative"]] = relationship(back_populates="microscope_picture")


class ImageDerivative(Base):
    __tablename__ = "image_derivatives"
    __required_fields__ = ("derivative_type", "microscope_picture_id")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    microscope_picture_id: Mapped[int] = mapped_column(
        ForeignKey("microscope_pictures.id", ondelete="CASCADE"),
        nullable=False,
    )
    derivative_type: Mapped[DerivativeType] = mapped_column(
        Enum(DerivativeType, name="derivative_type_enum"),
        nullable=False,
    )
    frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    microscope_picture: Mapped["MicroscopePicture"] = relationship(back_populates="derivatives")


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint(
            "(protocol_id IS NOT NULL) <> (sample_id IS NOT NULL)",
            name="ck_attachments_single_owner",
        ),
    )
    __required_fields__ = ("protocol_id",)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    protocol_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        nullable=True,
    )
    sample_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("samples.id", ondelete="CASCADE"),
        nullable=True,
    )

    protocol: Mapped["Protocol | None"] = relationship(back_populates="attachments")
    sample: Mapped["Sample | None"] = relationship(back_populates="attachments")


class OpticalImage(Base):
    __tablename__ = "optical_images"
    __table_args__ = (
        CheckConstraint(
            "(protocol_id IS NOT NULL) OR (sample_id IS NOT NULL)",
            name="ck_optical_images_has_owner",
        ),
    )
    __required_fields__ = ("caption", "description", "extra_info")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    protocol_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        nullable=True,
    )
    sample_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("samples.id", ondelete="CASCADE"),
        nullable=True,
    )
    caption: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    extra_info: Mapped[dict[str, Any]] = mapped_column(jsonb_type, nullable=False, default=dict)

    protocol: Mapped["Protocol | None"] = relationship(back_populates="optical_images")
    sample: Mapped["Sample | None"] = relationship(back_populates="optical_images")


class NavigationImage(Base):
    __tablename__ = "navigation_images"
    __table_args__ = (
        CheckConstraint(
            "(protocol_id IS NOT NULL) OR (sample_id IS NOT NULL)",
            name="ck_navigation_images_has_owner",
        ),
    )
    __required_fields__ = ("caption", "description", "extra_info")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    protocol_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        nullable=True,
    )
    sample_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("samples.id", ondelete="CASCADE"),
        nullable=True,
    )
    caption: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    extra_info: Mapped[dict[str, Any]] = mapped_column(jsonb_type, nullable=False, default=dict)

    protocol: Mapped["Protocol | None"] = relationship(back_populates="navigation_images")
    sample: Mapped["Sample | None"] = relationship(back_populates="navigation_images")


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        CheckConstraint(
            "(protocol_id IS NOT NULL) OR (sample_id IS NOT NULL)",
            name="ck_videos_has_owner",
        ),
    )
    __required_fields__ = ("caption", "description", "extra_info")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    protocol_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        nullable=True,
    )
    sample_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("samples.id", ondelete="CASCADE"),
        nullable=True,
    )
    caption: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    extra_info: Mapped[dict[str, Any]] = mapped_column(jsonb_type, nullable=False, default=dict)

    protocol: Mapped["Protocol | None"] = relationship(back_populates="videos")
    sample: Mapped["Sample | None"] = relationship(back_populates="videos")


class ExperimentConfiguration(Base):
    __tablename__ = "experiment_configurations"
    __required_fields__ = ("watch_folder",)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    watch_folder: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        comment="Documentation only. The server never uses watch_folder directly.",
    )


class DataServiceClient(Base):
    __tablename__ = "data_service_clients"
    __required_fields__ = (
        "hostname",
        "watch_folder",
        "os_info",
        "agent_version",
        "api_key_hash",
        "status",
        "is_revoked",
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    watch_folder: Mapped[str] = mapped_column(String(1024), nullable=False)
    os_info: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(64), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    session_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[DataServiceClientStatus] = mapped_column(
        Enum(DataServiceClientStatus, name="data_service_client_status_enum"),
        nullable=False,
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DataServiceTask(Base):
    __tablename__ = "data_service_tasks"
    __required_fields__ = ("client_id", "task_type", "operation", "params", "status")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    client_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("data_service_clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Plain string for server-side extensibility without schema changes.",
    )
    operation: Mapped[str] = mapped_column(String(255), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(jsonb_type, nullable=False, default=dict)
    status: Mapped[DataServiceTaskStatus] = mapped_column(
        Enum(DataServiceTaskStatus, name="data_service_task_status_enum"),
        nullable=False,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class FileEvent(Base):
    __tablename__ = "file_events"
    __required_fields__ = ("context_id", "decision")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    context_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        nullable=False,
        comment="Opaque token. data-service must not decode this value.",
    )
    decision: Mapped[FileEventDecision] = mapped_column(
        Enum(FileEventDecision, name="file_event_decision_enum"),
        nullable=False,
    )


class User(Base):
    __tablename__ = "users"
    __required_fields__ = ("email", "username", "role", "hashed_password", "is_active")

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    username: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
    )
    unit_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
