import secrets
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBasic, HTTPBasicCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import service as auth_svc
from src.auth.models import User
from src.config import AuthSettings, Settings
from src.core.db import get_session
from src.mail.client import MailClient
from src.core.rabbitmq import RabbitMQClient
from src.core.s3 import S3Client
from src.runtime import AppContainer
from src.inspector.service import InspectorService

_bearer = HTTPBearer(auto_error=False)
_basic = HTTPBasic(auto_error=False)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container


async def get_db(
    container: Annotated[AppContainer, Depends(get_container)],
) -> AsyncIterator[AsyncSession]:
    async for session in get_session(container.session_factory):
        yield session


def get_auth_settings(
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthSettings:
    return container.settings.auth


def get_settings(
    container: Annotated[AppContainer, Depends(get_container)],
) -> Settings:
    return container.settings


def get_s3(
    container: Annotated[AppContainer, Depends(get_container)],
) -> S3Client:
    return container.s3


def get_rabbitmq(
    container: Annotated[AppContainer, Depends(get_container)],
) -> RabbitMQClient:
    return container.rabbitmq


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    container: Annotated[AppContainer, Depends(get_container)],
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
) -> User:
    """
    Resolve the current user from a Bearer token, x-user-id (dev only), or dev bypass.

    Uses a short-lived session scoped only to the auth lookup — NOT the full
    request lifetime — so long-running SSE/streaming endpoints don't hold an
    idle DB connection open for minutes until the server kills it.
    """
    async with container.session_factory() as db:
        if credentials is None:
            x_user_id = request.headers.get("x-user-id")
            if x_user_id and settings.dev_bypass_enabled:
                try:
                    user_id = uuid.UUID(x_user_id.strip())
                    user = await auth_svc.get_user_by_id(db, user_id)
                    if user and user.is_active:
                        return user
                except (ValueError, TypeError):
                    pass
            if settings.dev_bypass_enabled:
                return await auth_svc.get_or_create_dev_user(
                    db, settings.dev_bypass_email
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            user_id, jti = auth_svc.decode_access_token(
                credentials.credentials, settings
            )
        except JWTError as exc:
            x_user_id = request.headers.get("x-user-id")
            if x_user_id and settings.dev_bypass_enabled:
                try:
                    uid = uuid.UUID(x_user_id.strip())
                    user = await auth_svc.get_user_by_id(db, uid)
                    if user and user.is_active:
                        return user
                except (ValueError, TypeError):
                    pass
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired access token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        # Single query: fetch user + check JTI not revoked
        user = await auth_svc.get_user_if_jti_valid(db, user_id, jti)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token revoked or user not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return user


# Convenient type alias used in route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_inspector_service(
    container: AppContainer = Depends(get_container),
) -> InspectorService:
    return InspectorService(
        session_factory=container.session_factory,
        s3=container.s3,
        qdrant=container.qdrant,
    )


def get_prompt_manager(
    container: Annotated[AppContainer, Depends(get_container)],
):
    return container.prompt_manager


def get_prompt_service(
    container: Annotated[AppContainer, Depends(get_container)],
):
    from src.prompts.service import PromptService

    return PromptService(session_factory=container.session_factory)


def get_mail_client(
    container: Annotated[AppContainer, Depends(get_container)],
) -> MailClient:
    return container.mail_client


async def require_admin_secret(
    request: Request,
    container: Annotated[AppContainer, Depends(get_container)],
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_basic)] = None,
) -> None:
    from src.api.admin_blacklist import AdminBruteForceGuard

    secret = container.settings.auth.admin_secret
    if not secret:
        return  # dev mode: no password configured

    ip = request.client.host if request.client else "unknown"
    guard: AdminBruteForceGuard = request.app.state.admin_brute_force

    if await guard.is_blacklisted(ip, container.session_factory):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": 'Basic realm="Admin Panel"'},
        )

    username_ok = secrets.compare_digest(
        credentials.username.encode(), container.settings.auth.admin_username.encode()
    )
    password_ok = secrets.compare_digest(
        credentials.password.encode(), secret.encode()
    )

    if not username_ok or not password_ok:
        just_blacklisted = await guard.record_failure(
            ip,
            container.settings.auth.admin_max_failed_attempts,
            container.session_factory,
        )
        if just_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="Admin Panel"'},
        )

    guard.record_success(ip)
