# src/database/models.py
from datetime import datetime
from tokenize import group
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, func, UniqueConstraint, String

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    chat_id: Mapped[str] = mapped_column(String(255), primary_key=True, autoincrement=False)  # chat_id روبیکا
    user_id: Mapped[str] = mapped_column(String(255), autoincrement=False)  # user_id روبیکا
    username: Mapped[str | None] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())

    installations: Mapped[list["InstallEvent"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    groups_owned: Mapped[list["Group"]] = relationship(back_populates="owner")

class Group(Base):
    __tablename__ = "groups"

    chat_id: Mapped[str] = mapped_column(String(255), primary_key=True, autoincrement=False)  # group_id روبیکا
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    owner_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("users.chat_id"))

    link_lock: Mapped[bool] = mapped_column(default=True)
    username_lock: Mapped[bool] = mapped_column(default=True)
    forward_lock: Mapped[bool] = mapped_column(default=True)

    owner: Mapped[User | None] = relationship(back_populates="groups_owned")
    installs: Mapped[list["InstallEvent"]] = relationship(back_populates="group")
    roles: Mapped[list["GroupRole"]] = relationship(back_populates="group", cascade="all, delete-orphan")

class InstallEvent(Base):
    __tablename__ = "install_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(255), ForeignKey("groups.chat_id"))
    owner_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.chat_id"))
    installed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    group: Mapped[Group] = relationship(back_populates="installs")
    owner: Mapped[User] = relationship(back_populates="installations")

class GroupRole(Base):
    __tablename__ = "group_roles"
    __table_args__ = (UniqueConstraint("group_id", "user_id", "role"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(String(255), ForeignKey("groups.chat_id"))
    user_id: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    group: Mapped[Group] = relationship(back_populates="roles")