import logging
from types import TracebackType
from typing import Any

import aioboto3
from botocore.config import Config

from src.config import S3Settings

logger = logging.getLogger(__name__)


class S3Client:
    """
    Thin async wrapper around aioboto3's S3 resource.

    Lifecycle
    ---------
    Use as an async context manager or call open()/close() manually.
    Typically created once during app startup and stored on app.state.
    """

    def __init__(self, settings: S3Settings) -> None:
        self._settings = settings
        self._session = aioboto3.Session()
        self._client: Any = None  # botocore.client.S3
        # Optional second client used only to sign presigned URLs against a
        # browser-reachable endpoint (see S3Settings.public_endpoint_url).
        self._presign_ctx: Any = None
        self._presign_client: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _client_kwargs(self, endpoint_url: str | None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "aws_access_key_id": self._settings.access_key_id,
            "aws_secret_access_key": self._settings.secret_access_key,
            "region_name": self._settings.region,
            "use_ssl": self._settings.use_ssl,
            "config": Config(
                s3=(
                    {"addressing_style": "path"}
                    if self._settings.use_path_style
                    else {}
                ),
                signature_version="s3v4",
            ),
        }
        if endpoint_url and endpoint_url.strip():
            kwargs["endpoint_url"] = endpoint_url
        return kwargs

    async def open(self) -> None:
        self._ctx = self._session.client(
            "s3", **self._client_kwargs(self._settings.endpoint_url)
        )
        self._client = await self._ctx.__aenter__()

        public = self._settings.public_endpoint_url.strip()
        if public and public != self._settings.endpoint_url.strip():
            self._presign_ctx = self._session.client(
                "s3", **self._client_kwargs(public)
            )
            self._presign_client = await self._presign_ctx.__aenter__()

    async def close(self) -> None:
        """Exit the aioboto3 client context. Call once at shutdown."""
        if self._presign_ctx is not None:
            await self._presign_ctx.__aexit__(None, None, None)
            self._presign_ctx = None
            self._presign_client = None
        if self._ctx is not None:
            await self._ctx.__aexit__(None, None, None)

    async def __aenter__(self) -> "S3Client":
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Bucket bootstrap
    # ------------------------------------------------------------------

    async def ensure_bucket(self) -> None:
        """Create the configured bucket if it doesn't already exist."""
        bucket = self._settings.bucket
        region = self._settings.region
        try:
            await self._client.head_bucket(Bucket=bucket)
            logger.debug("S3 bucket %r already exists", bucket)
        except self._client.exceptions.ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code not in ("403", "404", "NoSuchBucket", "AccessDenied"):
                raise
            create_kwargs: dict[str, Any] = {"Bucket": bucket}
            if region and region != "us-east-1":
                create_kwargs["CreateBucketConfiguration"] = {
                    "LocationConstraint": region,
                }
            try:
                await self._client.create_bucket(**create_kwargs)
                logger.info("Created S3 bucket %r in %r", bucket, region)
            except self._client.exceptions.ClientError as create_exc:
                create_code = create_exc.response["Error"]["Code"]
                if create_code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    logger.debug("S3 bucket %r already exists", bucket)
                    return
                raise

    # ------------------------------------------------------------------
    # Presigned URLs
    # ------------------------------------------------------------------

    @property
    def _signing_client(self) -> Any:
        """Client used for generating presigned URLs.

        Falls back to the regular client when no public endpoint override is
        configured.
        """
        return self._presign_client or self._client

    async def presigned_put_url(
        self,
        key: str,
        *,
        content_type: str,
        expires_in: int = 900,
    ) -> str:
        """
        Generate a presigned PUT URL for direct browser → S3 upload.

        Parameters
        ----------
        key:          S3 object key (e.g. "users/{user_id}/docs/{doc_id}.pdf")
        content_type: MIME type enforced by the presigned URL conditions
        expires_in:   URL validity in seconds (default 15 min)
        """
        url: str = await self._signing_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._settings.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )
        return url

    async def presigned_get_url(
        self,
        key: str,
        *,
        expires_in: int = 3600,
        filename: str | None = None,
    ) -> str:
        """
        Generate a presigned GET URL for downloading/viewing an object.

        Parameters
        ----------
        key:       S3 object key
        expires_in: URL validity in seconds (default 1 hour)
        filename:  If set, adds Content-Disposition: attachment; filename=…
        """
        params: dict[str, Any] = {"Bucket": self._settings.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        url: str = await self._signing_client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in,
        )
        return url

    # ------------------------------------------------------------------
    # Object management
    # ------------------------------------------------------------------

    async def delete_object(self, key: str) -> None:
        """Delete a single object. Silently succeeds if key doesn't exist."""
        await self._client.delete_object(Bucket=self._settings.bucket, Key=key)
        logger.debug("Deleted S3 object %r", key)

    async def delete_objects(self, keys: list[str]) -> None:
        """Batch-delete objects. S3 allows max 1000 per request, so we chunk."""
        if not keys:
            return
        for i in range(0, len(keys), 1000):
            chunk = keys[i : i + 1000]
            await self._client.delete_objects(
                Bucket=self._settings.bucket,
                Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
            )
        logger.debug("Batch-deleted %d S3 objects", len(keys))

    async def upload_bytes(
        self,
        key: str,
        body: bytes,
        *,
        content_type: str,
    ) -> None:
        """Upload raw bytes to the configured bucket."""
        await self._client.put_object(
            Bucket=self._settings.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
        logger.debug("Uploaded S3 object %r", key)

    async def download_bytes(self, key: str) -> bytes:
        """Download an object and return its full content as bytes."""
        response = await self._client.get_object(
            Bucket=self._settings.bucket,
            Key=key,
        )
        async with response["Body"] as stream:
            data = await stream.read()
        logger.debug("Downloaded S3 object %r", key)
        return data
