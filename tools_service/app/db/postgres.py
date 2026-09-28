"""Sesion async de SQLAlchemy contra PostgreSQL (lectura de datos relacionales
compartidos con auth_service - GoogleCredential, ver app/models/google_credential.py)."""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
