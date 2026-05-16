import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.deps import get_prompt_manager, get_prompt_service, require_admin_secret
from src.prompts.manager import PromptManager
from src.prompts.schemas import PromptCreate, PromptUpdate
from src.prompts.service import PromptService

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(
    prefix="/admin/prompts",
    tags=["admin"],
    dependencies=[Depends(require_admin_secret)],
    include_in_schema=False,
)


@router.get("/static/style.css", include_in_schema=False)
async def serve_css():
    return FileResponse(_TEMPLATES_DIR / "style.css", media_type="text/css")


# ── List ──────────────────────────────────────────────────────────────────────


@router.get("")
async def list_prompts_page(
    request: Request,
    service: str | None = Query(None),
    svc: PromptService = Depends(get_prompt_service),
):
    all_prompts = await svc.list_all()
    services = sorted(set(p.service for p in all_prompts))
    prompts = (
        [p for p in all_prompts if p.service == service] if service else all_prompts
    )

    count_label = f"{len(prompts)} prompt{'s' if len(prompts) != 1 else ''}"
    if service:
        count_label += f" in {service}"

    return templates.TemplateResponse(
        request,
        "list.html",
        {
            "title": "Prompts",
            "prompts": prompts,
            "services": services,
            "current_service": service,
            "count_label": count_label,
        },
    )


# ── Create ────────────────────────────────────────────────────────────────────


@router.get("/new")
async def new_prompt_page(request: Request):
    return templates.TemplateResponse(request, "new.html", {"title": "New Prompt"})


@router.post("")
async def create_prompt_form(
    service: str = Form(...),
    key: str = Form(...),
    content: str = Form(...),
    description: str = Form(""),
    variables: str = Form(""),
    svc: PromptService = Depends(get_prompt_service),
    pm: PromptManager = Depends(get_prompt_manager),
):
    var_list = (
        [v.strip() for v in variables.split(",") if v.strip()] if variables else []
    )
    await svc.create(
        PromptCreate(
            service=service.strip(),
            key=key.strip(),
            content=content,
            description=description or None,
            variables=var_list,
        )
    )
    await pm.reload()
    return RedirectResponse(
        f"/admin/prompts?service={service.strip()}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ── Edit ──────────────────────────────────────────────────────────────────────


@router.get("/{prompt_id}/edit")
async def edit_prompt_page(
    request: Request,
    prompt_id: uuid.UUID,
    svc: PromptService = Depends(get_prompt_service),
):
    p = await svc.get(prompt_id)
    if not p:
        return templates.TemplateResponse(
            request,
            "list.html",
            {
                "title": "Not Found",
                "prompts": [],
                "services": [],
                "current_service": None,
                "count_label": "Prompt not found",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "title": f"Edit {p.key}",
            "prompt": p,
        },
    )


@router.post("/{prompt_id}")
async def update_prompt_form(
    prompt_id: uuid.UUID,
    content: str = Form(...),
    description: str = Form(""),
    variables: str = Form(""),
    is_active: str | None = Form(None),
    svc: PromptService = Depends(get_prompt_service),
    pm: PromptManager = Depends(get_prompt_manager),
):
    var_list = (
        [v.strip() for v in variables.split(",") if v.strip()] if variables else []
    )
    await svc.update(
        prompt_id,
        PromptUpdate(
            content=content,
            description=description or None,
            variables=var_list,
            is_active=is_active == "true",
        ),
    )
    await pm.reload()
    return RedirectResponse(
        f"/admin/prompts/{prompt_id}/edit", status_code=status.HTTP_303_SEE_OTHER
    )


@router.delete("/{prompt_id}/delete")
async def delete_prompt_form(
    prompt_id: uuid.UUID,
    svc: PromptService = Depends(get_prompt_service),
    pm: PromptManager = Depends(get_prompt_manager),
):
    await svc.delete(prompt_id)
    await pm.reload()
    return RedirectResponse("/admin/prompts", status_code=status.HTTP_303_SEE_OTHER)


# ── Version history ───────────────────────────────────────────────────────────


@router.get("/{prompt_id}/versions")
async def versions_page(
    request: Request,
    prompt_id: uuid.UUID,
    svc: PromptService = Depends(get_prompt_service),
):
    p = await svc.get(prompt_id)
    if not p:
        return templates.TemplateResponse(
            request,
            "list.html",
            {
                "title": "Not Found",
                "prompts": [],
                "services": [],
                "current_service": None,
                "count_label": "Prompt not found",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )
    versions = await svc.list_versions(prompt_id)
    return templates.TemplateResponse(
        request,
        "versions.html",
        {
            "title": f"History {p.key}",
            "prompt": p,
            "versions": versions,
        },
    )
