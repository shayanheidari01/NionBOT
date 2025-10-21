# src/database/session.py
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import async_sessionmaker
from .config import engine

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)

@asynccontextmanager
async def async_session():
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except:
        await session.rollback()
        raise
    finally:
        await session.close()