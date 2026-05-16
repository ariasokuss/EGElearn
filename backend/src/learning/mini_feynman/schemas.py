"""Feynman API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class LessonRead(BaseModel):
    id: str
    user_id: str
    name: str
    content: str
    num_blocks: int
    created_at: datetime


class LessonBlockRead(BaseModel):
    id: str
    lesson_id: str
    user_id: str
    content: str
    block_number: int
    is_summary: bool
    created_at: datetime
