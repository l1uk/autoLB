from __future__ import annotations

import enum
import uuid
from typing import Any

from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy import CHAR
from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import Sequence
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from .base import Base
from .base import utcnow


class GUID(TypeDecorator[uuid.UUID]):
    """Portable UUID type for PostgreSQL and SQLite test databases."""

    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: uuid.UUID | str | None, dialect) -> str | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return uuid.UUID(str(value))
        return str(uuid.UUID(str(value)))

    def process_result_value(self, value: str | uuid.UUID | None, dialect) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class GUIDList(TypeDecorator[list[uuid.UUID]]):
    """Stores UUID lists as ARRAY on PostgreSQL and JSON on SQLite."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(PG_UUID(as_uuid=True)))
        return dialect.type_descriptor(JSON())

    def process_bind_param(
        self,
        value: list[uuid.UUID] | list[str] | None,
        dialect,
    ) -> list[uuid.UUID] | list[str] | None:
        if value is None:
            return None
        if dialect.name == "postgresql":
            return [uuid.UUID(str(item)) for item in value]
        return [str(uuid.UUID(str(item))) for item in value]

    def process_result_value(
        self,
        value: list[uuid.UUID] | list[str] | None,
        dialect,
    ) -> list[uuid.UUID]:
        if not value:
            return []
        return [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in value]


class PortableJSON(TypeDecorator[dict[str, Any]]):
    """Uses JSONB on PostgreSQL and JSON elsewhere."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        GUID(),
        primary_key=True,
        default_factory=uuid.uuid4,
        init=False,
    )


class PictureType(str, enum.Enum):
    QUATTRO_MICROSCOPE_PICTURE = "QUATTRO_MICROSCOPE_PICTURE"
    VERSA_MICROSCOPE_PICTURE = "VERSA_MICROSCOPE_PICTURE"
    FEI_MICROSCOPE_PICTURE = "FEI_MICROSCOPE_PICTURE"
    VEGA_MICROSCOPE_PICTURE = "VEGA_MICROSCOPE_PICTURE"
    VEGA_JPEG_MICROSCOPE_PICTURE = "VEGA_JPEG_MICROSCOPE_PICTURE"
    XL40_MICROSCOPE_PICTURE = "XL40_MICROSCOPE_PICTURE"
    XL40_MULTIFRAME_MICROSCOPE_PICTURE = "XL40_MULTIFRAME_MICROSCOPE_PICTURE"
    XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE = (
        "XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE"
    )
    XL40_WITH_STAGE_MICROSCOPE_PICTURE = "XL40_WITH_STAGE_MICROSCOPE_PICTURE"
    GENERIC_MICROSCOPE_PICTURE = "GENERIC_MICROSCOPE_PICTURE"


class DerivativeType(str, enum.Enum):
    THUMBNAIL = "THUMBNAIL"
    FULLSIZE_PNG = "FULLSIZE_PNG"
    DZI = "DZI"
    CROPPED = "CROPPED"
    FRAME_PNG = "FRAME_PNG"


class ProcessingStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    DONE = "DONE"
    ERROR = "ERROR"


class MicroscopeType(str, enum.Enum):
    QUATTRO = "QUATTRO"
    VERSA = "VERSA"
    VEGA = "VEGA"
    XL40 = "XL40"
    MULTI = "MULTI"


class ProtocolStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"


class AcquisitionStatus(str, enum.Enum):
    ONGOING = "ONGOING"
    COMPLETED = "COMPLETED"


class AttachmentType(str, enum.Enum):
    GENERIC = "GENERIC"
    UPLOAD = "UPLOAD"


class OpticalImageType(str, enum.Enum):
    GENERIC = "GENERIC"
    KEYENCE = "KEYENCE"
    DIGITAL_CAMERA = "DIGITAL_CAMERA"
    DIGITAL_CAMERA_WITH_GPS = "DIGITAL_CAMERA_WITH_GPS"


class CalibrationAlgorithm(str, enum.Enum):
    FEI_TAG = "FEI_TAG"
    VEGA_PIXEL_SIZE = "VEGA_PIXEL_SIZE"
    XL40_XMP = "XL40_XMP"


class DataServiceClientStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    NEVER_SEEN = "NEVER_SEEN"


class DataServiceTaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class FileEventDecision(str, enum.Enum):
    ACCEPT = "ACCEPT"
    IGNORE = "IGNORE"


class AccessPolicyScopeType(str, enum.Enum):
    OPEN = "OPEN"
    GROUP = "GROUP"
    EXPLICIT = "EXPLICIT"


