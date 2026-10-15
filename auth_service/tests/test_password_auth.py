import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.routes import password_auth
from app.core import rate_limit
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models import Base, GoogleCredential, User, UserSettings
from app.services.auth_service import login_with_google
from app.services.mailer import MailSendFailed

NUEVO = {"email": "Ana@Example.com", "password": "contrasena-larga", "full_name": "Ana"}
TOKENS = {"access_token": "a", "scope": ""}


@pytest.fixture(autouse=True)
def _aislar(monkeypatch):
    rate_limit.clear_all()
    monkeypatch.setattr(settings, "resend_api_key", "test-key")
    monkeypatch.setattr(
        settings, "google_oauth_redirect_uri", "https://gw.test/auth/google/callback"
    )


@pytest.fixture
def outbox(monkeypatch):
    enviados: list[str] = []

    async def fake(to, full_name, link):
        enviados.append(link)

    monkeypatch.setattr(password_auth, "send_verification_email", fake)
    return enviados


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


def _path(link: str) -> str:
    return "/" + link.split("//", 1)[1].split("/", 1)[1]


async def _registrar(client, outbox, **cambio) -> str:
    r = await client.post("/auth/register", json={**NUEVO, **cambio})
    assert r.status_code == 202, r.text
    return outbox[-1]


async def _crear_cuenta(client, outbox, **cambio) -> None:
    link = await _registrar(client, outbox, **cambio)
    assert (await client.get(_path(link))).status_code == 200


async def test_registro_no_crea_cuenta_hasta_confirmar(client, sessions, outbox):
    link = await _registrar(client, outbox)
    assert link.startswith("https://gw.test/auth/verify-email?token=")
    async with sessions() as db:
        assert await db.scalar(select(User)) is None
    assert (await client.post("/auth/login", json=NUEVO)).status_code == 401

    assert (await client.get(_path(link))).status_code == 200
    async with sessions() as db:
        user = await db.scalar(select(User))
        assert user.email == "ana@example.com"  # normalizado
        assert user.hashed_password != NUEVO["password"]
        assert await db.scalar(select(UserSettings).where(UserSettings.user_id == user.id))

    # mismo usuario sin importar mayusculas del correo
    r = await client.post("/auth/login", json={**NUEVO, "email": "ANA@example.com"})
    assert r.status_code == 200
    assert _sub(r.json()["access_token"]) == str(user.id)


async def test_enlace_usado_dos_veces_no_duplica(client, sessions, outbox):
    path = _path(await _registrar(client, outbox))
    assert (await client.get(path)).status_code == 200
    assert (await client.get(path)).status_code == 200  # "ya estaba activa"
    async with sessions() as db:
        assert len((await db.scalars(select(User))).all()) == 1


async def test_token_invalido_o_de_sesion_no_crea_cuenta(client, sessions):
    r = await client.get("/auth/verify-email", params={"token": "basura"})
    assert r.status_code == 400
    sesion = create_access_token(subject="1")
    r = await client.get("/auth/verify-email", params={"token": sesion})
    assert r.status_code == 400
    async with sessions() as db:
        assert await db.scalar(select(User)) is None


async def test_registro_sin_proveedor_de_correo_da_503(client, monkeypatch):
    monkeypatch.setattr(settings, "resend_api_key", "")
    assert (await client.post("/auth/register", json=NUEVO)).status_code == 503


async def test_fallo_de_correo_da_502(client, monkeypatch):
    async def boom(*a):
        raise MailSendFailed

    monkeypatch.setattr(password_auth, "send_verification_email", boom)
    assert (await client.post("/auth/register", json=NUEVO)).status_code == 502


async def test_correo_repetido(client, outbox):
    await _crear_cuenta(client, outbox)
    r = await client.post("/auth/register", json={**NUEVO, "email": "ana@example.com"})
    assert r.status_code == 409


async def test_credenciales_malas_dan_el_mismo_error(client, outbox):
    await _crear_cuenta(client, outbox)
    mala = await client.post("/auth/login", json={**NUEVO, "password": "otra-contrasena"})
    inexistente = await client.post("/auth/login", json={**NUEVO, "email": "x@example.com"})
    assert mala.status_code == inexistente.status_code == 401
    assert mala.json() == inexistente.json()


async def test_login_se_bloquea_tras_cinco_fallos(client, outbox):
    await _crear_cuenta(client, outbox)
    mala = {**NUEVO, "password": "otra-contrasena"}
    for _ in range(5):
        assert (await client.post("/auth/login", json=mala)).status_code == 401
    r = await client.post("/auth/login", json=mala)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    # bloqueado incluso con la contrasena correcta
    assert (await client.post("/auth/login", json=NUEVO)).status_code == 429
    # otro correo desde la misma IP no esta bloqueado
    otro = await client.post("/auth/login", json={**mala, "email": "otro@example.com"})
    assert otro.status_code == 401


async def test_login_exitoso_reinicia_el_contador(client, outbox):
    await _crear_cuenta(client, outbox)
    mala = {**NUEVO, "password": "otra-contrasena"}
    for _ in range(4):
        await client.post("/auth/login", json=mala)
    assert (await client.post("/auth/login", json=NUEVO)).status_code == 200
    for _ in range(4):
        assert (await client.post("/auth/login", json=mala)).status_code == 401


async def test_limite_por_ip_ante_barrido_de_correos(client):
    for i in range(30):
        r = await client.post(
            "/auth/login", json={"email": f"u{i}@example.com", "password": "cualquiera-123"}
        )
        assert r.status_code == 401
    r = await client.post(
        "/auth/login", json={"email": "nuevo@example.com", "password": "cualquiera-123"}
    )
    assert r.status_code == 429


async def test_xff_falsificado_no_evade_el_limite_por_correo(client, outbox):
    await _crear_cuenta(client, outbox)
    mala = {**NUEVO, "password": "otra-contrasena"}
    for i in range(5):
        h = {"x-forwarded-for": f"9.9.9.{i}, 1.2.3.4"}  # el ultimo es el del borde
        assert (await client.post("/auth/login", json=mala, headers=h)).status_code == 401
    h = {"x-forwarded-for": "8.8.8.8, 1.2.3.4"}
    assert (await client.post("/auth/login", json=mala, headers=h)).status_code == 429


async def test_limite_de_registros_por_ip(client, outbox):
    for i in range(5):
        r = await client.post("/auth/register", json={**NUEVO, "email": f"r{i}@example.com"})
        assert r.status_code == 202
    r = await client.post("/auth/register", json={**NUEVO, "email": "r9@example.com"})
    assert r.status_code == 429


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


async def test_google_invalida_password_de_registro_previo(client, sessions, outbox):
    """Cuenta con contrasena (p. ej. anterior a la verificacion de correo): al
    entrar el dueno por primera vez con Google se invalida esa contrasena."""
    await _crear_cuenta(client, outbox, email="victima@example.com")
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
