"""Initial domain models."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260409_0001"
down_revision = None
branch_labels = None
depends_on = None


picture_type_enum = sa.Enum(
    "QUATTRO_MICROSCOPE_PICTURE",
    "VERSA_MICROSCOPE_PICTURE",
    "FEI_MICROSCOPE_PICTURE",
    "VEGA_TIFF_MICROSCOPE_PICTURE",
    "VEGA_JPEG_MICROSCOPE_PICTURE",
    "XL40_VARIANT_A_MICROSCOPE_PICTURE",
    "XL40_VARIANT_B_MICROSCOPE_PICTURE",
    "GENERIC_MICROSCOPE_PICTURE",
    name="picture_type_enum",
)
processing_status_enum = sa.Enum(
    "PENDING",
    "PROCESSING",
    "DONE",
    "ERROR",
    name="processing_status_enum",
)
derivative_type_enum = sa.Enum(
    "THUMBNAIL",
    "FULLSIZE_PNG",
    "DZI",
    "CROPPED",
    "FRAME_PNG",
    name="derivative_type_enum",
)
protocol_status_enum = sa.Enum("DRAFT", "ACTIVE", "LOCKED", name="protocol_status_enum")
acquisition_status_enum = sa.Enum(
    "ONGOING",
    "COMPLETED",
    name="acquisition_status_enum",
)
calibration_algorithm_enum = sa.Enum(
    "FEI_TAG",
    "VEGA_PIXEL_SIZE",
    "XL40_XMP",
    name="calibration_algorithm_enum",
)
data_service_client_status_enum = sa.Enum(
    "ONLINE",
    "OFFLINE",
    "NEVER_SEEN",
    name="data_service_client_status_enum",
)
data_service_task_status_enum = sa.Enum(
    "PENDING",
    "DELIVERED",
    "SUCCESS",
    "ERROR",
    name="data_service_task_status_enum",
)
file_event_decision_enum = sa.Enum("ACCEPT", "IGNORE", name="file_event_decision_enum")
access_policy_scope_type_enum = sa.Enum(
    "OPEN",
    "GROUP",
    "EXPLICIT",
    name="access_policy_scope_type_enum",
)


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("microscope_picture_id_seq")))
    op.execute(sa.schema.CreateSequence(sa.Sequence("protocol_number_seq")))

    op.create_table(
        "access_policies",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("scope_type", access_policy_scope_type_enum, nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=True),
        sa.Column("allowed_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
    )

    op.create_table(
        "calibration_configs",
        sa.Column("picture_type", picture_type_enum, primary_key=True, nullable=False),
        sa.Column("calibration_algorithm", calibration_algorithm_enum, nullable=False),
    )

    op.create_table(
        "data_service_clients",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("session_token", sa.String(length=255), nullable=True),
        sa.Column("status", data_service_client_status_enum, nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False),
    )

    op.create_table(
        "data_service_tasks",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "task_type",
            sa.String(length=255),
            nullable=False,
            comment="Plain string for server-side extensibility without schema changes.",
        ),
        sa.Column("operation", sa.String(length=255), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", data_service_task_status_enum, nullable=False),
    )

    op.create_table(
        "experiment_configurations",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "watch_folder",
            sa.String(length=1024),
            nullable=False,
            comment="Documentation only. The server never uses watch_folder directly.",
        ),
    )

    op.create_table(
        "file_events",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "context_id",
            sa.Uuid(),
            nullable=False,
            comment="Opaque token. data-service must not decode this value.",
        ),
        sa.Column("decision", file_event_decision_enum, nullable=False),
    )

    op.create_table(
        "protocols",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "protocol_number",
            sa.Integer(),
            nullable=False,
            unique=True,
            comment="Application-managed sequence value.",
        ),
        sa.Column("status", protocol_status_enum, nullable=False),
        sa.Column("acquisition_status", acquisition_status_enum, nullable=False),
        sa.Column("access_policy_id", sa.Uuid(), nullable=False),
        sa.Column("yaml_customization", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("html_export_cache", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["access_policy_id"], ["access_policies.id"], ondelete="RESTRICT"),
    )

    op.create_table(
        "samples",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("access_policy_id", sa.Uuid(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["access_policy_id"], ["access_policies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["samples.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "microscope_pictures",
        sa.Column(
            "id",
            sa.Integer(),
            sa.Sequence("microscope_picture_id_seq"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("processing_status", processing_status_enum, nullable=False),
        sa.Column("has_metadata", sa.Boolean(), nullable=False),
        sa.Column("calibration_config_picture_type", picture_type_enum, nullable=False),
        sa.ForeignKeyConstraint(
            ["calibration_config_picture_type"],
            ["calibration_configs.picture_type"],
            ondelete="RESTRICT",
        ),
    )

    op.create_table(
        "attachments",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("protocol_id", sa.Uuid(), nullable=True),
        sa.Column("sample_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "(protocol_id IS NOT NULL) <> (sample_id IS NOT NULL)",
            name="ck_attachments_single_owner",
        ),
        sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sample_id"], ["samples.id"], ondelete="CASCADE"),
    )

    for table_name, constraint_name in (
        ("optical_images", "ck_optical_images_has_owner"),
        ("navigation_images", "ck_navigation_images_has_owner"),
        ("videos", "ck_videos_has_owner"),
    ):
        op.create_table(
            table_name,
            sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
            sa.Column("protocol_id", sa.Uuid(), nullable=True),
            sa.Column("sample_id", sa.Uuid(), nullable=True),
            sa.Column("caption", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("extra_info", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.CheckConstraint(
                "(protocol_id IS NOT NULL) OR (sample_id IS NOT NULL)",
                name=constraint_name,
            ),
            sa.ForeignKeyConstraint(["protocol_id"], ["protocols.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["sample_id"], ["samples.id"], ondelete="CASCADE"),
        )

    op.create_table(
        "image_derivatives",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("microscope_picture_id", sa.Integer(), nullable=False),
        sa.Column("derivative_type", derivative_type_enum, nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["microscope_picture_id"], ["microscope_pictures.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("image_derivatives")
    op.drop_table("videos")
    op.drop_table("navigation_images")
    op.drop_table("optical_images")
    op.drop_table("attachments")
    op.drop_table("microscope_pictures")
    op.drop_table("samples")
    op.drop_table("protocols")
    op.drop_table("file_events")
    op.drop_table("experiment_configurations")
    op.drop_table("data_service_tasks")
    op.drop_table("data_service_clients")
    op.drop_table("calibration_configs")
    op.drop_table("access_policies")

    op.execute(sa.schema.DropSequence(sa.Sequence("protocol_number_seq")))
    op.execute(sa.schema.DropSequence(sa.Sequence("microscope_picture_id_seq")))
