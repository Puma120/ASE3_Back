"""Siembra del historial sintetico, metricas de recuperacion y calificacion de
las respuestas del agente, compartidas por tests/integration/test_rag_ollama.py
y tests/kpi/eval_obj2.py.

Relevancia: un fragmento recuperado es relevante si pertenece al mismo
usuario y comparte al menos un tema con la consulta (etiquetas del dataset).
hit@k: la consulta acierta si al menos uno de los k fragmentos es relevante
(el dato llega al prompt aunque no sea el primero).
Respuesta correcta: contiene todos los grupos de `esperado` de la consulta.
"""

import json
import math
import random
import re
import statistics
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.graph.builder import agent_graph
from app.memory import vector_store
from tests.support.historial import indexar_historial

DATASET = Path(__file__).resolve().parent.parent / "data" / "historial_sintetico.json"


@dataclass(frozen=True)
class Etiqueta:
    usuario: str
    temas: frozenset[str]


def cargar_dataset() -> dict:
    return json.loads(DATASET.read_text(encoding="utf-8"))


def texto_indexado(intercambio: dict) -> str:
    """Mismo formato que app/api/routes/chat.py:_index_exchange."""
    return f"Usuario: {intercambio['usuario']}\nAsistente: {intercambio['asistente']}"


def etiquetas(dataset: dict) -> dict[str, Etiqueta]:
    return {
        texto_indexado(i): Etiqueta(clave, frozenset(i["temas"]))
        for clave, usuario in dataset["usuarios"].items()
        for i in usuario["intercambios"]
    }


def total_intercambios(dataset: dict) -> int:
    return sum(len(u["intercambios"]) for u in dataset["usuarios"].values())


async def sembrar(dataset: dict) -> list[float]:
    """Indexa todo el historial con el codigo de produccion. Devuelve la
    latencia de cada indexado (embedding + upsert) en ms."""
    latencias = []
    for usuario in dataset["usuarios"].values():
        for i in usuario["intercambios"]:
            inicio = time.perf_counter()
            await indexar_historial(usuario["user_id"], [(i["usuario"], i["asistente"])])
            latencias.append((time.perf_counter() - inicio) * 1000)
    return latencias


def metricas_consulta(recuperados: list[str], consulta: dict, etiquetado: dict[str, Etiqueta]) -> dict:
    """Metricas de una operacion. Las consultas sin respuesta en el historial
    (temas vacio) no tienen precision: se registra cuantos fragmentos se
    devolvieron igualmente."""
    temas = set(consulta["temas"])
    propios = [etiquetado.get(t) for t in recuperados]
    relevantes = [e is not None and e.usuario == consulta["usuario"] and bool(e.temas & temas) for e in propios]
    fugas = sum(1 for e in propios if e is None or e.usuario != consulta["usuario"])
    base = {"nivel": consulta.get("nivel"), "fugas": fugas, "devueltos": len(recuperados), "relevantes": relevantes}
    if not temas:
        return {**base, "sin_respuesta": True, "precision": None, "hit@1": None, "hit@k": None, "recall": None, "rr": None}
    total_relevantes = sum(
        1 for e in etiquetado.values() if e.usuario == consulta["usuario"] and e.temas & temas
    )
    primer_relevante = next((pos for pos, ok in enumerate(relevantes, start=1) if ok), None)
    return {
        **base,
        "sin_respuesta": False,
        "precision": sum(relevantes) / len(recuperados) if recuperados else 0.0,
        "hit@1": bool(relevantes and relevantes[0]),
        "hit@k": any(relevantes),
        "recall": sum(relevantes) / total_relevantes if total_relevantes else 0.0,
        "rr": 1 / primer_relevante if primer_relevante else 0.0,
    }


async def evaluar_precision(
    dataset: dict, top_k: int, muestras: int | None = None, niveles: tuple[str, ...] | None = None
) -> dict:
    """Hace al menos `muestras` operaciones de recuperacion con
    vector_store.search (embedding + Qdrant, como en produccion), recorriendo
    las consultas en ciclo (como minimo una por consulta). `niveles` filtra
    las consultas por dificultad. Los agregados excluyen las consultas sin
    respuesta y ponderan por operacion; el reporte de KPIs agrega por consulta."""
    etiquetado = etiquetas(dataset)
    consultas = [c for c in dataset["consultas"] if not niveles or c.get("nivel") in niveles]
    operaciones = []
    for i in range(max(muestras or 0, len(consultas))):
        consulta = consultas[i % len(consultas)]
        user_id = dataset["usuarios"][consulta["usuario"]]["user_id"]
        inicio = time.perf_counter()
        recuperados = await vector_store.search(user_id, consulta["consulta"], top_k)
        latencia = (time.perf_counter() - inicio) * 1000
        operaciones.append(
            {
                "id": consulta["id"],
                "consulta": consulta["consulta"],
                "latencia_search_ms": latencia,
                "recuperados": recuperados,
                **metricas_consulta(recuperados, consulta, etiquetado),
            }
        )
    con_respuesta = [o for o in operaciones if not o["sin_respuesta"]]
    return {
        "precision": statistics.mean(o["precision"] for o in con_respuesta),
        "hit@1": statistics.mean(o["hit@1"] for o in con_respuesta),
        "hit@k": statistics.mean(o["hit@k"] for o in con_respuesta),
        "recall": statistics.mean(o["recall"] for o in con_respuesta),
        "mrr": statistics.mean(o["rr"] for o in con_respuesta),
        "fugas": sum(o["fugas"] for o in operaciones),
        "latencias_search_ms": [o["latencia_search_ms"] for o in operaciones],
        "operaciones": operaciones,
    }


