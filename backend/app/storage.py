"""Where uploaded file bytes live: Cloudflare R2 (S3-compatible, private bucket).

Used when all four environment values are set (R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET).
Without them (local development, tests) the bytes stay in the database, exactly as before.

 - The bucket is private. Files only ever leave through our own download endpoint, which checks room membership.
 - Object keys are random (rooms/<room id>/<random hex>), never the user's file name.
 - When a file row is deleted (by hand, or because its room was deleted), its object is removed from R2
   right after the database commit succeeds. A rolled-back delete never touches R2.
"""
import logging
import os
import uuid

from sqlalchemy import event
from sqlalchemy.orm import Session, object_session

from .models import RoomFile

log = logging.getLogger("roomsync.storage")
_client = None
_NEEDED = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")


class StorageError(Exception):
    """R2 could not be reached or refused the request. The message never contains secrets."""


def enabled() -> bool:
    return all(os.getenv(name) for name in _NEEDED)


def _s3():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config

        _client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=30,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )
    return _client


def new_key(room_id: int) -> str:
    return f"rooms/{room_id}/{uuid.uuid4().hex}"


def put(key: str, data: bytes) -> None:
    try:
        _s3().put_object(Bucket=os.environ["R2_BUCKET"], Key=key, Body=data, ContentType="application/octet-stream")
    except Exception as problem:
        log.error("R2 upload failed (%s)", type(problem).__name__)
        raise StorageError("upload failed") from problem


def get(key: str, limit: int | None = None) -> bytes:
    """The object's bytes, or just the first `limit` bytes."""
    try:
        extra = {"Range": f"bytes=0-{limit - 1}"} if limit else {}
        return _s3().get_object(Bucket=os.environ["R2_BUCKET"], Key=key, **extra)["Body"].read()
    except Exception as problem:
        log.error("R2 download failed (%s)", type(problem).__name__)
        raise StorageError("download failed") from problem


def delete_many(keys: list[str]) -> None:
    """Best effort: a failure here is logged, never shown to the user (the database row is already gone)."""
    for start in range(0, len(keys), 1000):
        batch = keys[start:start + 1000]
        try:
            _s3().delete_objects(
                Bucket=os.environ["R2_BUCKET"], Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True}
            )
        except Exception as problem:
            log.error("R2 delete failed for %d object(s) (%s)", len(batch), type(problem).__name__)


# ---- keep R2 in step with the database -------------------------------------------------------------
@event.listens_for(RoomFile, "after_delete")
def _queue_object_for_removal(mapper, connection, row):
    if row.storage_key:
        session = object_session(row)
        if session is not None:
            session.info.setdefault("r2_delete", []).append(row.storage_key)


@event.listens_for(Session, "after_commit")
def _remove_queued_objects(session):
    keys = session.info.pop("r2_delete", None)
    if keys:
        delete_many(keys)


@event.listens_for(Session, "after_rollback")
def _forget_queued_objects(session):
    session.info.pop("r2_delete", None)
