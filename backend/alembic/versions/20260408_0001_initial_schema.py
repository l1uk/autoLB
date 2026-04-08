"""Initial autologbook schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260408_0001"
down_revision = None
branch_labels = None
depends_on = None


picture_type_enum = postgresql.ENUM(
    "QUATTRO_MICROSCOPE_PICTURE",
    "VERSA_MICROSCOPE_PICTURE",
    "FEI_MICROSCOPE_PICTURE",
    "VEGA_MICROSCOPE_PICTURE",
    "VEGA_JPEG_MICROSCOPE_PICTURE",
    "XL40_MICROSCOPE_PICTURE",
    "XL40_MULTIFRAME_MICROSCOPE_PICTURE",
    "XL40_MULTIFRAME_WITH_STAGE_MICROSCOPE_PICTURE",
    "XL40_WITH_STAGE_MICROSCOPE_PICTURE",
    "GENERIC_MICROSCOPE_PICTURE",
    name="picture_type",
)
image_derivative_type_enum = postgresql.ENUM(
    "THUMBNAIL",
    "FULLSIZE_PNG",
    "DZI",
    "CROPPED",
    "FRAME_PNG",
    name="image_derivative_type",
)
processing_status_enum = postgresql.ENUM(
    "PENDING",
    "PROCESSING",
    "DONE",
    "ERROR",
    name="processing_status",
)
microscope_type_enum = postgresql.ENUM(
    "QUATTRO",
    "VERSA",
    "VEGA",
    "XL40",
    "MULTI",
    name="microscope_type",
)
protocol_status_enum = postgresql.ENUM(
    "DRAFT",
    "ACTIVE",
    "LOCKED",
    name="protocol_status",
)
acquisition_status_enum = postgresql.ENUM(
    "ONGOING",
    "COMPLETED",
    name="acquisition_status",
)
attachment_type_enum = postgresql.ENUM(
    "GENERIC",
    "UPLOAD",
    name="attachment_type",
)
optical_image_type_enum = postgresql.ENUM(
    "GENERIC",
    "KEYENCE",
    "DIGITAL_CAMERA",
    "DIGITAL_CAMERA_WITH_GPS",
    name="optical_image_type",
)
calibration_algorithm_enum = postgresql.ENUM(
    "FEI_TAG",
    "VEGA_PIXEL_SIZE",
    "XL40_XMP",
    name="calibration_algorithm",
)
data_service_client_status_enum = postgresql.ENUM(
    "ONLINE",
    "OFFLINE",
    "NEVER_SEEN",
    name="data_service_client_status",
)
data_service_task_status_enum = postgresql.ENUM(
    "PENDING",
    "DELIVERED",
    "SUCCESS",
    "ERROR",
    name="data_service_task_status",
)
file_event_decision_enum = postgresql.ENUM(
    "ACCEPT",
    "IGNORE",
    name="file_event_decision",
)
access_policy_scope_type_enum = postgresql.ENUM(
    "OPEN",
    "GROUP",
    "EXPLICIT",
    name="access_policy_scope_type",
)


def upgrade() -> None:
    bind = op.get_bind()

    for enum_type in (
        picture_type_enum,
        image_derivative_type_enum,
        processing_status_enum,
        microscope_type_enum,
        protocol_status_enum,
        acquisition_status_enum,
        attachment_type_enum,
        optical_image_type_enum,
        calibration_algorithm_enum,
        data_service_client_status_enum,
        data_service_task_status_enum,
        file_event_decision_enum,
        access_policy_scope_type_enum,
    ):
        enum_type.create(bind, checkfirst=True)

    op.execute(sa.schema.CreateSequence(sa.Sequence("protocol_number_seq")))
    op.execute(sa.schema.CreateSequence(sa.Sequence("microscope_picture_id_seq")))

    op.create_table(
        "access_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", access_policy_scope_type_enum, nullable=False),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "allowed_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "data_service_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("watch_folder", sa.String(length=1024), nullable=False),
        sa.Column("api_key_hash", sa.String(length=255), nullable=False),
        sa.Column("session_token", sa.String(length=4096), nullable=True),
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            data_service_client_status_enum,
            nullable=False,
            server_default="NEVER_SEEN",
        ),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "registered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "is_revoked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("os_info", sa.String(length=255), nullable=True),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "protocols",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "protocol_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("nextval('protocol_number_seq')"),
        ),
        sa.Column("project", sa.String(length=255), nullable=False),
        sa.Column("responsible", sa.String(length=255), nullable=False),
        sa.Column("microscope_type", microscope_type_enum, nullable=False),
        sa.Column("introduction", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column(
            "status",
            protocol_status_enum,
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column(
            "acquisition_status",
            acquisition_status_enum,
            nullable=False,
            server_default="ONGOING",
        ),
        sa.Column("access_policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "yaml_customization",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("html_export_cache", sa.Text(), nullable=True),
        sa.Column("html_exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.ForeignKeyConstraint(
            ["access_policy_id"],
            ["access_policies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("protocol_number"),
    )
    op.create_index("ix_protocols_project", "protocols", ["project"])
    op.create_index("ix_protocols_responsible", "protocols", ["responsible"])

    op.create_table(
        "experiment_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("microscope_type", microscope_type_enum, nullable=False),
        sa.Column("watch_folder", sa.String(length=1024), nullable=False),
        sa.Column(
            "thumbnail_max_width",
            sa.Integer(),
            nullable=False,
            server_default="400",
        ),
        sa.Column("operator", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("protocol_id"),
    )

    op.create_table(
        "samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(length=1024), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("access_policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("full_name <> ''", name="ck_samples_full_name_non_empty"),
        sa.CheckConstraint("last_name <> ''", name="ck_samples_last_name_non_empty"),
        sa.ForeignKeyConstraint(["access_policy_id"], ["access_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["samples.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_samples_protocol_id", "samples", ["protocol_id"])
    op.create_index("ix_samples_parent_id", "samples", ["parent_id"])
    op.create_index("ix_samples_full_name", "samples", ["full_name"])

    op.create_table(
        "calibration_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("experiment_configuration_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("picture_type", picture_type_enum, nullable=False),
        sa.Column(
            "auto_calibration",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "databar_removal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("calibration_algorithm", calibration_algorithm_enum, nullable=False),
        sa.CheckConstraint(
            "picture_type <> 'GENERIC_MICROSCOPE_PICTURE'",
            name="ck_calibration_configs_picture_type_not_generic",
        ),
        sa.ForeignKeyConstraint(
            ["experiment_configuration_id"],
            ["experiment_configurations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_configuration_id", "picture_type"),
    )

    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sample_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("attachment_type", attachment_type_enum, nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("extra_info", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(protocol_id IS NOT NULL) <> (sample_id IS NOT NULL)",
            name="ck_attachments_owner_xor",
        ),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "optical_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sample_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column(
            "optical_image_type",
            optical_image_type_enum,
            nullable=False,
            server_default="GENERIC",
        ),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("extra_info", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(protocol_id IS NOT NULL) <> (sample_id IS NOT NULL)",
            name="ck_optical_images_owner_xor",
        ),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "navigation_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("extra_info", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sample_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("extra_info", sa.Text(), nullable=True),
        sa.CheckConstraint("sample_id IS NOT NULL", name="ck_videos_sample_required"),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "microscope_pictures",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("nextval('microscope_picture_id_seq')"),
        ),
        sa.Column("sample_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("sample_path", sa.String(length=1024), nullable=False),
        sa.Column("picture_type", picture_type_enum, nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("extra_info", sa.Text(), nullable=True),
        sa.Column(
            "has_metadata",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("calibration_config_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "processing_status",
            processing_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.ForeignKeyConstraint(["calibration_config_id"], ["calibration_configs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_microscope_pictures_sample_id", "microscope_pictures", ["sample_id"])
    op.create_index("ix_microscope_pictures_picture_type", "microscope_pictures", ["picture_type"])

    op.create_table(
        "image_derivatives",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("picture_id", sa.Integer(), nullable=False),
        sa.Column("derivative_type", image_derivative_type_enum, nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("frame_index", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.ForeignKeyConstraint(["picture_id"], ["microscope_pictures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "data_service_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            data_service_task_status_enum,
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["data_service_clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_data_service_tasks_client_id", "data_service_tasks", ["client_id"])
    op.create_index("ix_data_service_tasks_status", "data_service_tasks", ["status"])

    op.create_table(
        "file_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("context_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("protocol_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("relative_path", sa.String(length=1024), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("decision", file_event_decision_enum, nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column(
            "notified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("TIMEZONE('utc', NOW())"),
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["client_id"], ["data_service_clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("context_id"),
    )
    op.create_index("ix_file_events_client_id", "file_events", ["client_id"])
    op.create_index("ix_file_events_protocol_id", "file_events", ["protocol_id"])
    op.create_index("ix_file_events_decision", "file_events", ["decision"])


def downgrade() -> None:
    op.drop_index("ix_file_events_decision", table_name="file_events")
    op.drop_index("ix_file_events_protocol_id", table_name="file_events")
    op.drop_index("ix_file_events_client_id", table_name="file_events")
    op.drop_table("file_events")

    op.drop_index("ix_data_service_tasks_status", table_name="data_service_tasks")
    op.drop_index("ix_data_service_tasks_client_id", table_name="data_service_tasks")
    op.drop_table("data_service_tasks")

    op.drop_table("image_derivatives")

    op.drop_index("ix_microscope_pictures_picture_type", table_name="microscope_pictures")
    op.drop_index("ix_microscope_pictures_sample_id", table_name="microscope_pictures")
    op.drop_table("microscope_pictures")

    op.drop_table("videos")
    op.drop_table("navigation_images")
    op.drop_table("optical_images")
    op.drop_table("attachments")
    op.drop_table("calibration_configs")

    op.drop_index("ix_samples_full_name", table_name="samples")
    op.drop_index("ix_samples_parent_id", table_name="samples")
    op.drop_index("ix_samples_protocol_id", table_name="samples")
    op.drop_table("samples")

    op.drop_table("experiment_configurations")

    op.drop_index("ix_protocols_responsible", table_name="protocols")
    op.drop_index("ix_protocols_project", table_name="protocols")
    op.drop_table("protocols")

    op.drop_table("data_service_clients")
    op.drop_table("access_policies")

    op.execute(sa.schema.DropSequence(sa.Sequence("microscope_picture_id_seq")))
    op.execute(sa.schema.DropSequence(sa.Sequence("protocol_number_seq")))

    bind = op.get_bind()
    for enum_type in (
        access_policy_scope_type_enum,
        file_event_decision_enum,
        data_service_task_status_enum,
        data_service_client_status_enum,
        calibration_algorithm_enum,
        optical_image_type_enum,
        attachment_type_enum,
        acquisition_status_enum,
        protocol_status_enum,
        microscope_type_enum,
        processing_status_enum,
        image_derivative_type_enum,
        picture_type_enum,
    ):
        enum_type.drop(bind, checkfirst=True)
