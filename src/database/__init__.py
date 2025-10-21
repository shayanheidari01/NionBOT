# src/database/__init__.py
from .config import engine
from .session import async_session
from .models import Base

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)