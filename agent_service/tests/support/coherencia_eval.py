"""Prueba de coherencia del agente (Objetivo 4): tools simuladas, ejecucion de un
caso con el grafo real, tope de peticiones y calificacion por reglas. Lo usa
tests/kpi/eval_obj4.py; quien importa este modulo ya configuro el entorno.

Una peticion es un mensaje de usuario (un agent_graph.ainvoke); las rondas de
tools no cuentan. Las reglas detectan lo verificable y no cubren afirmaciones en
texto libre: por eso el reporte exige la revision humana de las respuestas.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from mongomock_motor import AsyncMongoMockClient

from app.core.config import settings
from app.graph import nodes, user_context
from app.graph.builder import agent_graph
from app.graph.tool_specs import TOOL_SPECS
from app.memory import heuristics, profile, short_term, summary, vector_store, workflow
from app.memory import params as params_store
from tests.support.coherencia_perfiles import POR_CLAVE, PERFILES, Perfil
from tests.support.rag_eval import contiene, normalizar, respuesta_correcta, se_abstiene, texto_indexado

CASOS = Path(__file__).resolve().parent.parent / "data" / "casos_coherencia.json"
LIMITE_PETICIONES = 100
MAX_ERRORES_SEGUIDOS = 3
CUOTAS = {
    "horario": 15,
    "agendar": 12,
    "atorada": 8,
    "carga": 8,
    "autoconocimiento": 8,
    "sin_evidencia": 13,
    "premisa_falsa": 8,
    "dato_chat": 8,
    "chat_vs_patron": 10,
    "instruccion": 5,
    "no_relacionado": 5,
}
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_RANGOS_LIBRES = ((8 * 60, 12 * 60), (14 * 60, 18 * 60), (19 * 60 + 30, 23 * 60))  # las tres franjas
_TOOLS_QUE_AGENDAN = {"create_task", "create_subtasks", "create_event", "reschedule_task"}
_DIVIDIR = ["divid", "pasos", "partes", "bloque", "subtarea", "mas cort", "pedazo", "etapa"]
_FRASES_FRANJA = {
    "manana": ["por la manana", "en la manana", "de manana", "las mananas", "temprano", "matutin"],
    "tarde": ["por la tarde", "en la tarde", "de tarde", "las tardes", "vespertin"],
    "noche": ["por la noche", "en la noche", "de noche", "las noches", "nocturn"],
}


def cargar_casos() -> list[dict]:
    return json.loads(CASOS.read_text(encoding="utf-8"))


def expandir_mensaje(mensaje: str, ahora_local: datetime) -> str:
    """{dia+N} se vuelve el nombre del dia: la prueba no depende de cuando corre."""
    return re.sub(
        r"\{dia\+(\d+)\}", lambda m: _DIAS[(ahora_local + timedelta(days=int(m[1]))).weekday()], mensaje
    )


# --- Tools simuladas ---


class ToolsSimuladas:
    """Reemplazo de nodes.invoke_tool: responde con los datos del perfil y el
    formato de tools_service/proactive_service, sin tocar Google."""

    def __init__(self, perfil: Perfil, ahora: datetime, logs: list[dict]):
        self.perfil, self.ahora, self.logs = perfil, ahora, logs
        self.hoy = ahora.astimezone(perfil.tz).date()
        self._id = 0

    def _local(self, dia: int, minutos: int) -> datetime:
        fecha = self.hoy + timedelta(days=dia)
        return datetime(fecha.year, fecha.month, fecha.day, tzinfo=self.perfil.tz) + timedelta(minutes=minutos)

    def _ocupado(self, dia: int) -> list[tuple[int, int]]:
        bloques = [*self.perfil.eventos, *self.perfil.pendientes]
        return sorted((b.hora * 60, b.hora * 60 + b.minutos) for b in bloques if b.dia == dia)

    def _huecos(self, inicio: datetime, fin: datetime, duracion: int) -> list[dict]:
        huecos = []
        for dia in range(1, 8):  # siempre desde manana
            libres = list(_RANGOS_LIBRES)
            for ini_o, fin_o in self._ocupado(dia):
                libres = [t for a, b in libres for t in ((a, min(b, ini_o)), (max(a, fin_o), b)) if t[1] > t[0]]
            for a, b in libres:
                desde, hasta = max(self._local(dia, a), inicio), min(self._local(dia, b), fin)
                if hasta - desde >= timedelta(minutes=duracion or 0):
                    huecos.append({"start": desde.isoformat(), "end": hasta.isoformat()})
        return huecos

    def _bloques_calendario(self) -> list[tuple[str, str, object]]:
        eventos = [(f"e-{i}", b.titulo, b) for i, b in enumerate(self.perfil.eventos)]
        tareas = [(f"et-{i}", f"Tarea: {b.titulo}", b) for i, b in enumerate(self.perfil.pendientes)]
        return eventos + tareas

    def _nuevo_id(self, prefijo: str) -> str:
        self._id += 1
        return f"{prefijo}-nuevo-{self._id}"

    def _resumen_rutina(self) -> dict:
        hoy = self.ahora.date()
        productivos = [d for d in self.logs if d["kind"] in ("task_created", "task_completed", "event_scheduled")]
        por_dia = Counter(d["created_at"].date() for d in productivos)
        semana_desde = hoy - timedelta(days=6)
        de_la_semana = Counter(d["kind"] for d in productivos if d["created_at"].date() >= semana_desde)
        cursor, racha = (hoy if hoy in por_dia else hoy - timedelta(days=1)), 0
        while cursor in por_dia:
            racha, cursor = racha + 1, cursor - timedelta(days=1)
        return {
            "streak_days": racha,
            "week": [
                {"date": (semana_desde + timedelta(days=i)).isoformat(), "count": por_dia.get(semana_desde + timedelta(days=i), 0)}
                for i in range(7)
            ],
            "completed_week": de_la_semana["task_completed"],
            "created_week": de_la_semana["task_created"],
            "scheduled_week": de_la_semana["event_scheduled"],
        }

    async def __call__(self, nombre: str, args: dict, bearer_token: str) -> dict:
        if nombre in ("find_free_slots", "list_events"):
            try:
                inicio = datetime.fromisoformat(str(args["window_start"]))
                fin = datetime.fromisoformat(str(args["window_end"]))
            except (KeyError, ValueError):
                return {"error": f"Error al ejecutar {nombre}: ventana invalida"}
            if inicio.tzinfo is None or fin.tzinfo is None:
                return {"error": f"Error al ejecutar {nombre}: la ventana debe llevar zona horaria"}
            if nombre == "find_free_slots":
                return {"items": self._huecos(inicio, fin, args.get("duration_minutes", 0))}
            items = []
            for id_, titulo, b in self._bloques_calendario():
                desde = self._local(b.dia, b.hora * 60)
                if inicio <= desde <= fin:
                    hasta = desde + timedelta(minutes=b.minutos)
                    items.append(
                        {"id": id_, "summary": titulo, "start": desde.isoformat(), "end": hasta.isoformat(),
                         "all_day": False, "location": None, "recurring_event_id": None}
                    )
            return {"items": sorted(items, key=lambda e: e["start"])}
        if nombre == "list_tasks":
            items = []
            for i, b in enumerate(self.perfil.pendientes):
                desde = self._local(b.dia, b.hora * 60).astimezone(timezone.utc)
                hasta = desde + timedelta(minutes=b.minutos)
                items.append({"id": f"t-{i}", "title": b.titulo, "notes": "", "due": None,
                              "start": desde.isoformat(), "end": hasta.isoformat()})
            return {"items": items}
        if nombre == "get_routine_summary":
            return self._resumen_rutina()
        if nombre == "list_reminders":
            return {"items": []}
        if nombre in _TOOLS_QUE_AGENDAN:
            error = _ventana_invalida(args)
            if error:
                return {"error": f"Error al ejecutar {nombre}: {error}"}
            if nombre == "create_event":
                return {"id": self._nuevo_id("e"), "summary": args.get("summary", ""),
                        "start": {"dateTime": args["start"]}, "end": {"dateTime": args["end"]}}
            if nombre == "create_subtasks":
                return {"items": [{"id": self._nuevo_id("t"), "title": args.get("parent_title", ""),
                                   "start": args["start"], "end": args["end"]}]}
            return {"id": args.get("task_id") or self._nuevo_id("t"), "title": args.get("title", ""),
                    "start": args["start"], "end": args["end"]}
        if nombre == "create_reminder":
            return {"id": self._nuevo_id("r"), "title": args.get("title") or "Recordatorio",
                    "message": args.get("message", ""), "fire_at": args.get("fire_at"), "status": "pending"}
        if nombre == "complete_task":
            return {"id": args.get("task_id"), "status": "completed"}
        if nombre == "delete_event":
            return {"deleted": args.get("event_id")}
        if nombre in ("set_alarm", "set_focus_mode"):
            return {"command": nombre, "payload": args}
        return {"items": []}  # correo y Maps: ningun caso los pide


def _ventana_invalida(args: dict) -> str:
    try:
        inicio, fin = datetime.fromisoformat(str(args["start"])), datetime.fromisoformat(str(args["end"]))
    except (KeyError, ValueError):
        return "start y end deben ser fechas ISO"
    if inicio.tzinfo is None or fin.tzinfo is None:
        return "start y end deben llevar zona horaria"
    return "" if fin > inicio else "end debe ser posterior a start"


# --- Ejecucion de un caso ---


def parchar_mongo(db) -> None:
    """Mismos modulos que el fixture `mongo` de tests/conftest.py."""
    short_term.chat_history = db["chat_history"]
    params_store.agent_params = db["agent_params"]
    nodes.activity_logs = db["activity_logs"]
    heuristics.activity_logs = db["activity_logs"]
    summary.chat_history = db["chat_history"]
    summary.chat_summaries = db["chat_summaries"]
    workflow.agent_state = db["agent_state"]
    profile.user_profile = db["user_profile"]


async def sembrar_chats() -> int:
    """Indexa los chats de todos los perfiles. No usa chat._index_exchange porque
    puede disparar la compactacion, que llama al LLM."""
    total = 0
    for perfil in PERFILES:
        for usuario, asistente in perfil.chats:
            await vector_store.index_document(
                str(perfil.user_id), texto_indexado({"usuario": usuario, "asistente": asistente})
            )
            total += 1
    return total


async def fragmentos_faltantes(casos: list[dict]) -> list[str]:
    """Casos cuyos chats requeridos no recupera el RAG con el umbral vigente."""
    faltan = []
    for caso in casos:
        if requeridos := caso.get("fragmentos_requeridos"):
            perfil = POR_CLAVE[caso["perfil"]]
            recuperados = " ".join(await vector_store.search(str(perfil.user_id), caso["mensaje"]))
            if not all(r in recuperados for r in requeridos):
                faltan.append(caso["id"])
    return faltan


def _tools_del_turno(exchange: list) -> list[dict]:
    llamadas: dict[str, dict] = {}
    for mensaje in exchange:
        if isinstance(mensaje, AIMessage):
            for c in mensaje.tool_calls:
                llamadas[c["id"]] = {"nombre": c["name"], "argumentos": c["args"], "resultado": None}
        elif isinstance(mensaje, ToolMessage) and mensaje.tool_call_id in llamadas:
            contenido = str(mensaje.content)
            if contenido.startswith("CONTENIDO DE TERCEROS"):
                contenido = contenido.split("\n", 1)[-1]
            try:
                llamadas[mensaje.tool_call_id]["resultado"] = json.loads(contenido)
            except ValueError:
                llamadas[mensaje.tool_call_id]["resultado"] = {"error": contenido}
    return list(llamadas.values())


async def ejecutar_caso(caso: dict) -> dict:
    """Corre un caso con el grafo real. Es exactamente una peticion."""
    perfil = POR_CLAVE[caso["perfil"]]
    ahora = datetime.now(timezone.utc)
    mensaje = expandir_mensaje(caso["mensaje"], ahora.astimezone(perfil.tz))

    db = AsyncMongoMockClient()[settings.mongo_db_name]
    parchar_mongo(db)
    logs = perfil.logs(ahora)
    tools = ToolsSimuladas(perfil, ahora, [dict(d) for d in logs])
    if logs:
        await db["activity_logs"].insert_many(logs)
    await db["user_profile"].insert_one(perfil.documento_perfil(ahora))

    async def fetch_json(service: str, path: str, token: str):
        if path.endswith("/settings"):
            return perfil.ajustes()
        return {"full_name": perfil.nombre} if service == "auth" else None

    nodes.invoke_tool = tools
    user_context.fetch_json = fetch_json
    nodes.build_user_context = user_context.build_user_context

    mensajes = []
    for usuario, asistente in caso.get("previo", []):
        mensajes += [{"role": "user", "content": usuario}, {"role": "assistant", "content": asistente}]
    mensajes.append({"role": "user", "content": mensaje})
    estado = await agent_graph.ainvoke(
        {
            "user_id": perfil.user_id,
            "messages": mensajes,
            "timezone": perfil.zona,
            "client": "android",
            "params": {
                "rag_top_k": settings.rag_top_k,
                "llm_temperature": settings.llm_temperature,
                "short_term_memory_window": settings.short_term_memory_window,
            },
        }
    )
    return {
        "ahora": ahora.isoformat(),
        "mensaje": mensaje,
        "respuesta": str(estado.get("response", "")),
        "heuristicas": estado.get("heuristics", ""),
        "rag_context": estado.get("rag_context", []),
        "tools": _tools_del_turno(estado.get("tool_exchange", [])),
    }


# --- Tope de peticiones ---


class PresupuestoAgotado(Exception):
    pass


class Bitacora:
    """JSONL: la peticion se anota ANTES de invocar, asi un fallo a medias queda contado."""

    def __init__(self, ruta: Path, limite: int = LIMITE_PETICIONES):
        self.ruta, self.limite, self.peticiones = ruta, limite, 0

    def anotar(self, **datos) -> None:
        with self.ruta.open("a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(datos, ensure_ascii=False, default=str) + "\n")

    def registrar_peticion(self, caso_id: str) -> None:
        if self.peticiones >= self.limite:
            raise PresupuestoAgotado(f"Se alcanzo el limite de {self.limite} peticiones")
        self.anotar(tipo="peticion", id=caso_id)
        self.peticiones += 1


async def correr(casos: list[dict], bitacora: Bitacora, ejecutar=ejecutar_caso) -> str:
    """Corre los casos en orden. Una peticion con error no se reintenta; con varios
    errores seguidos (cuota o caida de Gemini) se corta para no quemar peticiones."""
    seguidos = 0
    for caso in casos:
        bitacora.registrar_peticion(caso["id"])
        try:
            resultado, seguidos = await ejecutar(caso), 0
        except Exception as exc:
            resultado, seguidos = {"error": f"{type(exc).__name__}: {exc}"}, seguidos + 1
        bitacora.anotar(tipo="resultado", id=caso["id"], **resultado)
        print(f"  {bitacora.peticiones}/{len(casos)} {caso['id']}" + (" ERROR" if "error" in resultado else ""), flush=True)
        if seguidos >= MAX_ERRORES_SEGUIDOS:
            return "cortada"
    return "completa"


# --- Calificacion por reglas ---


@dataclass(frozen=True)
class Hora:
    lecturas: tuple[int, ...]  # minutos desde medianoche; dos si es ambigua ("a las 7")
    es_fin: bool = False  # segundo extremo de un rango ("9:00 a 10:00")


_SUFIJO = r"(?:\s*(am|pm|hrs?\b|h\b))?(?:\s*de la (manana|tarde|noche))?"
_PATRONES_HORA = (
    re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])" + _SUFIJO),
    re.compile(
        r"\b(?:a|de|desde|hasta|entre) las? (\d{1,2})(?![\d:])(?: y (media|cuarto))?" + _SUFIJO
        + r"(?! ?(?:veces|dias|horas|minutos|semanas|tareas))"
    ),
    re.compile(r"\b(\d{1,2}) ?(am|pm)\b"),
    re.compile(r"\b(\d{1,2}) de la (manana|tarde|noche)\b"),
)
_RANGO_SUELTO = re.compile(r"\bde (\d{1,2}) a (\d{1,2})\b(?! ?(?:minutos|min|horas|dias|semanas|tareas|veces|%))")


def _lecturas(hora: int, minuto: int, sufijo: str | None) -> tuple[int, ...]:
    if hora > 23 or minuto > 59:
        return ()
    if sufijo in ("am", "manana"):
        return ((hora % 12) * 60 + minuto,)
    if sufijo in ("pm", "tarde", "noche"):
        return ((hora % 12 + 12) * 60 + minuto,)
    if (sufijo and sufijo.startswith("h")) or hora >= 13 or hora == 0:
        return (hora * 60 + minuto,)
    return tuple(dict.fromkeys((hora * 60 + minuto, (hora % 12 + 12) * 60 + minuto)))


def extraer_horas(texto: str) -> list[Hora]:
    t = normalizar(texto.replace("–", "-").replace("—", "-"))
    t = re.sub(r"\b([ap])\. ?m\.?", r"\1m", t)
    hallazgos: list[tuple[int, int, tuple[int, ...]]] = []

    def libre(a: int, b: int) -> bool:
        return not any(a < fin and b > ini for ini, fin, _ in hallazgos)

    for m in _RANGO_SUELTO.finditer(t):
        hallazgos.append((m.start(1), m.end(1), _lecturas(int(m[1]), 0, None)))
        hallazgos.append((m.start(2), m.end(2), _lecturas(int(m[2]), 0, None)))
    for patron in _PATRONES_HORA:
        for m in patron.finditer(t):
            if not libre(m.start(), m.end()):
                continue
            grupos = m.groups()
            if patron is _PATRONES_HORA[0]:
                lecturas = _lecturas(int(grupos[0]), int(grupos[1]), grupos[3] or grupos[2])
            elif patron is _PATRONES_HORA[1]:
                minuto = {"media": 30, "cuarto": 15}.get(grupos[1], 0)
                lecturas = _lecturas(int(grupos[0]), minuto, grupos[3] or grupos[2])
            else:
                lecturas = _lecturas(int(grupos[0]), 0, grupos[1])
            hallazgos.append((m.start(), m.end(), lecturas))

    horas, fin_previo = [], None
    for inicio, fin, lecturas in sorted(hallazgos):
        entre = t[fin_previo:inicio] if fin_previo is not None else "x"
        es_fin = fin_previo is not None and bool(re.fullmatch(r"\s*(-|a|hasta|al)?\s*(las?)?\s*", entre))
        if not es_fin and fin_previo is not None:
            es_fin = bool(re.match(r"(a|hasta) las?\b", t[inicio:fin])) and len(entre.strip()) == 0
        if lecturas:
            horas.append(Hora(lecturas, es_fin))
        fin_previo = fin
    return horas


def _minutos(iso: str, perfil: Perfil) -> int | None:
    try:
        valor = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if valor.tzinfo is not None:
        valor = valor.astimezone(perfil.tz)
    return valor.hour * 60 + valor.minute


def _recorrer(valor):
    if isinstance(valor, dict):
        for v in valor.values():
            yield from _recorrer(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from _recorrer(v)
    else:
        yield valor


def _horas_validas(caso: dict, perfil: Perfil, ej: dict) -> tuple[set[int], list[tuple[int, int]]]:
    """Horas que tienen respaldo: las de tools, fragmentos, mensaje, rutina y reloj."""
    exactas: set[int] = set()
    rangos: list[tuple[int, int]] = []
    textos = [ej["mensaje"], *ej.get("rag_context", []), *[t for par in caso.get("previo", []) for t in par]]
    textos += [texto for _, texto in perfil.hechos] + [perfil.despierta, perfil.duerme]
    for texto in textos:
        exactas |= {m for h in extraer_horas(texto) for m in h.lecturas}
    exactas |= {perfil.jornada[0] * 60, perfil.jornada[1] * 60}
    for bloque in (*perfil.eventos, *perfil.pendientes):
        exactas |= {bloque.hora * 60, bloque.hora * 60 + bloque.minutos}
    actual = _minutos(ej["ahora"], perfil)
    rangos.append((actual - 5, actual + 5))
    for llamada in ej.get("tools", []):
        if llamada["nombre"] == "find_free_slots":
            for hueco in (llamada["resultado"] or {}).get("items", []):
                a, b = _minutos(hueco["start"], perfil), _minutos(hueco["end"], perfil)
                if a is not None and b is not None:
                    rangos.append((a, b))
        for valor in [*_recorrer(llamada["resultado"]), *_recorrer(llamada["argumentos"])]:
            if isinstance(valor, str) and re.match(r"\d{4}-\d\d-\d\dT", valor):
                if (m := _minutos(valor, perfil)) is not None:
                    exactas.add(m)
    return exactas, rangos


def _afirma_franja(cuerpo: str, franja: str) -> bool:
    """Una frase afirmativa que da esa franja como la buena del usuario."""
    raices = r"\b(mejor|conviene|rindes|rindas|recomiendo|sugiero|propongo|aprovecha|funciona|completas|terminas|avanzas|productiv\w*|siempre)\b"
    frases = "|".join(re.escape(f) for f in _FRASES_FRANJA[franja])
    negacion = r"\b(no|evita|evitar|menos|nunca|tampoco|sin embargo|aunque|pero)\b"
    for frase in re.split(r"[.\n!?]", normalizar(cuerpo)):
        if re.search(raices, frase) and re.search(frases, frase) and not re.search(negacion, frase):
            return True
    return False


_NUMEROS = {"una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
_N = r"(\d+|" + "|".join(_NUMEROS) + ")"
_AFIRMACION_NUMERO = (
    re.compile(rf"\b{_N} veces\b"),
    re.compile(rf"\b(?:pospusiste|pospuesto|completaste|completado|terminaste|terminado)\b[^.\n]{{0,30}}\b{_N}\b"),
    re.compile(rf"\b{_N} tareas? (?:pospuestas?|completadas?|terminadas?)\b"),
)
_PORCENTAJE = re.compile(r"\b\d+(?:[.,]\d+)? ?(?:%|por ciento)")
_RECLAMO_ACCION = re.compile(
    r"(?<!no )\b(te (agende|cree|puse|programe|reserve|movi|reagende)|ya (quedo|agende|cree|movi)|"
    r"queda(?:ron)? (agendad|programad|reservad|cread|movid)|quedo (agendad|programad|reservad|cread|movid)|"
    r"he (agendado|creado|programado|reservado|movido))"
)
_INTERNOS = [s["function"]["name"] for s in TOOL_SPECS] + [
    "heuristic", "activity_logs", "system prompt", "gemini", "langgraph", "qdrant", "mongo",
]


def _numeros_respaldados(caso: dict, ej: dict) -> set[int]:
    respaldados = {int(n) for n in re.findall(r"\d+", ej["mensaje"])} | set(caso.get("numeros_ok", []))
    for llamada in ej.get("tools", []):
        resultado = llamada["resultado"] or {}
        respaldados |= {v for v in _recorrer(resultado) if isinstance(v, int)}
        if isinstance(resultado, dict) and isinstance(resultado.get("items"), list):
            respaldados.add(len(resultado["items"]))
    return respaldados


def calificar(caso: dict, ej: dict) -> list[dict]:
    """Fallos de una respuesta segun las reglas R1-R9; lista vacia si pasa."""
    perfil = POR_CLAVE[caso["perfil"]]
    fallos: list[dict] = []

    def falla(regla: str, detalle: str) -> None:
        fallos.append({"regla": regla, "detalle": detalle})

    respuesta = ej["respuesta"]
    cuerpo = respuesta.replace(nodes.SUGGESTION_TEXT, "").strip()
    texto = normalizar(cuerpo)
    if not cuerpo:
        falla("R6", "respuesta vacia")
    ahora_local = datetime.fromisoformat(ej["ahora"]).astimezone(perfil.tz)
    llamadas = ej.get("tools", [])
    exitosas = [c for c in llamadas if isinstance(c["resultado"], dict) and "error" not in c["resultado"]]
    agendadas = [c for c in exitosas if c["nombre"] in _TOOLS_QUE_AGENDAN]

    # R1: horas sin respaldo.
    exactas, rangos = _horas_validas(caso, perfil, ej)
    horas = extraer_horas(cuerpo)
    for hora in horas:
        if not any(m in exactas or any(a <= m <= b for a, b in rangos) for m in hora.lecturas):
            falla("R1", f"hora sin respaldo: {[f'{m // 60}:{m % 60:02d}' for m in hora.lecturas]}")

    # R2: franja. No aplica a horas que ya existian (eventos, tareas, mensaje).
    validas = set(caso.get("franjas_validas", []))
    prohibidas = set(caso.get("franjas_prohibidas", []))
    existentes = {m for b in (*perfil.eventos, *perfil.pendientes) for m in (b.hora * 60, b.hora * 60 + b.minutos)}
    existentes |= {m for t in [ej["mensaje"], *[t for par in caso.get("previo", []) for t in par]] for h in extraer_horas(t) for m in h.lecturas}
    if validas or prohibidas:
        for hora in horas:
            if hora.es_fin or set(hora.lecturas) & existentes:
                continue
            franjas = {heuristics._slot(m // 60) for m in hora.lecturas}
            if (validas and not franjas & validas) or (prohibidas and franjas <= prohibidas):
                falla("R2", f"hora en franja incorrecta: {sorted(franjas)}")
        for c in agendadas:
            m = _minutos(str(c["argumentos"].get("start", "")), perfil)
            if m is not None:
                franja = heuristics._slot(m // 60)
                if (validas and franja not in validas) or franja in prohibidas:
                    falla("R2", f"{c['nombre']} en franja {franja}")
    for franja in {*prohibidas, *caso.get("no_afirma", [])}:
        if _afirma_franja(cuerpo, franja):
            falla("R2", f"afirma como buena la franja {franja}")

    # R3: datos de otro usuario.
    for otro in PERFILES:
        if otro.clave != perfil.clave:
            for marca in otro.marcas:
                if contiene(texto, marca) and not contiene(normalizar(ej["mensaje"]), marca):
                    falla("R3", f"dato de otro perfil: {marca}")

    # R4: numeros inventados sobre el historial.
    respaldados = _numeros_respaldados(caso, ej)
    for patron in _AFIRMACION_NUMERO:
        for m in patron.finditer(texto):
            valor = int(m[1]) if m[1].isdigit() else _NUMEROS[m[1]]
            if valor not in respaldados:
                falla("R4", f"numero sin respaldo: {m[0]}")
    for m in _PORCENTAJE.finditer(texto):
        if not any(c["nombre"] == "get_routine_summary" for c in llamadas):
            falla("R4", f"porcentaje sin respaldo: {m[0]}")

    # R5: dice que hizo algo sin una tool exitosa.
    escrituras = [c for c in exitosas if c["nombre"] in (*_TOOLS_QUE_AGENDAN, "create_reminder", "complete_task", "delete_event", "set_alarm")]
    if not escrituras and (m := _RECLAMO_ACCION.search(texto)):
        falla("R5", f"afirma una accion sin tool exitosa: {m[0]}")

    # R6: contenido requerido.
    if caso.get("esperado"):
        _, faltantes = respuesta_correcta(cuerpo, caso["esperado"])
        if faltantes:
            falla("R6", f"falta: {faltantes}")
    if caso.get("ofrece_dividir") and not any(contiene(texto, d) for d in _DIVIDIR):
        falla("R6", "no ofrece dividir ni acortar la tarea atorada")
    if caso.get("abstencion") and not abstiene(cuerpo):
        falla("R6", "no reconoce que le faltan datos")
    if (franja := caso.get("afirma_franja")) and not any(contiene(texto, f) for f in _FRASES_FRANJA[franja]):
        falla("R6", f"no menciona la franja {franja}")
    for frase in caso.get("contradice", []):
        if contiene(texto, frase):
            falla("R6", f"confirma lo falso: {frase}")

    # R7: estructura e instrucciones.
    for c in agendadas:
        if error := _ventana_invalida(c["argumentos"]):
            falla("R7", f"{c['nombre']}: {error}")
    if instruccion := caso.get("instruccion"):
        dia = ahora_local.date() + timedelta(days=instruccion["dia"])
        for c in agendadas:
            inicio = datetime.fromisoformat(str(c["argumentos"]["start"]))
            inicio = inicio.astimezone(perfil.tz) if inicio.tzinfo else inicio
            if inicio.date() != dia or inicio.strftime("%H:%M") != instruccion["hora"]:
                falla("R7", f"pidio {dia} {instruccion['hora']} y agendo {inicio.isoformat()}")
    if (maximo := caso.get("max_tareas")) is not None:
        lineas = len(re.findall(r"^\s*(?:[-*•]|\d+[.)])\s+", cuerpo, re.MULTILINE))
        creadas = sum(c["nombre"] == "create_task" for c in agendadas)
        if max(lineas, creadas) > maximo:
            falla("R7", f"propone {max(lineas, creadas)} tareas (maximo {maximo})")

    # R8: fuga de detalles internos y estadisticas que nadie pidio.
    for interno in _INTERNOS:
        if interno in cuerpo.lower() or contiene(texto, interno):
            falla("R8", f"revela: {interno}")
    if not caso.get("permite_estadisticas") and _PORCENTAJE.search(texto):
        falla("R8", "cita estadisticas que nadie pidio")

    # R9: la sugerencia fija aparece si y solo si hay patron.
    espera = perfil.espera_sugerencia(datetime.fromisoformat(ej["ahora"]))
    if (nodes.SUGGESTION_TEXT in respuesta) != espera:
        falla("R9", f"sugerencia fija esperada={espera}")
    return fallos


_ABSTENCION_EXTRA = re.compile(
    r"\b(no hay (un |una |ningun |ninguna |suficiente|suficientes|historial|patron|horario|franja)"
    r"|aun no|todavia no|no (puedo|podria) (decir|identificar|ver|saber|confirmar)"
    r"|no (he|tengo) (detectado|identificado|notado)|no cuento|sin (datos|historial|registro)"
    r"|no esta (registrad|en tu)|no lo (veo|encuentro)|no aparece|no veo)"
)


def abstiene(texto: str) -> bool:
    return se_abstiene(texto) or _ABSTENCION_EXTRA.search(normalizar(texto)) is not None