def ic95_bootstrap(valores: list[float], repeticiones: int = 2000, semilla: int = 2026) -> list[float]:
    """IC 95 % de la media por bootstrap de percentiles: remuestrea las
    unidades independientes (consultas distintas), no las repeticiones."""
    rng = random.Random(semilla)
    medias = sorted(statistics.fmean(rng.choices(valores, k=len(valores))) for _ in range(repeticiones))
    return [medias[int(0.025 * repeticiones)], medias[int(0.975 * repeticiones) - 1]]


def resumen(muestras: list[float], bootstrap: bool = False) -> dict:
    """n, media, desviacion estandar, IC 95 % de la media y percentiles. El IC
    es normal (muestras independientes, p. ej. latencias) o por bootstrap
    (valores por consulta, acotados como los porcentajes)."""
    ordenadas = sorted(muestras)
    n = len(ordenadas)
    media = statistics.mean(ordenadas)
    desv = statistics.stdev(ordenadas) if n > 1 else 0.0
    margen = 1.96 * desv / math.sqrt(n)
    percentiles = statistics.quantiles(ordenadas, n=100, method="inclusive") if n > 1 else ordenadas * 99
    return {
        "n": n,
        "media": media,
        "desv": desv,
        "ic95": ic95_bootstrap(ordenadas) if bootstrap else [media - margen, media + margen],
        "min": ordenadas[0],
        "p50": statistics.median(ordenadas),
        "p95": percentiles[94],
        "max": ordenadas[-1],
    }


# Frases con las que el agente reconoce que no tiene el dato (texto normalizado).
_ABSTENCION = re.compile(
    r"\bno (tengo|encuentro|encontre|veo|aparece|cuento con|lo tengo|lo se|recuerdo|tengo registr"
    r"|hay (registro|informacion|datos|nada)|me has (dicho|comentado|mencionado)|mencionaste"
    r"|has mencionado|me dijiste|se (cuando|a que|que dia|donde|cual))"
)


def normalizar(texto: str) -> str:
    """Minusculas, sin acentos ni negritas; 10.30 -> 10:30 y 4,500 -> 4500."""
    t = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    t = t.replace("*", "")
    t = re.sub(r"(\d)\.(\d\d)\b", r"\1:\2", t)
    t = re.sub(r"(\d),(\d{3})\b", r"\1\2", t)
    return re.sub(r"\s+", " ", t)


def contiene(texto_normalizado: str, alternativa: str) -> bool:
    """Las palabras coinciden como prefijo ("avis" -> avisar); los numeros
    completos: "9" no coincide con "19" ni con los minutos de "10:30"."""
    alt = normalizar(alternativa)
    fin = r"(?!\d)" if alt[-1].isdigit() else ""
    return re.search(r"(?<![\w:])" + re.escape(alt) + fin, texto_normalizado) is not None


def respuesta_correcta(respuesta: str, esperado: list[list[str]]) -> tuple[bool, list[list[str]]]:
    """Correcta si contiene todos los grupos (basta una alternativa por grupo).
    Devuelve tambien los grupos que faltaron."""
    texto = normalizar(respuesta)
    faltantes = [grupo for grupo in esperado if not any(contiene(texto, alt) for alt in grupo)]
    return not faltantes, faltantes


def se_abstiene(respuesta: str) -> bool:
    return _ABSTENCION.search(normalizar(respuesta)) is not None


async def evaluar_respuestas(dataset: dict, top_k: int) -> list[dict]:
    """Corre el grafo real del agente por cada consulta, sin memoria corta (el
    dato solo puede venir del RAG), y califica la respuesta. Quien llama debe
    haber aislado el grafo: LLM local, contexto de usuario, tools y sugerencia
    proactiva (ver tests/kpi/eval_obj2.py:_aislar_grafo)."""
    etiquetado = etiquetas(dataset)
    resultados = []
    for numero, consulta in enumerate(dataset["consultas"], start=1):
        user_id = dataset["usuarios"][consulta["usuario"]]["user_id"]
        inicio = time.perf_counter()
        try:
            estado = await agent_graph.ainvoke(
                {
                    "user_id": user_id,
                    "bearer_token": "evaluacion-local",
                    "messages": [{"role": "user", "content": consulta["consulta"]}],
                    "params": {"rag_top_k": top_k, "llm_temperature": 0.0, "short_term_memory_window": 10},
                }
            )
            error = None
        except Exception as exc:  # una consulta fallida no tumba una corrida de horas
            estado, error = {}, f"{type(exc).__name__}: {exc}"
        latencia = (time.perf_counter() - inicio) * 1000

        respuesta = str(estado.get("response", ""))
        contexto = estado.get("rag_context", [])
        if consulta["esperado"] is None:
            correcta, faltantes, abstencion = None, [], se_abstiene(respuesta)
        else:
            correcta, faltantes = respuesta_correcta(respuesta, consulta["esperado"])
            abstencion = None
        resultados.append(
            {
                "id": consulta["id"],
                "respuesta": respuesta,
                "correcta": correcta,
                "faltantes": faltantes,
                "abstencion": abstencion,
                "fragmento_relevante_en_prompt": any(
                    metricas_consulta(contexto, consulta, etiquetado)["relevantes"]
                ),
                "tools": [
                    llamada["name"]
                    for mensaje in estado.get("tool_exchange", [])
                    for llamada in (getattr(mensaje, "tool_calls", None) or [])
                ],
                "latencia_agente_ms": latencia,
                "error": error,
            }
        )
        if numero % 20 == 0:
            print(f"  top_k={top_k}: {numero}/{len(dataset['consultas'])} respuestas", flush=True)
    return resultados
