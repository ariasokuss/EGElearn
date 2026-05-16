import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_db
from src.exam import service as exam_svc
from src.exam.schemas import ExamCreate, ExamOut, ExamUpdate

router = APIRouter(prefix="/exams", tags=["exams"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


async def _build_exam_out(
    db: AsyncSession,
    exam,
    user_id: uuid.UUID,
    expanded_node_ids: list[uuid.UUID],
) -> ExamOut:
    """Build ExamOut using pre-expanded level-3 node IDs."""
    from src.roadmap.models import RoadmapProgress

    nodes = await exam_svc.fetch_nodes_for_exam(db, expanded_node_ids)

    # Compute progress from expanded (level-3) nodes
    progress = 0
    if expanded_node_ids:
        from sqlalchemy import select

        rows = await db.execute(
            select(RoadmapProgress.node_id, RoadmapProgress.progress).where(
                RoadmapProgress.node_id.in_(expanded_node_ids),
                RoadmapProgress.user_id == user_id,
            )
        )
        node_progress = {r.node_id: r.progress for r in rows}
        total = sum(node_progress.get(n, 0) for n in expanded_node_ids)
        progress = int(round(total / len(expanded_node_ids)))

    return ExamOut(
        id=exam.id,
        user_id=exam.user_id,
        folder_id=exam.folder_id,
        name=exam.name,
        exam_date=exam.exam_date,
        roadmap_nodes=nodes,
        created_at=exam.created_at,
        progress=progress,
    )


@router.get(
    "/folders/{folder_id}",
    response_model=list[ExamOut],
    summary="Get all exams in a folder for the current user",
)
async def get_exams(
    folder_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> list[ExamOut]:
    exams = await exam_svc.get_exams_for_folder(db, folder_id, current_user.id)
    results = []
    for e in exams:
        expanded = await exam_svc._expand_nodes(db, e.roadmap_nodes or [])
        results.append(await _build_exam_out(db, e, current_user.id, expanded))
    return results


@router.post(
    "",
    response_model=ExamOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new exam",
)
async def create_exam(
    body: ExamCreate,
    db: DbDep,
    current_user: CurrentUser,
) -> ExamOut:
    try:
        exam = await exam_svc.create_exam(db, current_user.id, body)
        expanded = await exam_svc._expand_nodes(db, exam.roadmap_nodes or [])
        return await _build_exam_out(db, exam, current_user.id, expanded)
    except exam_svc.ExamError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.patch(
    "/{exam_id}",
    response_model=ExamOut,
    summary="Update an exam (partial)",
)
async def update_exam(
    exam_id: uuid.UUID,
    body: ExamUpdate,
    db: DbDep,
    current_user: CurrentUser,
) -> ExamOut:
    try:
        exam = await exam_svc.update_exam(db, exam_id, current_user.id, body)
        expanded = await exam_svc._expand_nodes(db, exam.roadmap_nodes or [])
        return await _build_exam_out(db, exam, current_user.id, expanded)
    except exam_svc.ExamError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete(
    "/{exam_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an exam",
)
async def delete_exam(
    exam_id: uuid.UUID,
    db: DbDep,
    current_user: CurrentUser,
) -> None:
    try:
        await exam_svc.delete_exam(db, exam_id, current_user.id)
    except exam_svc.ExamError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
