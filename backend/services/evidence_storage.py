"""Private storage adapters for operator verification evidence."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Any, Protocol

from backend.config import Settings, get_settings

SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
SAFE_FILENAME = re.compile(r"^[a-f0-9]{32}\.(jpg|jpeg|png|webp)$")


class EvidenceStorage(Protocol):
    def save(self, report_id: str, filename: str, content: bytes, content_type: str) -> None: ...

    def read(self, report_id: str, filename: str) -> bytes: ...

    def delete(self, report_id: str, filename: str) -> None: ...


def _validate_key_parts(report_id: str, filename: str) -> None:
    if not SAFE_REPORT_ID.fullmatch(report_id) or not SAFE_FILENAME.fullmatch(filename):
        raise ValueError("Invalid private evidence storage key.")


class LocalEvidenceStorage:
    """Private local disk store for development and explicitly non-production use."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.base_dir, 0o700)

    def _path(self, report_id: str, filename: str) -> Path:
        _validate_key_parts(report_id, filename)
        path = (self.base_dir / report_id / filename).resolve()
        if not path.is_relative_to(self.base_dir):
            raise ValueError("Evidence path escaped the configured storage directory.")
        return path

    def save(self, report_id: str, filename: str, content: bytes, content_type: str) -> None:
        del content_type
        path = self._path(report_id, filename)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)

    def read(self, report_id: str, filename: str) -> bytes:
        path = self._path(report_id, filename)
        if not path.exists():
            legacy_path = (self.base_dir / filename).resolve()
            if legacy_path.parent == self.base_dir:
                path = legacy_path
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            raise
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise FileNotFoundError("Private verification evidence not found.")
            return source.read()

    def delete(self, report_id: str, filename: str) -> None:
        path = self._path(report_id, filename)
        if not path.exists():
            legacy_path = (self.base_dir / filename).resolve()
            if legacy_path.parent == self.base_dir:
                path = legacy_path
        try:
            path.unlink()
            if path.parent != self.base_dir:
                path.parent.rmdir()
        except FileNotFoundError:
            return


class S3EvidenceStorage:
    """Private S3-compatible storage; access is always proxied through API auth."""

    def __init__(self, client: Any, bucket: str):
        if not bucket:
            raise ValueError("Configure a dedicated verification-evidence S3 bucket.")
        self.client = client
        self.bucket = bucket

    @staticmethod
    def _key(report_id: str, filename: str) -> str:
        _validate_key_parts(report_id, filename)
        return f"verification-evidence/{report_id}/{filename}"

    def save(self, report_id: str, filename: str, content: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket,
            Key=self._key(report_id, filename),
            Body=content,
            ContentType=content_type,
            CacheControl="private, no-store",
            ServerSideEncryption="AES256",
        )

    def read(self, report_id: str, filename: str) -> bytes:
        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=self._key(report_id, filename),
            )
        except Exception as exc:
            response = getattr(exc, "response", {})
            code = str(response.get("Error", {}).get("Code", ""))
            if code in {"NoSuchKey", "NotFound", "404"}:
                raise FileNotFoundError("Private verification evidence not found.") from exc
            raise
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def delete(self, report_id: str, filename: str) -> None:
        self.client.delete_object(
            Bucket=self.bucket,
            Key=self._key(report_id, filename),
        )


def build_evidence_storage(settings: Settings | None = None) -> EvidenceStorage:
    settings = settings or get_settings()
    backend = settings.verification_evidence_storage.strip().lower()
    if backend == "local":
        if settings.environment.strip().lower() == "production":
            raise RuntimeError(
                "Local verification evidence storage is disabled in production; configure S3."
            )
        return LocalEvidenceStorage(settings.verification_evidence_local_dir)
    if backend != "s3":
        raise ValueError("VERIFICATION_EVIDENCE_STORAGE must be 'local' or 's3'.")
    if bool(settings.aws_access_key_id) != bool(settings.aws_secret_access_key):
        raise ValueError("Configure both AWS access key fields or use the AWS role credential chain.")
    if (
        not settings.verification_evidence_s3_bucket
        or settings.verification_evidence_s3_bucket == settings.aws_s3_bucket_name
    ):
        raise ValueError(
            "VERIFICATION_EVIDENCE_S3_BUCKET must name a dedicated bucket, separate "
            "from AWS_S3_BUCKET_NAME."
        )

    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("The boto3 package is required for S3 evidence storage.") from exc

    client_options: dict[str, str] = {"region_name": settings.aws_region}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        client_options["aws_access_key_id"] = settings.aws_access_key_id
        client_options["aws_secret_access_key"] = settings.aws_secret_access_key
    return S3EvidenceStorage(
        boto3.client("s3", **client_options),
        settings.verification_evidence_s3_bucket,
    )
