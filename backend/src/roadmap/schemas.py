from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ProgressUpdate(BaseModel):
    progress: int = Field(ge=0, le=100)


class RoadmapLessonOut(BaseModel):
    id: uuid.UUID
    name: str
    lesson_id: uuid.UUID | None
    description: str | None = Field(
        default=None,
        description="Short blurb from lessons.description (folder lesson cards).",
    )
    progress: int
    mastery: float | None = None
    confidence: float | None = None
    study_star: bool = False
    feynman_star: bool = False
    test_star: bool = False

    model_config = {"from_attributes": True}


class RoadmapSubsectionOut(BaseModel):
    id: uuid.UUID
    name: str
    lessons: list[RoadmapLessonOut]

    model_config = {"from_attributes": True}


class RoadmapSectionOut(BaseModel):
    id: uuid.UUID
    name: str
    subsections: list[RoadmapSubsectionOut]
    lessons: list[RoadmapLessonOut]  # direct lessons (when no subsection)

    model_config = {"from_attributes": True}


class RoadmapOut(BaseModel):
    folder_id: uuid.UUID
    sections: list[RoadmapSectionOut]
    total_lessons: int
    completed_lessons: int  # progress == 100
    overall_progress: float  # average progress across all lessons


class OptionalThemeOption(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class OptionalThemesOut(BaseModel):
    title: str
    exam_date: str
    blocks: list[list[OptionalThemeOption]]


class OptionalThemesSelectionIn(BaseModel):
    option_ids: list[uuid.UUID]
