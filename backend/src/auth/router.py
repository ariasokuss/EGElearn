import logging
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import RedirectResponse
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.activity.service import ActivityEventInput, log_activity_from_request
from src.api.deps import CurrentUser, get_auth_settings, get_db
from src.auth import service as auth_svc
from src.auth.google_oauth import (
    build_google_authorization_url,
    decode_oauth_state_jwt,
    exchange_authorization_code,
    google_is_configured,
)
from src.auth.models import User
from src.auth.schemas import (
    DesktopLoginRequest,
    GoogleAuthorizationUrlResponse,
    GoogleCredentialRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserOut,
)
from src.config import AuthSettings

router = APIRouter(prefix="/auth", tags=["auth"])

logger = logging.getLogger(__name__)

DbDep = Annotated[AsyncSession, Depends(get_db)]
AuthDep = Annotated[AuthSettings, Depends(get_auth_settings)]


def _auth_replay_payload(action: str, method: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "items": [
            {
                "kind": "user_action",
                "title": "Authentication",
                "value": action,
                "method": method,
            }
        ],
    }


def _log_auth_activity(
    request: Request,
    *,
    user_id: uuid.UUID,
    event_type: str,
    auth_method: str,
    metadata: dict[str, object] | None = None,
) -> None:
    labels = {
        "user_registered": "Registered account",
        "user_logged_in": "Logged in",
        "user_logged_out": "Logged out",
    }
    event_metadata = {"auth_method": auth_method, **(metadata or {})}
    log_activity_from_request(
        request,
        ActivityEventInput(
            user_id=user_id,
            event_type=event_type,
            event_group="auth",
            request_path=str(request.url.path),
            http_method=request.method,
            route_label=labels.get(event_type),
            entity_type="user",
            entity_id=user_id,
            metadata=event_metadata,
            replay_payload=_auth_replay_payload(
                labels.get(event_type) or event_type.replace("_", " ").title(),
                auth_method,
            ),
        ),
    )


def _decode_issued_user_id(
    tokens: TokenPair,
    settings: AuthSettings,
    *,
    context: str,
) -> uuid.UUID | None:
    try:
        user_id, _jti = auth_svc.decode_access_token(tokens.access_token, settings)
        return user_id
    except Exception:
        logger.exception("Failed to decode issued access token for %s activity", context)
        return None


# ---------------------------------------------------------------------------
# Background helpers (run after response is sent)
# ---------------------------------------------------------------------------


