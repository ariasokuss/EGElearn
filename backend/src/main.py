import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from voyageai.client_async import AsyncClient as AsyncVoyageClient

from src.auth.profile_router import router as profile_router
from src.auth.router import router as auth_router
from src.chat.agent import DocumentChatAgent
from src.chat.citation_extractor import CitationExtractor
from src.chat.context_manager import ContextManager
from src.chat.router import router as chat_router
from src.chat.service import ChatRepository
from src.config import get_settings
from src.core.logging import configure_logging
from src.core.yandex_gpt import YandexGPTLLMGateway
from src.core.voyage import VoyageEmbeddingService
from src.events.router import router as events_router
from src.files.router import router as files_router
from src.mail.router import router as mail_router
from src.learning.router import router as learning_router
from src.learning.feedback.router import router as feedback_router
from src.learning.mini_feynman.router import router as mini_feynman_router
from src.learning.feynman.router import router as feynman_router
from src.prompts.admin import router as prompts_admin_router
from src.prompts.router import router as prompts_router
from src.inspector.router import router as inspector_router
from src.prompts.seeds import seed_chat_prompts
from src.exam.router import router as exam_router
from src.learning.highlights.router import router as highlights_router
from src.learning.past_paper.router import router as past_paper_router
from src.learning.past_paper.admin import router as past_paper_admin_router
from src.learning.tests.router import router as tests_router
from src.referral.router import router as referral_router
from src.referral.admin import router as referral_admin_router
from src.roadmap.router import router as roadmap_router
from src.roadmap.ege_seed import seed_ege_subject_folders
from src.usage.router import router as usage_router
from src.usage.admin import router as usage_admin_router
from src.api.security_admin import router as security_admin_router
from src.activity.router import router as activity_router
from src.activity.service import ActivityService
from src.processing.markdown import MistralOCR
from src.rag.service import RagService
from src.runtime import build_container, close_container
from src.usage.service import UsageService

_settings = get_settings()
configure_logging(_settings)

logger = logging.getLogger(__name__)


async def _seed_prompts_with_db_retry(container) -> None:
    """Postgres on PaaS may accept TCP a few seconds after the web process starts."""
    attempts = int(os.environ.get("STARTUP_DB_RETRY_ATTEMPTS", "15"))
    delay_s = float(os.environ.get("STARTUP_DB_RETRY_DELAY", "2"))
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            await seed_chat_prompts(container.session_factory)
            await seed_ege_subject_folders(container.session_factory)
            await container.prompt_manager.start()
            if i > 0:
                logger.info("DB ready after %s attempt(s)", i + 1)
            return
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Startup DB phase failed (%s/%s): %s; retry in %ss",
                i + 1,
                attempts,
                exc,
                delay_s,
            )
            await asyncio.sleep(delay_s)
    assert last_exc is not None
    logger.exception("Startup DB phase failed after %s attempts", attempts)
    raise last_exc


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    container = await build_container(settings)
    app.state.container = container
    logger.info("Runtime container initialised")
    # logger.info("S3 client opened, bucket %r ensured", settings.s3.bucket)

    await _seed_prompts_with_db_retry(container)
    app.state.prompt_manager = container.prompt_manager
    from src.learning.past_paper.admin_library import ensure_admin_library_folder
    await ensure_admin_library_folder(container.session_factory)

    voyage_client = AsyncVoyageClient(api_key=settings.voyage.api_key)
    chat_repo = ChatRepository(container.session_factory)
    rag_service = RagService(container.qdrant)
    embedding_service = VoyageEmbeddingService(voyage_client)
    llm_gateway = YandexGPTLLMGateway()
    usage_service = UsageService(container.session_factory)
    activity_service = ActivityService(container.session_factory)
    context_manager = ContextManager(prompt_manager=container.prompt_manager)
    citation_extractor = CitationExtractor()
    mistral_ocr = MistralOCR(settings.mistral)
    chat_agent = DocumentChatAgent(
        chat_repo=chat_repo,
        retrieval=rag_service,
        embedding=embedding_service,
        llm=llm_gateway,
        context_manager=context_manager,
        citation_extractor=citation_extractor,
        s3=container.s3,
        usage_service=usage_service,
        mistral_ocr=mistral_ocr,
    )
    from src.api.admin_blacklist import AdminBruteForceGuard
    app.state.admin_brute_force = AdminBruteForceGuard()
    app.state.usage_service = usage_service
    app.state.activity_service = activity_service
    app.state.chat_agent = chat_agent
    app.state.chat_repo = chat_repo

    # Start test grading consumer
    from src.learning.tests.grading_worker import start_grading_consumer

    await start_grading_consumer(container)

    yield

    await close_container(container)
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app.name,
        version="0.1.0",
        docs_url=None,
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Trust X-Forwarded-Proto / X-Forwarded-For from the reverse proxy
    # so that request.base_url returns https:// instead of http://
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    src_dir = Path(__file__).resolve().parent
    app.mount("/static", StaticFiles(directory=src_dir / "static"), name="static")
    templates = Jinja2Templates(directory=src_dir / "templates")

    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui(request: Request):
        return templates.TemplateResponse(
            "swagger.html",
            {
                "request": request,
                "title": f"{settings.app.name} - API Docs",
                "root": str(request.base_url).rstrip("/"),
            },
        )

    app.add_middleware(GZipMiddleware, minimum_size=1000)

    cors_origins = settings.server.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins != ["*"] else [],
        allow_origin_regex=".*" if cors_origins == ["*"] else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def custom_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        if "/chat/" in request.url.path:
            for err in exc.errors():
                if tuple(err.get("loc") or ()) == ("body", "message") and err.get(
                    "type"
                ) == "string_too_long":
                    max_length = (err.get("ctx") or {}).get("max_length")
                    detail = (
                        f"Message should have at most {max_length} characters."
                        if max_length
                        else "Message is too long."
                    )
                    return JSONResponse(status_code=413, content={"detail": detail})
        return await request_validation_exception_handler(request, exc)

    @app.get(f"{settings.app.api_prefix}/health", tags=["health"])
    async def health():
        return {"status": "ok"}

    prefix = settings.app.api_prefix
    app.include_router(auth_router, prefix=prefix)
    app.include_router(profile_router, prefix=prefix)
    app.include_router(mail_router, prefix=prefix)
    app.include_router(events_router, prefix=prefix)
    app.include_router(files_router, prefix=prefix)
    app.include_router(chat_router, prefix=prefix)
    app.include_router(learning_router, prefix=prefix)
    app.include_router(mini_feynman_router, prefix=prefix)
    app.include_router(feedback_router, prefix=prefix)
    app.include_router(feynman_router, prefix=prefix)
    app.include_router(prompts_router, prefix=prefix)
    app.include_router(exam_router, prefix=prefix)
    app.include_router(highlights_router, prefix=prefix)
    app.include_router(past_paper_router, prefix=prefix)
    app.include_router(tests_router, prefix=prefix)
    app.include_router(referral_router, prefix=prefix)
    app.include_router(roadmap_router, prefix=prefix)
    app.include_router(
        prompts_admin_router
    )  # no api_prefix — admin panel is not versioned
    app.include_router(inspector_router, prefix=prefix)
    app.include_router(usage_router, prefix=prefix)
    app.include_router(activity_router, prefix=prefix)
    app.include_router(usage_admin_router)
    app.include_router(security_admin_router)
    app.include_router(past_paper_admin_router)
    app.include_router(referral_admin_router)

    return app


app = create_app()