picture_type_enum = Enum(PictureType, name="picture_type")
derivative_type_enum = Enum(DerivativeType, name="image_derivative_type")
processing_status_enum = Enum(ProcessingStatus, name="processing_status")
microscope_type_enum = Enum(MicroscopeType, name="microscope_type")
protocol_status_enum = Enum(ProtocolStatus, name="protocol_status")
acquisition_status_enum = Enum(AcquisitionStatus, name="acquisition_status")
attachment_type_enum = Enum(AttachmentType, name="attachment_type")
optical_image_type_enum = Enum(OpticalImageType, name="optical_image_type")
calibration_algorithm_enum = Enum(
    CalibrationAlgorithm,
    name="calibration_algorithm",
)
data_service_client_status_enum = Enum(
    DataServiceClientStatus,
    name="data_service_client_status",
)
data_service_task_status_enum = Enum(
    DataServiceTaskStatus,
    name="data_service_task_status",
)
file_event_decision_enum = Enum(FileEventDecision, name="file_event_decision")
access_policy_scope_type_enum = Enum(
    AccessPolicyScopeType,
    name="access_policy_scope_type",
)


class AccessPolicy(Base, kw_only=True):
    __tablename__ = "access_policies"

    id: Mapped[uuid.UUID] = uuid_pk()
    scope_type: Mapped[AccessPolicyScopeType] = mapped_column(
        access_policy_scope_type_enum,
        nullable=False,
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), default=None)
    allowed_ids: Mapped[list[uuid.UUID]] = mapped_column(GUIDList(), default_factory=list)
    owner_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        nullable=False,
    )

    protocols: Mapped[list[Protocol]] = relationship(
        back_populates="access_policy",
        default_factory=list,
        init=False,
    )
    samples: Mapped[list[Sample]] = relationship(
        back_populates="access_policy",
        default_factory=list,
        init=False,
    )