async def _post_registration_work(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    ref_code: str | None,
    visitor_id: str | None,
    *,
    attribute_referral_now: bool,
) -> None:
    """Seed roadmap progress and record referral attribution in the background.

    `attribute_referral_now` should be True only when the email is already
    verified at creation time (Google OAuth, dev-bypass). Email/password
    registrations defer attribution to `verify_email` so a typo'd address
    cannot inflate referral counts before the user proves ownership.
    """
    try:
        async with session_factory() as db:
            from src.roadmap.seed import seed_progress_for_user

            await seed_progress_for_user(db, user_id)

            if attribute_referral_now and ref_code:
                from src.referral.service import create_attribution

                await create_attribution(db, ref_code, user_id, visitor_id)

            await db.commit()
    except Exception:
        logger.exception(
            "Background post-registration work failed for user %s", user_id
        )


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new account",
)
async def register(
    body: RegisterRequest,
    db: DbDep,
    request: Request,
    background_tasks: BackgroundTasks,
) -> User:
    try:
        user = await auth_svc.register_user(
            db, body.email, body.password, body.ref_code, body.visitor_id
        )
    except auth_svc.AuthError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # Seed progress in background. Referral attribution is deferred until the
    # user verifies their email — see verify_email in src/mail/service.py.
    session_factory = request.app.state.container.session_factory
    background_tasks.add_task(
        _post_registration_work,
        session_factory,
        user.id,
        body.ref_code,
        body.visitor_id,
        attribute_referral_now=False,
    )
    _log_auth_activity(
        request,
        user_id=user.id,
        event_type="user_registered",
        auth_method="password",
        metadata={"has_referral": bool(body.ref_code or body.visitor_id)},
    )

    return user


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Obtain access + refresh tokens",
)
async def login(
    body: LoginRequest,
    db: DbDep,
    settings: AuthDep,
    request: Request,
) -> TokenPair:
    try:
        tokens = await auth_svc.login_user(db, body.email, body.password, settings)
    except auth_svc.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    user_id = _decode_issued_user_id(tokens, settings, context="password login")
    if user_id is not None:
        _log_auth_activity(
            request,
            user_id=user_id,
            event_type="user_logged_in",
            auth_method="password",
        )
    return tokens


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotate refresh token and get a new access token",
)
async def refresh(
    body: RefreshRequest,
    db: DbDep,
    settings: AuthDep,
) -> TokenPair:
    try:
        return await auth_svc.refresh_tokens(db, body.refresh_token, settings)
    except auth_svc.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post(
    "/desktop-login",
    response_model=TokenPair,
    summary="Exchange a desktop email login token for access + refresh tokens",
)
async def desktop_login(
    body: DesktopLoginRequest,
    db: DbDep,
    settings: AuthDep,
    request: Request,
) -> TokenPair:
    try:
        tokens = await auth_svc.exchange_desktop_login_token(db, body.token, settings)
    except auth_svc.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    user_id = _decode_issued_user_id(tokens, settings, context="desktop login")
    if user_id is not None:
        _log_auth_activity(
            request,
            user_id=user_id,
            event_type="user_logged_in",
            auth_method="desktop_link",
        )
    return tokens


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token",
)
async def logout(
    body: RefreshRequest,
    db: DbDep,
    request: Request,
) -> None:
    user_id = await auth_svc.logout_user(db, body.refresh_token)
    if user_id is not None:
        _log_auth_activity(
            request,
            user_id=user_id,
            event_type="user_logged_out",
            auth_method="refresh_token",
        )


@router.get(
    "/me",
    response_model=UserOut,
    summary="Return the currently authenticated user",
)
async def me(
    current_user: CurrentUser,
    request: Request,
) -> dict:
    data = UserOut.model_validate(current_user).model_dump()
    if current_user.avatar_s3_key:
        from src.api.deps import get_container

        s3 = get_container(request).s3
        data["avatar_url"] = await s3.presigned_get_url(
            current_user.avatar_s3_key, expires_in=86400
        )
    return data


# ---------------------------------------------------------------------------
# Google OAuth 2.0
# ---------------------------------------------------------------------------


def _fragment_redirect(base_url: str, params: dict[str, str]) -> RedirectResponse:
    from urllib.parse import quote, urlencode

    frag = urlencode(params, quote_via=quote)
    return RedirectResponse(url=f"{base_url.rstrip('/')}#{frag}", status_code=302)


