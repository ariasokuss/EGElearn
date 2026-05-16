from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select

from src.api.admin_blacklist import AdminBruteForceGuard, AdminIPBlacklist
from src.api.deps import get_container, require_admin_secret
from src.runtime import AppContainer

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(
    prefix="/admin/security",
    tags=["admin"],
    dependencies=[Depends(require_admin_secret)],
    include_in_schema=False,
)


@router.get("")
async def blacklist_page(
    request: Request,
    container: AppContainer = Depends(get_container),
):
    async with container.session_factory() as session:
        result = await session.execute(
            select(AdminIPBlacklist).order_by(AdminIPBlacklist.blocked_at.desc())
        )
        entries = result.scalars().all()
    return templates.TemplateResponse(
        request, "blacklist.html", {"title": "Security", "entries": entries}
    )


@router.post("/{entry_id}/unban")
async def unban_ip(
    entry_id: str,
    request: Request,
    container: AppContainer = Depends(get_container),
):
    async with container.session_factory() as session:
        result = await session.execute(
            select(AdminIPBlacklist).where(AdminIPBlacklist.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry:
            guard: AdminBruteForceGuard = request.app.state.admin_brute_force
            guard.record_success(entry.ip)
            await session.execute(
                delete(AdminIPBlacklist).where(AdminIPBlacklist.id == entry_id)
            )
            await session.commit()
    return RedirectResponse("/admin/security", status_code=status.HTTP_303_SEE_OTHER)
