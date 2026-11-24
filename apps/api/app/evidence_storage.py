"""Private server-side storage for receivable evidence files."""

import os
import socket
import struct
import tempfile
from pathlib import Path
from uuid import UUID

from .config import settings


class EvidenceScannerUnavailable(RuntimeError):
    """The private malware scanner could not validate an uploaded file."""


class EvidenceMalwareDetected(ValueError):
    """The private malware scanner rejected an uploaded file."""


def scan_evidence(content: bytes) -> None:
    """Fail closed using a private clamd INSTREAM endpoint on a trusted network."""
    if not settings.evidence_scanner_host:
        raise EvidenceScannerUnavailable("EVIDENCE_SCANNER_HOST is not configured")
    try:
        with socket.create_connection(
            (settings.evidence_scanner_host, settings.evidence_scanner_port),
            timeout=settings.evidence_scanner_timeout_seconds,
        ) as connection:
            connection.settimeout(settings.evidence_scanner_timeout_seconds)
            connection.sendall(b"zINSTREAM\0")
            for offset in range(0, len(content), 64 * 1024):
                chunk = content[offset:offset + 64 * 1024]
                connection.sendall(struct.pack("!I", len(chunk)) + chunk)
            connection.sendall(struct.pack("!I", 0))
            response = bytearray()
            while not response.endswith(b"\0"):
                chunk = connection.recv(4096)
                if not chunk:
                    raise EvidenceScannerUnavailable("Scanner closed without a verdict")
                response.extend(chunk)
                if len(response) > 4096:
                    raise EvidenceScannerUnavailable("Scanner response exceeded the limit")
    except EvidenceScannerUnavailable:
        raise
    except OSError as exc:
        raise EvidenceScannerUnavailable("Private evidence scanner is unavailable") from exc

    verdict = bytes(response).rstrip(b"\0").decode("utf-8", errors="replace")
    if verdict.endswith(" FOUND"):
        raise EvidenceMalwareDetected("Uploaded evidence was rejected by malware scanning")
    if not verdict.endswith(" OK"):
        raise EvidenceScannerUnavailable("Private evidence scanner returned no valid verdict")


def _s3_client():
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - deployment configuration guard
        raise RuntimeError("S3 evidence storage requires boto3 in the API image") from exc
    return boto3.client(
        "s3",
        region_name=settings.evidence_s3_region,
        endpoint_url=settings.evidence_s3_endpoint_url or None,
        aws_access_key_id=settings.evidence_s3_access_key or None,
        aws_secret_access_key=settings.evidence_s3_secret_key or None,
    )


def put_private(key: str, content: bytes, content_type: str) -> None:
    if settings.evidence_storage_backend == "s3":
        _s3_client().put_object(
            Bucket=settings.evidence_s3_bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
            ServerSideEncryption="AES256",
            Metadata={"visibility": "private"},
        )
        return
    path = Path(settings.uploads_dir).resolve() / "receivables" / key
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".upload-", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(content)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    finally:
        if "temp_path" in locals():
            temp_path.unlink(missing_ok=True)


def delete_private(key: str) -> None:
    if settings.evidence_storage_backend == "s3":
        _s3_client().delete_object(Bucket=settings.evidence_s3_bucket, Key=key)
        return
    root = (Path(settings.uploads_dir).resolve() / "receivables").resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise ValueError("Invalid private evidence key")
    path.unlink(missing_ok=True)


def get_private(key: str) -> bytes:
    if settings.evidence_storage_backend == "s3":
        result = _s3_client().get_object(Bucket=settings.evidence_s3_bucket, Key=key)
        try:
            return result["Body"].read()
        finally:
            result["Body"].close()
    root = (Path(settings.uploads_dir).resolve() / "receivables").resolve()
    path = (root / key).resolve()
    if root not in path.parents:
        raise ValueError("Invalid private evidence key")
    return path.read_bytes()


def storage_ready() -> bool:
    if settings.evidence_storage_backend == "s3":
        return bool(settings.evidence_s3_bucket)
    return settings.app_env.lower() != "production" or settings.evidence_local_storage_persistent


def safe_key(organization_id: UUID, case_id: UUID, artifact_id: UUID, suffix: str) -> str:
    extension = suffix.lower()
    if extension not in {".pdf", ".csv"}:
        raise ValueError("Unsupported evidence file extension")
    return f"{organization_id}/{case_id}/{artifact_id}{extension}"
