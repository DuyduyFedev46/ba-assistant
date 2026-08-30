"""Projects — CRUD project + profile dự án (config khai báo, không phải code)."""

from __future__ import annotations

from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import repos
from ..engine.profile_loader import Profile, load_profile_yaml
from .deps import get_current_user, get_session

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    slug: str
    name: str
    profile_yaml: str
    repo_url: str | None = None


class ProfileUpdate(BaseModel):
    profile_yaml: str


def _parse_profile_or_422(text: str) -> Profile:
    """Parse profile YAML — lỗi cú pháp/schema → 422."""
    try:
        return load_profile_yaml(text)
    except (yaml.YAMLError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="profile_yaml không hợp lệ") from exc


def _profile_out(project, profile: Profile) -> dict:
    return {
        "slug": project.slug,
        "name": project.name,
        "profile_yaml": project.profile_yaml,
        "profile": profile.model_dump(mode="json"),
    }


@router.post("", status_code=201)
async def create_project(
    body: ProjectCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Tạo project mới — profile validate trước khi lưu; slug trùng → 409."""
    if await repos.get_project_by_slug(session, body.slug) is not None:
        raise HTTPException(status_code=409, detail="slug đã tồn tại")
    profile = _parse_profile_or_422(body.profile_yaml)
    project = await repos.create_project(
        session,
        slug=body.slug,
        name=body.name,
        profile_yaml=body.profile_yaml,
        repo_url=body.repo_url,
    )
    return _profile_out(project, profile)


@router.get("")
async def list_projects(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[str, Depends(get_current_user)],
) -> list[dict]:
    projects = await repos.list_projects(session)
    return [
        {
            "slug": p.slug,
            "name": p.name,
            "repo_url": p.repo_url,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in projects
    ]


@router.get("/{slug}/profile")
async def get_profile(
    slug: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Profile hiện tại của project — 404 nếu slug không tồn tại."""
    project = await repos.get_project_by_slug(session, slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project '{slug}' chưa tồn tại")
    return _profile_out(project, load_profile_yaml(project.profile_yaml))


@router.put("/{slug}/profile")
async def update_profile(
    slug: str,
    body: ProfileUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Thay profile (revalidate 422) — 404 nếu slug không tồn tại."""
    project = await repos.get_project_by_slug(session, slug)
    if project is None:
        raise HTTPException(status_code=404, detail=f"project '{slug}' chưa tồn tại")
    profile = _parse_profile_or_422(body.profile_yaml)
    project.profile_yaml = body.profile_yaml
    await session.commit()
    await session.refresh(project)
    return _profile_out(project, profile)
