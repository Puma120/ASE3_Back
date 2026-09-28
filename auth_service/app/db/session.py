"""Sesion async de SQLAlchemy contra PostgreSQL. Base declarativa en
app/db/base.py; modelos en app/models/; migraciones en alembic/."""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
