from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.domain.models import (
    AccessPolicy,
    Attachment,
    CalibrationConfig,
    Comment,
    DataServiceClient,
    DataServiceTask,
    ExperimentConfiguration,
    FileEvent,
    ImageDerivative,
    MicroscopePicture,
    NavigationImage,
    OpticalImage,
    Protocol,
    Sample,
    UnitPolicy,
    User,
    Video,
)
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


def make_access_policy() -> AccessPolicy:
    return AccessPolicy(
        id=uuid4(),
        scope_type=AccessPolicyScopeType.OPEN,
        allowed_ids=[uuid4()],
        owner_id=uuid4(),
    )


def make_protocol(access_policy_id):
    return Protocol(
        id=uuid4(),
        protocol_number=1,
        status=ProtocolStatus.DRAFT,
        acquisition_status=AcquisitionStatus.ONGOING,
        access_policy_id=access_policy_id,
        project="Project A",
    )


def make_sample(access_policy_id):
    return Sample(
        id=uuid4(),
        full_name="Sample Full",
        last_name="Sample Last",
        access_policy_id=access_policy_id,
    )


@pytest.mark.parametrize(
    ("model_class", "kwargs"),
    [
        (AccessPolicy, {}),
        (CalibrationConfig, {}),
        (Sample, {}),
        (Protocol, {}),
        (Attachment, {}),
        (ExperimentConfiguration, {}),
        (DataServiceClient, {}),
        (DataServiceTask, {}),
        (FileEvent, {}),
        (MicroscopePicture, {}),
        (ImageDerivative, {}),
        (User, {}),
    ],
)
def test_required_fields_raise_validation_error(model_class, kwargs) -> None:
    with pytest.raises(ValidationError):
        model_class(**kwargs)


def test_domain_models_happy_path_instantiation() -> None:
    access_policy = make_access_policy()
    sample = make_sample(access_policy.id)
    protocol = make_protocol(access_policy.id)
    calibration = CalibrationConfig(
        picture_type=PictureType.QUATTRO_MICROSCOPE_PICTURE,
        calibration_algorithm=CalibrationAlgorithm.FEI_TAG,
    )
    picture = MicroscopePicture(
        params={"exposure": 1},
        processing_status=ProcessingStatus.PENDING,
        has_metadata=True,
        calibration_config_picture_type=calibration.picture_type,
    )
    derivative = ImageDerivative(
        microscope_picture_id=1,
        derivative_type=DerivativeType.THUMBNAIL,
    )
    attachment = Attachment(protocol_id=protocol.id)
    optical_image = OpticalImage(
        protocol_id=protocol.id,
        caption="Optical",
        description="Overview",
        extra_info={},
    )
    navigation_image = NavigationImage(
        sample_id=sample.id,
        caption="Navigation",
        description="Context",
        extra_info={},
    )
    video = Video(
        protocol_id=protocol.id,
        caption="Video",
        description="Recording",
        extra_info={},
    )
    experiment_configuration = ExperimentConfiguration(watch_folder="C:/watch")
    client = DataServiceClient(
        id=uuid4(),
        hostname="acq-pc-01",
        watch_folder="C:/watch",
        os_info="Windows 11",
        agent_version="0.1.0",
        api_key_hash="hashed-api-key",
        status=DataServiceClientStatus.ONLINE,
        is_revoked=False,
    )
    task = DataServiceTask(
        client_id=client.id,
        task_type="sync-folder",
        operation="collect",
        params={"path": "/opaque"},
        status=DataServiceTaskStatus.PENDING,
    )
    file_event = FileEvent(
        context_id=uuid4(),
        decision=FileEventDecision.ACCEPT,
    )
    user = User(
        email="user@example.com",
        username="user1",
        role=UserRole.OPERATOR,
        hashed_password="hashed",
        is_active=True,
    )

    assert access_policy.id is not None
    assert sample.access_policy_id == access_policy.id
    assert protocol.access_policy_id == access_policy.id
    assert picture.calibration_config_picture_type == calibration.picture_type
    assert derivative.derivative_type == DerivativeType.THUMBNAIL
    assert attachment.protocol_id == protocol.id
    assert optical_image.caption == "Optical"
    assert navigation_image.sample_id == sample.id
    assert video.description == "Recording"
    assert experiment_configuration.watch_folder == "C:/watch"
    assert client.hostname == "acq-pc-01"
    assert client.status == DataServiceClientStatus.ONLINE
    assert task.task_type == "sync-folder"
    assert file_event.decision == FileEventDecision.ACCEPT
    assert user.role == UserRole.OPERATOR


@pytest.mark.asyncio
async def test_sqlite_metadata_round_trip(db_session) -> None:
    access_policy = make_access_policy()
    sample = make_sample(access_policy.id)
    protocol = make_protocol(access_policy.id)

    db_session.add(access_policy)
    db_session.add(sample)
    db_session.add(protocol)
    await db_session.commit()

    rows = await db_session.execute(select(Protocol).where(Protocol.id == protocol.id))
    persisted_protocol = rows.scalar_one()

    assert persisted_protocol.protocol_number == 1
    assert persisted_protocol.acquisition_status == AcquisitionStatus.ONGOING


def test_protocol_item_mixin_columns_present_on_protocol_items() -> None:
    protocol_item_models = [
        MicroscopePicture,
        Attachment,
        OpticalImage,
        NavigationImage,
        Video,
    ]

    for model in protocol_item_models:
        assert "caption" in model.__table__.c
        assert "description" in model.__table__.c
        assert "extra_info" in model.__table__.c


def test_comment_parent_id_nullable() -> None:
    assert Comment.__table__.c.parent_id.nullable is True


def test_unit_policy_unit_id_nullable() -> None:
    assert UnitPolicy.__table__.c.unit_id.nullable is True


def test_protocol_removed_fields_not_present() -> None:
    assert not hasattr(Protocol, "yaml_customization")
    assert not hasattr(Protocol, "responsible")