class Protocol(Base, kw_only=True):
    __tablename__ = "protocols"

    id: Mapped[uuid.UUID] = uuid_pk()
    protocol_number: Mapped[int] = mapped_column(
        Integer,
        Sequence("protocol_number_seq"),
        unique=True,
        nullable=False,
        init=False,
    )
    project: Mapped[str] = mapped_column(String(255), nullable=False)
    responsible: Mapped[str] = mapped_column(String(255), nullable=False)
    microscope_type: Mapped[MicroscopeType] = mapped_column(
        microscope_type_enum,
        nullable=False,
    )
    introduction: Mapped[str | None] = mapped_column(Text, default=None)
    conclusion: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[ProtocolStatus] = mapped_column(
        protocol_status_enum,
        default=ProtocolStatus.DRAFT,
        nullable=False,
    )
    # Acquisition status is manual-only. The domain model must not imply any
    # automatic state transition based on upload, processing, or export events.
    acquisition_status: Mapped[AcquisitionStatus] = mapped_column(
        acquisition_status_enum,
        default=AcquisitionStatus.ONGOING,
        nullable=False,
    )
    access_policy_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("access_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), default=None)
    yaml_customization: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON(),
        default_factory=dict,
        nullable=False,
    )
    html_export_cache: Mapped[str | None] = mapped_column(Text, default=None)
    html_exported_at: Mapped[Any] = mapped_column(DateTime(timezone=True), default=None, nullable=True)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        nullable=False,
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    access_policy: Mapped[AccessPolicy] = relationship(
        back_populates="protocols",
        init=False,
    )
    samples: Mapped[list[Sample]] = relationship(
        back_populates="protocol",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="protocol",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    optical_images: Mapped[list[OpticalImage]] = relationship(
        back_populates="protocol",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    navigation_images: Mapped[list[NavigationImage]] = relationship(
        back_populates="protocol",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    experiment_configuration: Mapped[ExperimentConfiguration | None] = relationship(
        back_populates="protocol",
        uselist=False,
        default=None,
        init=False,
    )
    data_service_tasks: Mapped[list[DataServiceTask]] = relationship(
        back_populates="protocol",
        default_factory=list,
        init=False,
    )
    file_events: Mapped[list[FileEvent]] = relationship(
        back_populates="protocol",
        default_factory=list,
        init=False,
    )


class ExperimentConfiguration(Base, kw_only=True):
    __tablename__ = "experiment_configurations"

    id: Mapped[uuid.UUID] = uuid_pk()
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    microscope_type: Mapped[MicroscopeType] = mapped_column(
        microscope_type_enum,
        nullable=False,
    )
    watch_folder: Mapped[str] = mapped_column(String(1024), nullable=False)
    thumbnail_max_width: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    operator: Mapped[str] = mapped_column(String(255), nullable=False)

    protocol: Mapped[Protocol] = relationship(back_populates="experiment_configuration", init=False)
    calibration_configs: Mapped[list[CalibrationConfig]] = relationship(
        back_populates="experiment_configuration",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )


class CalibrationConfig(Base, kw_only=True):
    __tablename__ = "calibration_configs"

    __table_args__ = (
        CheckConstraint(
            "picture_type <> 'GENERIC_MICROSCOPE_PICTURE'",
            name="ck_calibration_configs_picture_type_not_generic",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    experiment_configuration_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("experiment_configurations.id", ondelete="CASCADE"),
        nullable=False,
    )
    picture_type: Mapped[PictureType] = mapped_column(
        picture_type_enum,
        nullable=False,
    )
    auto_calibration: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    databar_removal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    calibration_algorithm: Mapped[CalibrationAlgorithm] = mapped_column(
        calibration_algorithm_enum,
        nullable=False,
    )

    experiment_configuration: Mapped[ExperimentConfiguration] = relationship(
        back_populates="calibration_configs",
        init=False,
    )
    microscope_pictures: Mapped[list[MicroscopePicture]] = relationship(
        back_populates="calibration_config",
        default_factory=list,
        init=False,
    )


class Sample(Base, kw_only=True):
    __tablename__ = "samples"

    __table_args__ = (
        CheckConstraint("full_name <> ''", name="ck_samples_full_name_non_empty"),
        CheckConstraint("last_name <> ''", name="ck_samples_last_name_non_empty"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("samples.id", ondelete="CASCADE"),
        default=None,
    )
    description: Mapped[str | None] = mapped_column(Text, default=None)
    access_policy_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("access_policies.id", ondelete="RESTRICT"),
        nullable=False,
    )

    protocol: Mapped[Protocol] = relationship(back_populates="samples", init=False)
    parent: Mapped[Sample | None] = relationship(
        back_populates="subsamples",
        remote_side=lambda: [Sample.id],
        default=None,
        init=False,
    )
    subsamples: Mapped[list[Sample]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    access_policy: Mapped[AccessPolicy] = relationship(back_populates="samples", init=False)
    microscope_pictures: Mapped[list[MicroscopePicture]] = relationship(
        back_populates="sample",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    videos: Mapped[list[Video]] = relationship(
        back_populates="sample",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    optical_images: Mapped[list[OpticalImage]] = relationship(
        back_populates="sample",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="sample",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )


class MicroscopePicture(Base, kw_only=True):
    __tablename__ = "microscope_pictures"

    id: Mapped[int] = mapped_column(
        Integer,
        Sequence("microscope_picture_id_seq"),
        primary_key=True,
        init=False,
    )
    sample_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("samples.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sample_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # Detection order is critical and must remain:
    # QUATTRO -> VERSA -> FEI -> VEGA -> VEGA_JPEG -> XL40 variants -> GENERIC.
    picture_type: Mapped[PictureType] = mapped_column(
        picture_type_enum,
        nullable=False,
    )
    params: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON(),
        default_factory=dict,
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    extra_info: Mapped[str | None] = mapped_column(Text, default=None)
    has_metadata: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    calibration_config_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("calibration_configs.id", ondelete="SET NULL"),
        default=None,
    )
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        processing_status_enum,
        default=ProcessingStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        nullable=False,
    )
    updated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    sample: Mapped[Sample] = relationship(back_populates="microscope_pictures", init=False)
    calibration_config: Mapped[CalibrationConfig | None] = relationship(
        back_populates="microscope_pictures",
        default=None,
        init=False,
    )
    derivatives: Mapped[list[ImageDerivative]] = relationship(
        back_populates="picture",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )


class ImageDerivative(Base, kw_only=True):
    __tablename__ = "image_derivatives"

    id: Mapped[uuid.UUID] = uuid_pk()
    picture_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("microscope_pictures.id", ondelete="CASCADE"),
        nullable=False,
    )
    derivative_type: Mapped[DerivativeType] = mapped_column(
        derivative_type_enum,
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2048), default=None)
    frame_index: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        nullable=False,
    )

    picture: Mapped[MicroscopePicture] = relationship(back_populates="derivatives", init=False)


class Attachment(Base, kw_only=True):
    __tablename__ = "attachments"

    __table_args__ = (
        CheckConstraint(
            "(protocol_id IS NOT NULL) <> (sample_id IS NOT NULL)",
            name="ck_attachments_owner_xor",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    protocol_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        default=None,
    )
    sample_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("samples.id", ondelete="CASCADE"),
        default=None,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attachment_type: Mapped[AttachmentType] = mapped_column(
        attachment_type_enum,
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    extra_info: Mapped[str | None] = mapped_column(Text, default=None)

    protocol: Mapped[Protocol | None] = relationship(back_populates="attachments", default=None, init=False)
    sample: Mapped[Sample | None] = relationship(back_populates="attachments", default=None, init=False)


class OpticalImage(Base, kw_only=True):
    __tablename__ = "optical_images"

    __table_args__ = (
        CheckConstraint(
            "(protocol_id IS NOT NULL) <> (sample_id IS NOT NULL)",
            name="ck_optical_images_owner_xor",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    protocol_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        default=None,
    )
    sample_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("samples.id", ondelete="CASCADE"),
        default=None,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    optical_image_type: Mapped[OpticalImageType] = mapped_column(
        optical_image_type_enum,
        default=OpticalImageType.GENERIC,
        nullable=False,
    )
    caption: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    extra_info: Mapped[str | None] = mapped_column(Text, default=None)

    protocol: Mapped[Protocol | None] = relationship(back_populates="optical_images", default=None, init=False)
    sample: Mapped[Sample | None] = relationship(back_populates="optical_images", default=None, init=False)


class NavigationImage(Base, kw_only=True):
    __tablename__ = "navigation_images"

    id: Mapped[uuid.UUID] = uuid_pk()
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("protocols.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    extra_info: Mapped[str | None] = mapped_column(Text, default=None)

    protocol: Mapped[Protocol] = relationship(back_populates="navigation_images", init=False)


class Video(Base, kw_only=True):
    __tablename__ = "videos"

    __table_args__ = (
        CheckConstraint(
            "sample_id IS NOT NULL",
            name="ck_videos_sample_required",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    sample_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("samples.id", ondelete="CASCADE"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, default=None)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    extra_info: Mapped[str | None] = mapped_column(Text, default=None)

    sample: Mapped[Sample] = relationship(back_populates="videos", init=False)


class DataServiceClient(Base, kw_only=True):
    __tablename__ = "data_service_clients"

    id: Mapped[uuid.UUID] = uuid_pk()
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    watch_folder: Mapped[str] = mapped_column(String(1024), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    session_token: Mapped[str | None] = mapped_column(String(4096), default=None)
    session_expires_at: Mapped[Any] = mapped_column(DateTime(timezone=True), default=None)
    status: Mapped[DataServiceClientStatus] = mapped_column(
        data_service_client_status_enum,
        default=DataServiceClientStatus.NEVER_SEEN,
        nullable=False,
    )
    last_seen: Mapped[Any] = mapped_column(DateTime(timezone=True), default=None)
    registered_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        nullable=False,
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    os_info: Mapped[str | None] = mapped_column(String(255), default=None)
    agent_version: Mapped[str | None] = mapped_column(String(64), default=None)

    tasks: Mapped[list[DataServiceTask]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )
    file_events: Mapped[list[FileEvent]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
        default_factory=list,
        init=False,
    )


class DataServiceTask(Base, kw_only=True):
    __tablename__ = "data_service_tasks"

    id: Mapped[uuid.UUID] = uuid_pk()
    client_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("data_service_clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    protocol_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("protocols.id", ondelete="SET NULL"),
        default=None,
    )
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON(),
        default_factory=dict,
        nullable=False,
    )
    status: Mapped[DataServiceTaskStatus] = mapped_column(
        data_service_task_status_enum,
        default=DataServiceTaskStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        nullable=False,
    )
    delivered_at: Mapped[Any] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[Any] = mapped_column(DateTime(timezone=True), default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    client: Mapped[DataServiceClient] = relationship(back_populates="tasks", init=False)
    protocol: Mapped[Protocol | None] = relationship(back_populates="data_service_tasks", default=None, init=False)


class FileEvent(Base, kw_only=True):
    __tablename__ = "file_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    context_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("data_service_clients.id", ondelete="CASCADE"),
        nullable=False,
    )
    protocol_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("protocols.id", ondelete="SET NULL"),
        default=None,
    )
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    decision: Mapped[FileEventDecision] = mapped_column(
        file_event_decision_enum,
        nullable=False,
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, default=None)
    notified_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        default_factory=utcnow,
        nullable=False,
    )
    uploaded_at: Mapped[Any] = mapped_column(DateTime(timezone=True), default=None)

    client: Mapped[DataServiceClient] = relationship(back_populates="file_events", init=False)
    protocol: Mapped[Protocol | None] = relationship(back_populates="file_events", default=None, init=False)
