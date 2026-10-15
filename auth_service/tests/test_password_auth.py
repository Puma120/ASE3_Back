import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.session import get_db
from app.main import app
from app.models import Base, GoogleCredential, User, UserSettings
from app.services.auth_service import login_with_google

NUEVO = {"email": "Ana@Example.com", "password": "contrasena-larga", "full_name": "Ana"}
TOKENS = {"access_token": "a", "scope": ""}


@pytest.fixture
async def sessions():
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _get_db():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    yield maker
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
async def client(sessions):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        yield c


def _sub(token: str) -> str:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])["sub"]


async def test_registro_y_login(client, sessions):
    r = await client.post("/auth/register", json=NUEVO)
    assert r.status_code == 201
    async with sessions() as db:
        user = await db.scalar(select(User))
        assert user.email == "ana@example.com"  # normalizado
        assert user.hashed_password != NUEVO["password"]
        assert await db.scalar(select(UserSettings).where(UserSettings.user_id == user.id))
    assert _sub(r.json()["access_token"]) == str(user.id)

    # mismo usuario sin importar mayusculas del correo
    r = await client.post("/auth/login", json={**NUEVO, "email": "ANA@example.com"})
    assert r.status_code == 200
    assert _sub(r.json()["access_token"]) == str(user.id)


async def test_correo_repetido(client):
    await client.post("/auth/register", json=NUEVO)
    r = await client.post("/auth/register", json={**NUEVO, "email": "ana@example.com"})
    assert r.status_code == 409


async def test_credenciales_malas_dan_el_mismo_error(client):
    await client.post("/auth/register", json=NUEVO)
    mala = await client.post("/auth/login", json={**NUEVO, "password": "otra-contrasena"})
    inexistente = await client.post("/auth/login", json={**NUEVO, "email": "x@example.com"})
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()


@pytest.mark.parametrize(
    "cambio",
    [{"password": "corta"}, {"password": "ñ" * 40}, {"email": "no-es-correo"}, {"full_name": ""}],
)
async def test_validacion(client, cambio):
    r = await client.post("/auth/register", json={**NUEVO, **cambio})
    assert r.status_code == 422


async def test_cuenta_solo_google_no_entra_con_password(client, sessions):
    async with sessions() as db:
        await login_with_google(db, "g@example.com", "G", TOKENS)
    r = await client.post(
        "/auth/login", json={"email": "g@example.com", "password": "cualquiera-123"}
    )
    assert r.status_code == 401


async def test_google_invalida_password_de_registro_previo(client, sessions):
    """Quien se registra con un correo ajeno pierde acceso cuando el dueno
    entra por primera vez con Google."""
    await client.post("/auth/register", json={**NUEVO, "email": "victima@example.com"})
    async with sessions() as db:
        await login_with_google(db, "victima@example.com", "V", TOKENS)
        assert await db.scalar(select(GoogleCredential))
    r = await client.post(
        "/auth/login", json={"email": "victima@example.com", "password": NUEVO["password"]}
    )
    assert r.status_code == 401


async def test_google_repetido_no_toca_password_ya_ligada(sessions):
    async with sessions() as db:
        await login_with_google(db, "u@example.com", "U", TOKENS)
        user = await db.scalar(select(User))
        user.hashed_password = "marca"
        await db.commit()
        await login_with_google(db, "u@example.com", "U", {**TOKENS, "access_token": "b"})
        assert (await db.scalar(select(User))).hashed_password == "marca"