@router.get(
    "/google",
    summary="Start Google OAuth (302 redirect to Google, or JSON with authorization URL)",
    response_model=None,
    response_description=(
        "302 to accounts.google.com with OAuth parameters, or JSON when format=json. "
        "The authorization URL always includes `prompt` (default `select_account`) "
        "unless overridden via the `prompt` query parameter."
    ),
)
async def google_oauth_start(
    settings: AuthDep,
    format: str | None = None,
    prompt: str | None = Query(
        None,
        description=(
            "Forwarded to Google as the OpenID Connect `prompt` parameter. "
            "Use space-separated values from: `none`, `login`, `consent`, "
            "`select_account`. Omit or leave empty to use `select_account` "
            "(show account picker instead of silent re-auth)."
        ),
        examples=["select_account", "consent", "login", "none"],
    ),
    ref_code: str | None = Query(None, max_length=64),
    visitor_id: str | None = Query(None, max_length=36),
) -> RedirectResponse | GoogleAuthorizationUrlResponse:
    if not google_is_configured(settings):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )
    try:
        url = build_google_authorization_url(
            settings, prompt=prompt, ref_code=ref_code, visitor_id=visitor_id
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if format == "json":
        return GoogleAuthorizationUrlResponse(authorization_url=url)
    return RedirectResponse(url=url, status_code=302)


@router.get(
    "/google/callback",
    summary="OAuth redirect URI — exchanges code, issues tokens, redirects to frontend",
    response_model=None,
)
async def google_oauth_callback(
    db: DbDep,
    settings: AuthDep,
    request: Request,
    background_tasks: BackgroundTasks,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    if not google_is_configured(settings):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )
    base = settings.google.frontend_redirect_url
    if error:
        return _fragment_redirect(
            base,
            {"error": error, "error_description": error_description or ""},
        )
    if not code or not state:
        return _fragment_redirect(
            base,
            {"error": "invalid_request", "error_description": "Missing code or state"},
        )
    try:
        state_payload = decode_oauth_state_jwt(state, settings)
    except JWTError:
        return _fragment_redirect(
            base,
            {"error": "invalid_state", "error_description": "Invalid or expired state"},
        )
    state_ref_code = state_payload.get("ref_code")
    state_visitor_id = state_payload.get("visitor_id")
    try:
        token_payload = await exchange_authorization_code(code, settings)
    except Exception:
        logger.exception("Google token exchange failed")
        return _fragment_redirect(
            base,
            {
                "error": "token_exchange_failed",
                "error_description": "Could not exchange authorization code",
            },
        )
    id_token_str = token_payload.get("id_token")
    if not id_token_str:
        return _fragment_redirect(
            base,
            {
                "error": "no_id_token",
                "error_description": "Google did not return id_token",
            },
        )
    try:
        _user, created, tokens = await auth_svc.complete_google_login(
            db, id_token_str, settings
        )
    except auth_svc.AuthError as exc:
        return _fragment_redirect(
            base,
            {"error": "auth_failed", "error_description": str(exc)},
        )
    if created:
        session_factory = request.app.state.container.session_factory
        # Google email is already verified by the IdP, so referral attribution
        # can run immediately — no risk of typo'd addresses inflating counts.
        background_tasks.add_task(
            _post_registration_work,
            session_factory,
            _user.id,
            state_ref_code,
            state_visitor_id,
            attribute_referral_now=True,
        )
        _log_auth_activity(
            request,
            user_id=_user.id,
            event_type="user_registered",
            auth_method="google",
            metadata={"has_referral": bool(state_ref_code or state_visitor_id)},
        )
    _log_auth_activity(
        request,
        user_id=_user.id,
        event_type="user_logged_in",
        auth_method="google",
        metadata={"created_account": created},
    )

    return _fragment_redirect(
        base,
        {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "token_type": tokens.token_type,
            "expires_in": str(tokens.expires_in),
        },
    )


@router.post(
    "/google",
    response_model=TokenPair,
    summary="Sign in with Google (JWT credential from Google Identity Services)",
)
async def google_sign_in_with_credential(
    body: GoogleCredentialRequest,
    db: DbDep,
    settings: AuthDep,
    request: Request,
    background_tasks: BackgroundTasks,
) -> TokenPair:
    if not google_is_configured(settings):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured",
        )
    try:
        user, created, tokens = await auth_svc.complete_google_login(
            db, body.credential, settings
        )
    except auth_svc.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    if created:
        session_factory = request.app.state.container.session_factory
        background_tasks.add_task(
            _post_registration_work,
            session_factory,
            user.id,
            None,
            None,
        )
        _log_auth_activity(
            request,
            user_id=user.id,
            event_type="user_registered",
            auth_method="google",
            metadata={"has_referral": False},
        )
    _log_auth_activity(
        request,
        user_id=user.id,
        event_type="user_logged_in",
        auth_method="google",
        metadata={"created_account": created},
    )
    return tokens
