from __future__ import annotations

import inspect
import uuid

import pytest
from sqlalchemy.orm import Session

from app.domain import AccessPolicy
from app.domain import AccessPolicyScopeType
from app.domain import Attachment
from app.domain import AttachmentType
from app.domain import CalibrationAlgorithm
from app.domain import CalibrationConfig
from app.domain import DataServiceClient
from app.domain import DataServiceTask
from app.domain import DerivativeType
from app.domain import ExperimentConfiguration
from app.domain import FileEvent
from app.domain import FileEventDecision
from app.domain import ImageDerivative
from app.domain import MicroscopePicture
from app.domain import MicroscopeType
from app.domain import NavigationImage
from app.domain import OpticalImage
from app.domain import OpticalImageType
from app.domain import PictureType
from app.domain import Protocol
from app.domain import Sample
from app.domain import Video


def _required_init_fields(model_cls: type) -> list[str]:
    signature = inspect.signature(model_cls)
    return [
        name
        for name, parameter in signature.parameters.items()
        if name != "self" and parameter.default is inspect._empty
    ]


MODEL_KWARGS: dict[type, dict[str, object]] = {
    AccessPolicy: {
        "scope_type": AccessPolicyScopeType.OPEN,
        "owner_id": uuid.uuid4(),
    },
    Protocol: {
        "project": "Project A",
        "responsible": "Researcher",
        "microscope_type": MicroscopeType.QUATTRO,
        "access_policy_id": uuid.uuid4(),
        "owner_id": uuid.uuid4(),
    },
    ExperimentConfiguration: {
        "protocol_id": uuid.uuid4(),
        "microscope_type": MicroscopeType.QUATTRO,
        "watch_folder": "/watched",
        "operator": "operator",
    },
    CalibrationConfig: {
        "experiment_configuration_id": uuid.uuid4(),
        "picture_type": PictureType.QUATTRO_MICROSCOPE_PICTURE,
        "calibration_algorithm": CalibrationAlgorithm.FEI_TAG,
    },
    Sample: {
        "protocol_id": uuid.uuid4(),
        "full_name": "Primary Sample",
        "last_name": "Sample",
        "access_policy_id": uuid.uuid4(),
    },
    MicroscopePicture: {
        "sample_id": uuid.uuid4(),
        "storage_key": "pictures/sample.dat",
        "original_filename": "sample.dat",
        "sample_path": "/input/sample.dat",
        "picture_type": PictureType.GENERIC_MICROSCOPE_PICTURE,
    },
    ImageDerivative: {
        "picture_id": 1,
        "derivative_type": DerivativeType.THUMBNAIL,
        "storage_key": "pictures/sample-thumb.png",
    },
    Attachment: {
        "protocol_id": uuid.uuid4(),
        "storage_key": "attachments/file.txt",
        "original_filename": "file.txt",
        "file_size": 123,
        "attachment_type": AttachmentType.GENERIC,
    },
    OpticalImage: {
        "protocol_id": uuid.uuid4(),
        "storage_key": "optical/image.png",
        "original_filename": "image.png",
        "file_size": 456,
        "optical_image_type": OpticalImageType.GENERIC,
    },
    NavigationImage: {
        "protocol_id": uuid.uuid4(),
        "storage_key": "navigation/map.png",
        "original_filename": "map.png",
        "file_size": 789,
    },
    Video: {
        "sample_id": uuid.uuid4(),
        "storage_key": "videos/video.mp4",
        "original_filename": "video.mp4",
        "file_size": 999,
    },
    DataServiceClient: {
        "hostname": "host-1",
        "display_name": "Host 1",
        "ip_address": "127.0.0.1",
        "watch_folder": "/watch",
        "api_key_hash": "hash",
    },
    DataServiceTask: {
        "client_id": uuid.uuid4(),
        "task_type": "sync",
        "operation": "scan",
    },
    FileEvent: {
        "context_id": uuid.uuid4(),
        "client_id": uuid.uuid4(),
        "relative_path": "folder/file.dat",
        "filename": "file.dat",
        "file_size": 321,
        "decision": FileEventDecision.ACCEPT,
    },
}


@pytest.mark.parametrize("model_cls", list(MODEL_KWARGS))
def test_domain_model_can_be_constructed_with_minimal_required_fields(model_cls: type) -> None:
    instance = model_cls(**MODEL_KWARGS[model_cls])
    assert instance is not None


@pytest.mark.parametrize("model_cls", list(MODEL_KWARGS))
def test_domain_model_missing_required_fields_raise_type_error(model_cls: type) -> None:
    base_kwargs = MODEL_KWARGS[model_cls]
    for field_name in _required_init_fields(model_cls):
        incomplete_kwargs = dict(base_kwargs)
        incomplete_kwargs.pop(field_name, None)
        with pytest.raises(TypeError):
            model_cls(**incomplete_kwargs)


def test_sample_microscope_picture_fixture_is_minimally_valid(sample_microscope_picture: MicroscopePicture) -> None:
    assert sample_microscope_picture.storage_key == "microscope/sample-1.dat"
    assert sample_microscope_picture.picture_type is PictureType.GENERIC_MICROSCOPE_PICTURE


def test_sqlite_in_memory_session_can_persist_sample_microscope_picture(
    db_session: Session,
    sample_microscope_picture: MicroscopePicture,
) -> None:
    access_policy = AccessPolicy(
        scope_type=AccessPolicyScopeType.OPEN,
        owner_id=uuid.uuid4(),
    )
    protocol = Protocol(
        project="SQLite Test",
        responsible="Tester",
        microscope_type=MicroscopeType.QUATTRO,
        access_policy_id=access_policy.id,
        owner_id=uuid.uuid4(),
    )
    protocol.protocol_number = 123
    protocol.html_exported_at = None
    sample = Sample(
        protocol_id=protocol.id,
        full_name="Persisted Sample",
        last_name="Sample",
        access_policy_id=access_policy.id,
    )
    sample_microscope_picture.sample_id = sample.id

    db_session.add(access_policy)
    db_session.add(protocol)
    db_session.add(sample)
    db_session.add(sample_microscope_picture)
    db_session.commit()

    persisted = db_session.get(MicroscopePicture, sample_microscope_picture.id)
    assert persisted is not None
    assert persisted.storage_key == sample_microscope_picture.storage_key
