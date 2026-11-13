from pathlib import Path
from typing import Any

import pytest

from backend.config import Settings
from backend.services.evidence_storage import (
    LocalEvidenceStorage,
    S3EvidenceStorage,
    build_evidence_storage,
)

REPORT_ID = "a" * 36
FILENAME = "b" * 32 + ".jpg"


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_options: dict[str, Any] | None = None

    def put_object(self, **kwargs: Any) -> None:
        self.put_options = kwargs
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]

    def get_object(self, **kwargs: Any) -> dict[str, Any]:
        from io import BytesIO

        return {"Body": BytesIO(self.objects[(kwargs["Bucket"], kwargs["Key"])])}

    def delete_object(self, **kwargs: Any) -> None:
        self.objects.pop((kwargs["Bucket"], kwargs["Key"]), None)


def test_local_evidence_is_private_and_round_trips(tmp_path: Path):
    storage = LocalEvidenceStorage(tmp_path / "private")
    storage.save(REPORT_ID, FILENAME, b"private bytes", "image/jpeg")

    stored = tmp_path / "private" / REPORT_ID / FILENAME
    assert storage.read(REPORT_ID, FILENAME) == b"private bytes"
    assert stored.stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "private" / REPORT_ID).stat().st_mode & 0o777 == 0o700

    storage.delete(REPORT_ID, FILENAME)
    with pytest.raises(FileNotFoundError):
        storage.read(REPORT_ID, FILENAME)


def test_local_evidence_rejects_path_traversal(tmp_path: Path):
    storage = LocalEvidenceStorage(tmp_path / "private")
    with pytest.raises(ValueError):
        storage.read("../outside", FILENAME)
    with pytest.raises(ValueError):
        storage.read(REPORT_ID, "../outside.jpg")


def test_local_storage_reads_legacy_flat_files_without_moving_them(tmp_path: Path):
    storage = LocalEvidenceStorage(tmp_path / "private")
    storage.base_dir.mkdir(exist_ok=True)
    legacy = storage.base_dir / FILENAME
    legacy.write_bytes(b"existing private evidence")

    assert storage.read(REPORT_ID, FILENAME) == b"existing private evidence"
    assert legacy.exists()


def test_s3_evidence_is_encrypted_and_has_no_public_acl():
    client = FakeS3()
    storage = S3EvidenceStorage(client, "private-evidence-test")
    storage.save(REPORT_ID, FILENAME, b"private bytes", "image/jpeg")

    assert client.put_options is not None
    assert client.put_options["ServerSideEncryption"] == "AES256"
    assert client.put_options["CacheControl"] == "private, no-store"
    assert "ACL" not in client.put_options
    assert storage.read(REPORT_ID, FILENAME) == b"private bytes"
    storage.delete(REPORT_ID, FILENAME)
    assert client.objects == {}


def test_production_local_storage_fails_closed():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        VERIFICATION_EVIDENCE_STORAGE="local",
    )
    with pytest.raises(RuntimeError, match="disabled in production"):
        build_evidence_storage(settings)


def test_s3_requires_dedicated_private_bucket():
    settings = Settings(
        _env_file=None,
        VERIFICATION_EVIDENCE_STORAGE="s3",
        VERIFICATION_EVIDENCE_S3_BUCKET="",
    )
    with pytest.raises(ValueError, match="dedicated bucket"):
        build_evidence_storage(settings)
