from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path
from urllib.parse import quote

from pipeline.config import Settings


def _safe_key(key: str) -> str:
    cleaned = key.replace("\\", "/").lstrip("/")
    parts = [p for p in cleaned.split("/") if p not in {"", ".", ".."}]
    if not parts:
        raise ValueError("empty object key")
    return "/".join(parts)


def sign_object(secret: str, key: str, exp: int) -> str:
    message = f"{key}:{exp}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signature(secret: str, key: str, exp: int, signature: str) -> bool:
    if exp < int(time.time()):
        return False
    expected = sign_object(secret, key, exp)
    return hmac.compare_digest(expected, signature)


class LocalStore:
    backend = "local"

    def __init__(self, root: Path, settings: Settings) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings = settings

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        del content_type
        path = self.path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return _safe_key(key)

    def put_file(self, key: str, source: Path, content_type: str = "application/octet-stream") -> str:
        return self.put_bytes(key, source.read_bytes(), content_type)

    def get_bytes(self, key: str) -> bytes:
        return self.path_for(key).read_bytes()

    def path_for(self, key: str) -> Path:
        return self.root / _safe_key(key)

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def materialize(self, key: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        source = self.path_for(key)
        if source.resolve() != dest.resolve():
            dest.write_bytes(source.read_bytes())
        return dest

    def presign(self, key: str, expires_s: int | None = None) -> str:
        ttl = expires_s if expires_s is not None else self.settings.presign_ttl_s
        exp = int(time.time()) + ttl
        safe = _safe_key(key)
        sig = sign_object(self.settings.signing_secret, safe, exp)
        base = self.settings.public_base_url.rstrip("/")
        return f"{base}/objects/{quote(safe)}?exp={exp}&sig={sig}"

    def health(self) -> dict:
        probe = self.root / ".health"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return {"backend": "local", "ok": True}
        except OSError as exc:
            return {"backend": "local", "ok": False, "error": str(exc)}


class S3Store:
    backend = "s3"

    def __init__(
        self,
        settings: Settings,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str = "auto",
        use_ssl: bool = True,
    ) -> None:
        import boto3
        from botocore.config import Config

        self.settings = settings
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint or None,
            aws_access_key_id=access_key or None,
            aws_secret_access_key=secret_key or None,
            region_name=region or "auto",
            use_ssl=use_ssl,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        safe = _safe_key(key)
        self.client.put_object(Bucket=self.bucket, Key=safe, Body=data, ContentType=content_type)
        return safe

    def put_file(self, key: str, source: Path, content_type: str = "application/octet-stream") -> str:
        return self.put_bytes(key, source.read_bytes(), content_type)

    def get_bytes(self, key: str) -> bytes:
        safe = _safe_key(key)
        response = self.client.get_object(Bucket=self.bucket, Key=safe)
        return response["Body"].read()

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.client.head_object(Bucket=self.bucket, Key=_safe_key(key))
            return True
        except ClientError:
            return False

    def materialize(self, key: str, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.get_bytes(key))
        return dest

    def presign(self, key: str, expires_s: int | None = None) -> str:
        ttl = expires_s if expires_s is not None else self.settings.presign_ttl_s
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": _safe_key(key)},
            ExpiresIn=ttl,
        )

    def health(self) -> dict:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return {"backend": "s3", "ok": True, "bucket": self.bucket}
        except Exception as exc:  # noqa: BLE001
            return {"backend": "s3", "ok": False, "bucket": self.bucket, "error": str(exc)}


def object_storage_target(settings: Settings) -> dict | None:
    """Resolve R2 first, then generic S3/MinIO. None means the local disk."""
    if settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key:
        account = settings.r2_account_id.strip()
        return {
            "endpoint": f"https://{account}.r2.cloudflarestorage.com",
            "bucket": settings.r2_bucket or "videomind-media",
            "access_key": settings.r2_access_key_id,
            "secret_key": settings.r2_secret_access_key,
            "region": "auto",
            "use_ssl": True,
        }
    if settings.s3_endpoint or settings.s3_access_key:
        return {
            "endpoint": settings.s3_endpoint,
            "bucket": settings.s3_bucket,
            "access_key": settings.s3_access_key,
            "secret_key": settings.s3_secret_key,
            "region": settings.s3_region or "auto",
            "use_ssl": settings.s3_use_ssl,
        }
    return None


def build_store(settings: Settings) -> LocalStore | S3Store:
    target = object_storage_target(settings)
    if target:
        return S3Store(settings, **target)
    return LocalStore(Path(settings.data_dir) / "objects", settings)
