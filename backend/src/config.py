import os
from functools import lru_cache
from typing import Self

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseModel):
    name: str = "novalearn"
    env: str = "local"
    debug: bool = True
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"


class ServerSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class DatabaseSettings(BaseModel):
    dsn: str = "postgresql+asyncpg://nova:pakistan@postgres:5432/novalearn"
    echo: bool = False
    pool_size: int = 30
    max_overflow: int = 50
    ssl_insecure: bool = False


class QdrantSettings(BaseModel):
    url: str = "http://localhost:6333"
    api_key: str | None = None
    prefer_grpc: bool = False
    timeout: int = 15
    vector_size: int = 1024


class GoogleOAuthSettings(BaseModel):
    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = ""
    frontend_redirect_url: str = "http://localhost:3000/auth/callback"


class AuthSettings(BaseModel):
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    refresh_token_expire_days: int = 7
    dev_bypass_enabled: bool = False
    dev_bypass_email: str = "dev@novalearn.local"
    admin_secret: str = ""
    admin_username: str = "admin"
    admin_max_failed_attempts: int = 5
    google: GoogleOAuthSettings = Field(default_factory=GoogleOAuthSettings)


class MailSettings(BaseModel):
    api_key: str = ""
    api_url: str = "https://api.resend.com"
    from_email: str = "roman@novalearn.ai"
    from_name: str = "NovaLearn"
    # Reply-To address. Defaults to from_email when unset.
    reply_to: str = ""
    # Sender identity for security emails (verification codes, password resets,
    # account-change notices). Falls back to from_email/from_name when unset.
    security_from_email: str = "security@novalearn.ai"
    security_from_name: str = "NovaLearn Security"
    timeout: float = 30.0  # HTTP request timeout in seconds
    # Account-level lockout / send throttle
    max_code_attempts: int = 5  # wrong verification codes before lockout
    max_token_attempts: int = 5  # wrong reset token submissions before lockout
    max_sends_per_hour: int = 3  # max emails per address per hour
    lockout_minutes: int = 15  # lockout duration after max attempts


class GenAISettings(BaseModel):
    api_key: str = ""
    embedding_model: str = "gemini-embedding-exp-03-07"


class VoyageSettings(BaseModel):
    api_key: str = ""
    embedding_model: str = "voyage-4-large"
    output_dimension: int = 1024
    max_batch_tokens: int = 100_000


class MistralSettings(BaseModel):
    api_key: str = ""
    ocr_model: str = "mistral-ocr-latest"


def _default_model_id_map() -> dict[str, str]:
    return {"YandexGPT": "yandexgpt/latest"}


def _default_model_pricing() -> dict[str, dict[str, float]]:
    """Yandex returns token usage, not USD cost; billing is tracked outside API responses."""
    return {"yandexgpt/latest": {"prompt": 0.0, "completion": 0.0}}


def _default_reasoning_params_map() -> dict[str, dict[str, str]]:
    return {"default": {}}


class LLMSettings(BaseModel):
    api_key: str = ""
    folder_id: str = ""
    base_url: str = "https://llm.api.cloud.yandex.net/v1"
    model: str = "yandexgpt/latest"
    timeout_seconds: float = 120.0
    max_retries: int = 3
    retry_base_delay: float = 1.0
    max_connections: int = 10
    conversation_title_max_length: int = 60
    model_id_map: dict[str, str] = Field(default_factory=_default_model_id_map)
    reasoning_params_map: dict[str, dict[str, str]] = Field(
        default_factory=_default_reasoning_params_map
    )
    model_pricing: dict[str, dict[str, float]] = Field(
        default_factory=_default_model_pricing
    )

    def resolve_model_uri(self, model_name: str | None = None) -> str:
        raw = (model_name or self.model).strip()
        if raw.startswith("gpt://"):
            return raw
        if not self.folder_id.strip():
            return raw
        return f"gpt://{self.folder_id.strip()}/{raw}"


class S3Settings(BaseModel):
    endpoint_url: str = "http://minio:9000"
    access_key_id: str = "minioadmin"
    secret_access_key: str = "minioadmin"
    region: str = "us-east-1"
    bucket: str = "novalearn-assets"
    use_ssl: bool = False
    use_path_style: bool = True
    # Optional override used ONLY when generating presigned URLs (so the
    # browser can reach the S3/MinIO host even when the backend reaches it
    # over a Docker-internal hostname). Leave empty to use `endpoint_url`.
    # Example: endpoint_url="http://minio:9000",
    #          public_endpoint_url="http://localhost:9000"
    public_endpoint_url: str = ""


