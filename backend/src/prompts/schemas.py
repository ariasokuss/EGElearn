import uuid
from datetime import datetime

from pydantic import BaseModel


class PromptCreate(BaseModel):
    service: str
    key: str
    content: str
    description: str | None = None
    variables: list[str] = []


class PromptUpdate(BaseModel):
    content: str | None = None
    description: str | None = None
    variables: list[str] | None = None
    is_active: bool | None = None


class PromptRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    service: str
    key: str
    content: str
    description: str | None
    variables: list[str]
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime


class PromptVersionRead(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    prompt_id: uuid.UUID
    content: str
    version: int
    changed_by: str | None
    created_at: datetime
