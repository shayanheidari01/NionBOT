# src/database/crud.py
from typing import Literal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from . import models

async def upsert_user(session: AsyncSession, chat_id: str, user_id: str, username: str | None) -> models.User:
    result = await session.execute(select(models.User).where(models.User.chat_id == chat_id))
    user = result.scalar_one_or_none()
    if user:
        user.username = username or user.username
        return user
    user = models.User(chat_id=chat_id, user_id=user_id, username=username)
    session.add(user)
    return user

async def upsert_group(session: AsyncSession, group_id: int, title: str | None, owner: models.User) -> models.Group:
    result = await session.execute(select(models.Group).where(models.Group.chat_id == group_id))
    group = result.scalar_one_or_none()
    if group:
        group.title = title or group.title
        group.owner = owner
        return group, "Exist"
    group = models.Group(chat_id=group_id, title=title, owner=owner)
    session.add(group)
    return group, "New"

async def log_install(session: AsyncSession, group: models.Group, owner: models.User) -> models.InstallEvent:
    event = models.InstallEvent(group=group, owner=owner)
    session.add(event)
    return event

async def update_group_locks(
    session: AsyncSession,
    group_id: str,
    *,
    link_lock: bool | None = None,
    username_lock: bool | None = None,
    forward_lock: bool | None = None,
) -> models.Group | None:
    result = await session.execute(select(models.Group).where(models.Group.chat_id == group_id))
    group = result.scalar_one_or_none()
    if group is None:
        return None
    if link_lock is not None:
        group.link_lock = link_lock
    if username_lock is not None:
        group.username_lock = username_lock
    if forward_lock is not None:
        group.forward_lock = forward_lock
    return group

async def ensure_group_role(
    session: AsyncSession,
    group_id: str,
    user_id: str,
    role: Literal["owner", "admin"],
) -> models.GroupRole:
    result = await session.execute(
        select(models.GroupRole).where(
            models.GroupRole.group_id == group_id,
            models.GroupRole.user_id == user_id,
            models.GroupRole.role == role,
        )
    )
    group_role = result.scalar_one_or_none()
    if group_role:
        return group_role
    group_role = models.GroupRole(group_id=group_id, user_id=user_id, role=role)
    session.add(group_role)
    return group_role

async def user_has_role(
    session: AsyncSession,
    group_id: str,
    user_id: str,
    role: Literal["owner", "admin"],
) -> bool:
    result = await session.execute(
        select(models.GroupRole.id).where(
            models.GroupRole.group_id == group_id,
            models.GroupRole.user_id == user_id,
            models.GroupRole.role == role,
        )
    )
    return result.scalar_one_or_none() is not None

async def remove_group_role(
    session: AsyncSession,
    group_id: str,
    user_id: str,
    role: Literal["owner", "admin"],
) -> bool:
    result = await session.execute(
        select(models.GroupRole).where(
            models.GroupRole.group_id == group_id,
            models.GroupRole.user_id == user_id,
            models.GroupRole.role == role,
        )
    )
    group_role = result.scalar_one_or_none()
    if group_role is None:
        return False
    await session.delete(group_role)
    return True