class RabbitMQSettings(BaseModel):
    """RabbitMQ / AMQP for file processing jobs and test grading queue.

    Env (nested, delimiter ``__``):
    - ``RABBITMQ__URL`` — broker URL (same as used by ``aio_pika``).
    - ``RABBITMQ__ENABLED`` — if false, API skips connect at startup (optional).
    - ``RABBITMQ__QUEUE_NAME`` — processing queue name.

    If ``RABBITMQ__URL`` is unset, ``Settings`` also checks (in order) ``RABBITMQ_URL``,
    ``AMQP_URL``, ``CLOUDAMQP_URL`` (common on Railway/Heroku templates).
    """

    enabled: bool = True
    url: str = "amqp://guest:guest@rabbitmq:5672/"
    queue_name: str = "processing_jobs"


class ChunkingSettings(BaseModel):
    window_max_tokens: int = 40_000
    tiktoken_encoding: str = "cl100k_base"
    clustering_model: str = "YandexGPT"
    clustering_max_retries: int = 3
    semantic_percentile_threshold: int = 3
    min_segments_for_similarity: int = 4
    centroid_sim_threshold: float = 0.78
    chunk_chunk_sim_threshold: float = 0.76
    centroid_borderline_low: float = 0.68
    centroid_borderline_high: float = 0.84
    candidate_centroid_floor: float = 0.58
    top_neighbors_per_cluster: int = 2
    megaclustering_enabled: bool = True


class ProcessingSettings(BaseModel):
    stream_interval_seconds: float = 1.0
    max_parallel: int = 4
    max_attempts: int = 3
    txt_wrap_max_length: int = 100
    chunking: ChunkingSettings = ChunkingSettings()


class RagSettings(BaseModel):
    top_k: int = 25
    similarity_threshold: float = 0.7


class MasterySettings(BaseModel):
    lambda_decay: float = 0.97  # daily decay factor, half-life ≈ 23 days
    mastery_percentile: float = 0.10  # 10th percentile of Beta posterior
    alpha_prior: float = 1.0
    beta_prior: float = 1.0
    confidence_threshold: float = 20.0  # effective events for 100% confidence
    calibrating_threshold: float = (
        30.0  # confidence % below which UI shows "Calibrating"
    )


class ChatSettings(BaseModel):
    max_agent_iterations: int = 8
    total_context_budget: int = 120_000
    history_token_budget: int = 30_000
    retrieval_token_budget: int = 85_000
    page_buffer: int = 2
    max_concurrent_tool_calls: int = 3
    max_history_messages: int = 50
    conversation_title_max_length: int = 60
    message_max_length: int = 150_000
    chars_per_token: int = 4
    followup_max_questions: int = 3
    last_message_preview_length: int = 100
    max_attachments_per_message: int = 5
    max_image_size_bytes: int = 20_971_520  # 20MB
    max_pdf_size_bytes: int = 52_428_800  # 50MB
    max_text_size_bytes: int = 5_242_880  # 5MB
    max_attachment_text_chars: int = 50_000  # per file, for LLM context


class LearningSettings(BaseModel):
    last_accessed_lessons_limit: int = 3


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: AppSettings = AppSettings()
    server: ServerSettings = ServerSettings()
    auth: AuthSettings = AuthSettings()
    mail: MailSettings = MailSettings()

    s3: S3Settings = S3Settings()
    rabbitmq: RabbitMQSettings = RabbitMQSettings()
    postgres: DatabaseSettings = DatabaseSettings()
    qdrant: QdrantSettings = QdrantSettings()
    processing: ProcessingSettings = ProcessingSettings()

    genai: GenAISettings = GenAISettings()
    voyage: VoyageSettings = VoyageSettings()
    mistral: MistralSettings = MistralSettings()
    llm: LLMSettings = LLMSettings()
    rag: RagSettings = RagSettings()
    mastery: MasterySettings = MasterySettings()
    chat: ChatSettings = ChatSettings()
    learning: LearningSettings = LearningSettings()

    @model_validator(mode="after")
    def apply_platform_env_overrides(self) -> Self:
        """Railway/Heroku: PORT; DATABASE_URL; AMQP URL aliases."""
        port_s = os.environ.get("PORT")
        if port_s:
            try:
                self.server.port = int(port_s)
            except ValueError:
                pass

        if not os.environ.get("POSTGRES__DSN"):
            db_url = os.environ.get("DATABASE_URL")
            if db_url:
                dsn = db_url
                if dsn.startswith("postgres://"):
                    dsn = "postgresql://" + dsn[len("postgres://") :]
                if dsn.startswith("postgresql://") and "+asyncpg" not in dsn:
                    dsn = dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
                self.postgres.dsn = dsn

        # Nested RABBITMQ__URL is applied by pydantic-settings before this hook.
        if not (os.environ.get("RABBITMQ__URL") or "").strip():
            for key in ("RABBITMQ_URL", "AMQP_URL", "CLOUDAMQP_URL"):
                v = os.environ.get(key)
                if v and str(v).strip():
                    self.rabbitmq = self.rabbitmq.model_copy(
                        update={"url": str(v).strip()}
                    )
                    break

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
