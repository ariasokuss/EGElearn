"""Pydantic schemas for highlights/notes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, computed_field

# Normalize empty string to None so "" and null both mean "no comment"
_NullableStr = Annotated[str | None, BeforeValidator(lambda v: v or None)]


class HighlightCreate(BaseModel):
    text: str
    comment: _NullableStr = None


class HighlightPatch(BaseModel):
    comment: _NullableStr = None


class HighlightRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    lesson_id: uuid.UUID
    text: str
    comment: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def type(self) -> str:
        return "note" if self.comment else "highlight"

    model_config = {"from_attributes": True}
