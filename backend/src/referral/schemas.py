import uuid
from datetime import datetime

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class CreateSourceRequest(BaseModel):
    code: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str | None = Field(None, max_length=255)


class UpdateSourceRequest(BaseModel):
    label: str | None = None
    is_active: bool | None = None


class TrackVisitRequest(BaseModel):
    code: str
    visitor_id: str = Field(max_length=36)
    landing_page: str | None = Field(None, max_length=2048)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class SourceOut(BaseModel):
    id: uuid.UUID
    code: str
    label: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SourceStats(BaseModel):
    source_id: uuid.UUID
    code: str
    label: str | None
    visits_count: int
    unique_visitors: int
    registrations: int
    purchases: int


class DashboardOut(BaseModel):
    sources: list[SourceStats]
    totals: SourceStats | None = None
