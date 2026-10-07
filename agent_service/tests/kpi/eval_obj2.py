"""Evaluacion de los KPI del Objetivo 2 (Tabla tab:kpi-obj2 de la tesina):
latencia de la base vectorial, tokens por operacion de recuperacion y
precision de los fragmentos recuperados, con N muestras por indicador
(default 500). Ademas mide la exactitud de respuesta del agente: corre el
grafo real con qwen3.8 por cada consulta y califica si la respuesta contiene
el dato esperado (se omite con --sin-respuestas; tarda 1-2 h con k=1,3,5).

Siembra el historial sintetico (tests/data) en una coleccion aislada
(tdah_agent_memory_eval) usando el codigo de produccion, mide y escribe el
reporte en tests/kpi/resultados/ (JSON, Markdown y tabla LaTeX). Nunca toca
Railway ni la coleccion de produccion.

Uso, desde agent_service/:
    .venv\\Scripts\\python -m tests.kpi.eval_obj2 --top-k 1,3,5
    .venv\\Scripts\\python -m tests.kpi.eval_obj2 --embeddings gemini   # fiel a produccion (centavos de USD)

Requiere Ollama con qwen3-embedding:0.6b (embeddings) y qwen3.8 (conteo de
tokens). Para una latencia representativa levanta Qdrant en Docker:
    docker compose up -d qdrant
"""

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[2]
RESULTADOS = Path(__file__).resolve().parent / "resultados"
COLECCION_EVAL = "tdah_agent_memory_eval"
NIVELES = ("directa", "parafraseada", "vaga", "coloquial")


def clasificar_latencia(ms: float) -> str:
    return "Óptimo" if ms < 300 else "Aceptable" if ms <= 800 else "No aceptable"


def clasificar_tokens(tokens: float) -> str:
    return "Óptimo" if tokens < 500 else "Aceptable" if tokens <= 1200 else "No aceptable"


def clasificar_precision(porcentaje: float) -> str:
    return "Óptimo" if porcentaje >= 90 else "Aceptable" if porcentaje >= 75 else "No aceptable"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KPIs del Objetivo 2 (almacenamiento y recuperacion de contexto)")
    parser.add_argument("--embeddings", choices=["ollama", "gemini"], default="ollama")
    parser.add_argument("--qdrant-url", default="http://localhost:6333")
    parser.add_argument("--top-k", default="5", help="valores separados por coma, p. ej. 1,3,5 (produccion: 5)")
    parser.add_argument("--muestras", type=int, default=500, help="muestras por indicador y por top_k")
    parser.add_argument("--relleno", type=int, default=1000, help="intercambios extra del usuario evaluado (distractores)")
    parser.add_argument("--otros-usuarios", type=int, default=50, help="usuarios ficticios que cargan la coleccion")
    parser.add_argument("--puntos-por-usuario", type=int, default=200, help="puntos por cada usuario ficticio")
    parser.add_argument(
        "--sin-respuestas", action="store_true", help="omite la exactitud de respuesta del agente (la fase lenta)"
    )
    return parser.parse_args()


def _aislar_grafo() -> None:
    """Mismos reemplazos que tests/conftest.py: LLM local y sin servicios
    externos. Sin el de la sugerencia proactiva, el grafo leeria Mongo y
    esperaria 30 s por consulta."""
    from app.graph import nodes
    from tests.support.entorno import CONTEXTO_USUARIO_FIJO
    from tests.support.local_models import get_llm_local

    async def contexto_fijo(bearer_token: str) -> str:
        return CONTEXTO_USUARIO_FIJO

    async def tool_vacia(tool_name: str, payload: dict, bearer_token: str) -> dict:
        return {"items": []}

    async def sin_sugerencia(user_id: str) -> str:
        return ""

    nodes._get_llm = get_llm_local()
    nodes.build_user_context = contexto_fijo
    nodes.invoke_tool = tool_vacia
    nodes.proactive_suggestion_text = sin_sugerencia


def _conectar_qdrant(url: str, notas: list[str]):
    from qdrant_client import QdrantClient

    try:
        cliente = QdrantClient(url=url, timeout=5, check_compatibility=False)
        cliente.get_collections()
        return cliente, f"servidor {url}"
    except Exception:
        notas.append(
            f"Qdrant no respondio en {url}: se uso Qdrant en memoria (en proceso). La latencia NO es "
            "representativa de un servidor; levantalo con `docker compose up -d qdrant` y repite."
        )
        return QdrantClient(":memory:"), "en memoria (latencia no representativa)"


def _latencia_bd(cliente, consultas, vectores, user_ids, ks, muestras) -> dict:
    """Solo la consulta a Qdrant (vector ya calculado), con el mismo filtro que
    search(), recorriendo las consultas en ciclo."""
    from qdrant_client.http import models as qmodels

    def consultar(consulta, k):
        filtro = qmodels.Filter(
            must=[qmodels.FieldCondition(key="user_id", match=qmodels.MatchValue(value=user_ids[consulta["id"]]))]
        )
        inicio = time.perf_counter()
        cliente.query_points(COLECCION_EVAL, query=vectores[consulta["id"]], limit=k, query_filter=filtro)
        return (time.perf_counter() - inicio) * 1000

    for consulta in consultas[:5]:  # calentamiento
        consultar(consulta, max(ks))
    return {k: [consultar(consultas[i % len(consultas)], k) for i in range(muestras)] for k in ks}


async def _tokens(consultas, operaciones_por_k, ks, notas) -> dict:
    """Tokens de cada operacion de recuperacion: lo que el bloque recuperado
    agrega al prompt real del agente (prompt con contexto menos prompt sin el)
    mas los tokens de embeber la consulta. El conteo es determinista para un
    mismo texto, asi que se calcula una vez por (consulta, fragmentos)."""
    from app.graph import nodes
    from tests.support.entorno import CONTEXTO_USUARIO_FIJO
    from tests.support.local_models import ContadorTokens

    contador = ContadorTokens()

    def mensajes(texto, fragmentos):
        return nodes._to_langchain_messages(
            {
                "messages": [{"role": "user", "content": texto}],
                "user_context": CONTEXTO_USUARIO_FIJO,
                "rag_context": fragmentos,
            }
        )

    base, embedding = {}, {}
    for consulta in consultas:
        base[consulta["consulta"]] = await contador.prompt(mensajes(consulta["consulta"], []))
        embedding[consulta["consulta"]] = await contador.embedding(consulta["consulta"])
    if await contador.prompt(mensajes(consultas[0]["consulta"], [])) != base[consultas[0]["consulta"]]:
        notas.append("Advertencia: el conteo de tokens de Ollama vario entre llamadas identicas.")

    con_contexto: dict[tuple[str, tuple[str, ...]], int] = {}
    por_k = {}
    for k in ks:
        for operacion in operaciones_por_k[k]:
            clave = (operacion["consulta"], tuple(operacion["recuperados"]))
            if clave not in con_contexto:
                con_contexto[clave] = await contador.prompt(mensajes(clave[0], list(clave[1])))
            operacion["tokens_contexto"] = con_contexto[clave] - base[operacion["consulta"]]
            operacion["tokens_embedding"] = embedding[operacion["consulta"]]
            operacion["tokens_total"] = operacion["tokens_contexto"] + operacion["tokens_embedding"]
        por_k[k] = {
            "total": [o["tokens_total"] for o in operaciones_por_k[k]],
            "contexto": [o["tokens_contexto"] for o in operaciones_por_k[k]],
        }
    return por_k


def _resultados_distintos(operaciones: list[dict]) -> int:
    """Cuantas consultas recuperaron fragmentos distintos entre repeticiones."""
    vistos: dict[str, set] = {}
    for operacion in operaciones:
        vistos.setdefault(operacion["id"], set()).add(tuple(operacion["recuperados"]))
    return sum(1 for resultados in vistos.values() if len(resultados) > 1)


async def evaluar(args: argparse.Namespace) -> dict:
    from app.core.config import settings
    from app.memory import vector_store
    from tests.support import local_models, rag_eval, relleno
    from tests.support.entorno import verificar_entorno

    verificar_entorno(settings)
    ks = sorted({int(k) for k in args.top_k.split(",")})
    notas: list[str] = []

    cliente, modo_qdrant = _conectar_qdrant(args.qdrant_url, notas)
    vector_store.qdrant_client = cliente
    if args.embeddings == "ollama":
        motivo = local_models.motivo_no_disponible(local_models.OLLAMA_EMBEDDING_MODEL)
        if motivo:
            raise SystemExit(motivo)
        vector_store._embeddings = local_models.build_embeddings()
        vector_store._EMBEDDING_SIZE = local_models.OLLAMA_EMBEDDING_SIZE
        modelo_embeddings = f"{local_models.OLLAMA_EMBEDDING_MODEL} (Ollama, local)"
        notas.append(
            "Embeddings locales: la precision y la latencia de embedding difieren de produccion "
            "(gemini-embedding-001). Para el valor fiel a produccion usa --embeddings gemini."
        )
    else:
        if not settings.gemini_api_key:
            raise SystemExit("--embeddings gemini requiere GEMINI_API_KEY en agent_service/.env")
        modelo_embeddings = f"{settings.gemini_embedding_model} (Gemini, produccion)"

    print(f"Qdrant: {modo_qdrant} | coleccion: {COLECCION_EVAL} | embeddings: {modelo_embeddings}")
    if cliente.collection_exists(COLECCION_EVAL):
        cliente.delete_collection(COLECCION_EVAL)

    dataset = relleno.ampliar_dataset(rag_eval.cargar_dataset(), args.relleno)
    consultas = dataset["consultas"]
    historial_a = len(dataset["usuarios"]["a"]["intercambios"])
    print(f"Sembrando {rag_eval.total_intercambios(dataset)} intercambios con embeddings reales "
          f"({historial_a} del usuario evaluado)...")
    latencias_indexado = await rag_eval.sembrar(dataset)
    print(f"Sembrando {args.otros_usuarios} x {args.puntos_por_usuario} puntos de otros usuarios...")
    otros = relleno.sembrar_otros_usuarios(
        cliente, COLECCION_EVAL, args.otros_usuarios, args.puntos_por_usuario, vector_store._EMBEDDING_SIZE
    )
    indexados = cliente.count(COLECCION_EVAL).count
    if indexados != rag_eval.total_intercambios(dataset) + otros:
        raise SystemExit(f"Solo se indexaron {indexados} puntos; revisa el log de agent.chat")

    print(f"Midiendo latencia de la base vectorial ({args.muestras} muestras por top_k)...")
    vectores = {c["id"]: await vector_store._get_embeddings().aembed_query(c["consulta"]) for c in consultas}
    user_ids = {c["id"]: dataset["usuarios"][c["usuario"]]["user_id"] for c in consultas}
    latencias_bd = _latencia_bd(cliente, consultas, vectores, user_ids, ks, args.muestras)

    print(f"Recuperando con search() de produccion ({args.muestras} operaciones por top_k)...")
    precision = {k: await rag_eval.evaluar_precision(dataset, k, args.muestras) for k in ks}
    distintos = {k: _resultados_distintos(precision[k]["operaciones"]) for k in ks}
    if any(distintos.values()):
        notas.append(f"Consultas con resultados distintos entre repeticiones (por top_k): {distintos}.")
    else:
        notas.append(
            "Cada consulta recupero siempre los mismos fragmentos en sus repeticiones. Por eso precision y "
            "tokens se agregan por consulta distinta (n = consultas) con IC 95 % por bootstrap sobre las "
            "consultas; las latencias si son muestras independientes (n = muestras, IC normal)."
        )

    tokens = None
    motivo = local_models.motivo_no_disponible(local_models.OLLAMA_CHAT_MODEL)
    if motivo:
        notas.append(f"Sin conteo de tokens: {motivo}")
    else:
        print("Contando tokens con el tokenizer local...")
        tokens = await _tokens(consultas, {k: precision[k]["operaciones"] for k in ks}, ks, notas)
        notas.append(
            f"Tokens contados con el tokenizer de {local_models.OLLAMA_CHAT_MODEL}: aproximan el consumo "
            "en Gemini (tokenizers distintos). Contexto = tokens que el bloque recuperado agrega al prompt "
            "real del agente; total = contexto + embedding de la consulta."
        )

    respuestas = None
    if args.sin_respuestas:
        notas.append("Exactitud de respuesta omitida (--sin-respuestas).")
    elif motivo:
        notas.append(f"Sin exactitud de respuesta: {motivo}")
    else:
        _aislar_grafo()
        respuestas = {}
        for k in ks:
            print(f"Generando respuestas del agente con top_k={k} ({len(consultas)} consultas)...", flush=True)
            respuestas[k] = {r["id"]: r for r in await rag_eval.evaluar_respuestas(dataset, k)}
        notas.append(
            f"Exactitud de respuesta: grafo real del agente con {local_models.OLLAMA_CHAT_MODEL} a temperatura 0, "
            "una corrida por consulta, sin memoria corta (el dato solo puede venir del RAG) y con tools que "
            "devuelven vacio. Correcta = contiene todos los datos esperados de la consulta (calificacion "
            "automatica por coincidencia de texto; las respuestas quedan en el JSON para auditarlas)."
        )

    if modo_qdrant.startswith("servidor"):
        cliente.delete_collection(COLECCION_EVAL)

    kpis = {}
    detalle = {}
    for k in ks:
        filas = _por_consulta(precision[k]["operaciones"])
        if respuestas:
            for fila in filas:
                fila.update({c: v for c, v in respuestas[k][fila["id"]].items() if c != "id"})
        detalle[k] = filas
        con = [f for f in filas if not f["sin_respuesta"]]
        sin = [f for f in filas if f["sin_respuesta"]]
        lat = rag_eval.resumen(latencias_bd[k])
        prec = rag_eval.resumen([f["precision"] * 100 for f in con], bootstrap=True)
        tok = rag_eval.resumen([f["tokens_total"] for f in filas], bootstrap=True) if tokens else None
        kpis[k] = {
            "latencia_bd_ms": lat,
            "latencia_search_ms": rag_eval.resumen(precision[k]["latencias_search_ms"]),
            "tokens_total": tok,
            "tokens_contexto": rag_eval.resumen([f["tokens_contexto"] for f in filas], bootstrap=True)
            if tokens
            else None,
            "precision_pct": prec,
            "precision_por_nivel_pct": {
                nivel: rag_eval.resumen([f["precision"] * 100 for f in con if f["nivel"] == nivel], bootstrap=True)
                for nivel in NIVELES
                if any(f["nivel"] == nivel for f in con)
            },
            "hit@1_pct": statistics.fmean(f["hit@1"] for f in con) * 100,
            "recall_pct": statistics.fmean(f["recall"] for f in con) * 100,
            "mrr": statistics.fmean(f["rr"] for f in con),
            "fugas_entre_usuarios": precision[k]["fugas"],
            "sin_respuesta": {
                "consultas": len(sin),
                "con_fragmentos_pct": statistics.fmean(f["devueltos"] > 0 for f in sin) * 100 if sin else None,
                "fragmentos_media": statistics.fmean(f["devueltos"] for f in sin) if sin else None,
                "tokens_media": statistics.fmean(f["tokens_total"] for f in sin) if sin and tokens else None,
            },
            "clasificacion": {
                "latencia": clasificar_latencia(lat["p95"]),
                "tokens": clasificar_tokens(tok["media"]) if tok else None,
                "precision": clasificar_precision(prec["media"]),
            },
            "respuestas": _resumen_respuestas(filas) if respuestas else None,
        }

    return {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "configuracion": {
            "qdrant": modo_qdrant,
            "coleccion": COLECCION_EVAL,
            "embeddings": modelo_embeddings,
            "modelo_tokens": local_models.OLLAMA_CHAT_MODEL,
            "top_k_produccion": settings.rag_top_k,
            "top_k_evaluados": ks,
            "muestras_por_indicador": args.muestras,
            "puntos_en_coleccion": indexados,
            "historial_usuario_evaluado": historial_a,
            "intercambios_de_relleno": args.relleno,
            "otros_usuarios": f"{args.otros_usuarios} x {args.puntos_por_usuario} puntos (vectores aleatorios)",
            "consultas_distintas": len(consultas),
            "consultas_por_nivel": dict(Counter(c.get("nivel") for c in consultas)),
            "equipo": f"{platform.platform()} | {platform.processor()}",
        },
        "latencia_indexado_ms": rag_eval.resumen(latencias_indexado),
        "kpis": {str(k): v for k, v in kpis.items()},
        # Una fila por consulta distinta (las repeticiones dan el mismo resultado).
        "detalle": {str(k): detalle[k] for k in ks},
        "muestras": {
            str(k): {
                "latencia_bd_ms": latencias_bd[k],
                "latencia_search_ms": precision[k]["latencias_search_ms"],
            }
            for k in ks
        },
        "notas": notas,
    }


def _por_consulta(operaciones: list[dict]) -> list[dict]:
    """Una fila por consulta distinta, promediando sus repeticiones. Precision
    y tokens se agregan asi porque la unidad independiente es la consulta:
    repetir una consulta da el mismo resultado y no agrega informacion."""
    grupos: dict[str, list[dict]] = {}
    for operacion in operaciones:
        grupos.setdefault(operacion["id"], []).append(operacion)

    def media(ops: list[dict], campo: str):
        valores = [o[campo] for o in ops if o.get(campo) is not None]
        return statistics.fmean(valores) if valores else None

    return [
        {
            "id": id_,
            "consulta": ops[0]["consulta"],
            "nivel": ops[0]["nivel"],
            "sin_respuesta": ops[0]["sin_respuesta"],
            "repeticiones": len(ops),
            "precision": media(ops, "precision"),
            "hit@1": media(ops, "hit@1"),
            "recall": media(ops, "recall"),
            "rr": media(ops, "rr"),
            "devueltos": media(ops, "devueltos"),
            "tokens_contexto": media(ops, "tokens_contexto"),
            "tokens_total": media(ops, "tokens_total"),
            "recuperados": ops[0]["recuperados"],
            "relevantes": ops[0]["relevantes"],
        }
        for id_, ops in grupos.items()
    ]


def _resumen_respuestas(filas: list[dict]) -> dict:
    """Exactitud de respuesta (sobre las consultas con respuesta), su cruce con
    la recuperacion y la abstencion en las consultas sin respuesta."""
    from tests.support import rag_eval

    con = [f for f in filas if not f["sin_respuesta"]]
    sin = [f for f in filas if f["sin_respuesta"]]

    def pct(condicion, grupo) -> float | None:
        return statistics.fmean(bool(condicion(f)) for f in grupo) * 100 if grupo else None

    def cuenta(relevante: bool, correcta: bool) -> int:
        return sum(1 for f in con if f["fragmento_relevante_en_prompt"] == relevante and f["correcta"] == correcta)

    return {
        "exactitud_pct": rag_eval.resumen([100.0 * f["correcta"] for f in con], bootstrap=True),
        "exactitud_por_nivel_pct": {
            nivel: rag_eval.resumen([100.0 * f["correcta"] for f in con if f["nivel"] == nivel], bootstrap=True)
            for nivel in NIVELES
            if any(f["nivel"] == nivel for f in con)
        },
        "cruce": {
            "relevante_y_correcta": cuenta(True, True),
            "relevante_e_incorrecta": cuenta(True, False),
            "sin_relevante_y_correcta": cuenta(False, True),
            "sin_relevante_e_incorrecta": cuenta(False, False),
        },
        "abstencion": {
            "consultas": len(sin),
            "se_abstiene_pct": pct(lambda f: f["abstencion"], sin),
            "responde_algo_pct": pct(lambda f: not f["abstencion"], sin),
        },
        "latencia_agente_ms": rag_eval.resumen([f["latencia_agente_ms"] for f in filas]),
        "con_tools_pct": pct(lambda f: f["tools"], filas),
        "errores": sum(1 for f in filas if f["error"]),
    }


def _fmt(r: dict | None, decimales: int = 1, unidad: str = "") -> str:
    if not r:
        return "n/d"
    return (
        f"{r['media']:.{decimales}f} ± {r['desv']:.{decimales}f}{unidad} "
        f"(IC95 {r['ic95'][0]:.{decimales}f}–{r['ic95'][1]:.{decimales}f})"
    )


def _markdown(reporte: dict) -> str:
    cfg = reporte["configuracion"]
    lineas = [
        "# KPIs del Objetivo 2: almacenamiento y recuperación de contexto",
        "",
        f"- Fecha: {reporte['fecha']}",
        f"- Qdrant: {cfg['qdrant']} (colección `{cfg['coleccion']}`)",
        f"- Embeddings: {cfg['embeddings']}",
        f"- Muestras de latencia por top_k: **{cfg['muestras_por_indicador']}**; consultas distintas: "
        f"**{cfg['consultas_distintas']}** ({', '.join(f'{n} {v}' for v, n in cfg['consultas_por_nivel'].items())})",
        f"- Historial del usuario evaluado: {cfg['historial_usuario_evaluado']} intercambios "
        f"({cfg['intercambios_de_relleno']} de relleno que no responden ninguna consulta)",
        f"- Otros usuarios en la colección: {cfg['otros_usuarios']}; total de puntos: {cfg['puntos_en_coleccion']}",
        f"- top_k en producción: {cfg['top_k_produccion']}",
        f"- Equipo: {cfg['equipo']}",
        "",
        "## Resultado por KPI",
        "",
        "| top_k | Latencia BD p95 (ms) | Clase | Tokens por recuperación (media) | Clase | Precisión (%) | Clase |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, kpi in reporte["kpis"].items():
        clase = kpi["clasificacion"]
        tokens = f"{kpi['tokens_total']['media']:.0f}" if kpi["tokens_total"] else "n/d"
        lineas.append(
            f"| {k} | {kpi['latencia_bd_ms']['p95']:.2f} | {clase['latencia']} | {tokens} | {clase['tokens'] or 'n/d'} "
            f"| {kpi['precision_pct']['media']:.1f} | {clase['precision']} |"
        )
    if any(kpi["respuestas"] for kpi in reporte["kpis"].values()):
        lineas += [
            "",
            "## Recuperación contra respuesta del agente",
            "",
            "| top_k | Precisión de recuperación (%) | Exactitud de respuesta (%) | Se abstiene sin dato (%) "
            "| Tokens por recuperación |",
            "|---|---|---|---|---|",
        ]
        for k, kpi in reporte["kpis"].items():
            r = kpi["respuestas"]
            if not r:
                continue
            exacta = r["exactitud_pct"]
            abstiene = r["abstencion"]["se_abstiene_pct"]
            tokens = f"{kpi['tokens_total']['media']:.0f}" if kpi["tokens_total"] else "n/d"
            lineas.append(
                f"| {k} | {kpi['precision_pct']['media']:.1f} | {exacta['media']:.1f} "
                f"({exacta['ic95'][0]:.1f}–{exacta['ic95'][1]:.1f}) "
                f"| {f'{abstiene:.0f}' if abstiene is not None else 'n/d'} | {tokens} |"
            )
    lineas += ["", "## Estadísticos (media ± desviación estándar, IC 95 % de la media)", ""]
    for k, kpi in reporte["kpis"].items():
        lat = kpi["latencia_bd_ms"]
        lineas += [
            f"### top_k = {k}",
            "",
            "| Indicador | n | Media ± desv. (IC 95 %) | p50 | p95 | Mín / Máx |",
            "|---|---|---|---|---|---|",
            f"| Latencia BD (ms) | {lat['n']} | {_fmt(lat, 2)} | {lat['p50']:.2f} | {lat['p95']:.2f} "
            f"| {lat['min']:.2f} / {lat['max']:.2f} |",
        ]
        busq = kpi["latencia_search_ms"]
        lineas.append(
            f"| search() completo: embedding + BD (ms) | {busq['n']} | {_fmt(busq, 1)} | {busq['p50']:.1f} "
            f"| {busq['p95']:.1f} | {busq['min']:.1f} / {busq['max']:.1f} |"
        )
        for nombre, clave in (("Tokens por recuperación (total)", "tokens_total"), ("Tokens del bloque de contexto", "tokens_contexto")):
            r = kpi[clave]
            if r:
                lineas.append(
                    f"| {nombre} | {r['n']} | {_fmt(r, 1)} | {r['p50']:.0f} | {r['p95']:.0f} | {r['min']:.0f} / {r['max']:.0f} |"
                )
        prec = kpi["precision_pct"]
        lineas += [
            f"| Precisión (%), por consulta | {prec['n']} | {_fmt(prec, 1)} | {prec['p50']:.0f} | {prec['p95']:.0f} "
            f"| {prec['min']:.0f} / {prec['max']:.0f} |",
            "",
            "Precisión por nivel de dificultad de la consulta:",
            "",
            "| Nivel | Consultas | Precisión media (IC 95 %) | Clase |",
            "|---|---|---|---|",
            *[
                f"| {nivel} | {r['n']} | {r['media']:.1f} % ({r['ic95'][0]:.1f}–{r['ic95'][1]:.1f}) "
                f"| {clasificar_precision(r['media'])} |"
                for nivel, r in kpi["precision_por_nivel_pct"].items()
            ],
            "",
            f"Complementarias: hit@1 {kpi['hit@1_pct']:.1f} %, recall {kpi['recall_pct']:.1f} %, "
            f"MRR {kpi['mrr']:.3f}, fugas entre usuarios {kpi['fugas_entre_usuarios']}.",
            "",
        ]
        sin = kpi["sin_respuesta"]
        if sin["consultas"]:
            tokens_sin = f", con {sin['tokens_media']:.0f} tokens de media" if sin["tokens_media"] is not None else ""
            lineas += [
                f"Consultas sin respuesta en el historial ({sin['consultas']}): el {sin['con_fragmentos_pct']:.0f} % "
                f"recibió fragmentos igualmente (media {sin['fragmentos_media']:.1f}){tokens_sin}; todos son "
                "irrelevantes porque search() no tiene umbral de similitud.",
                "",
            ]
        lineas += _markdown_respuestas(reporte["configuracion"], kpi["respuestas"])
    indexado = reporte["latencia_indexado_ms"]
    lineas += [
        f"Indexado (embedding + upsert, n={indexado['n']}): media {indexado['media']:.1f} ms, "
        f"p95 {indexado['p95']:.1f} ms.",
        "",
        "Criterios: latencia clasificada por el p95 de la consulta a Qdrant; tokens por la media del total por "
        "recuperación (todas las consultas); precisión por la media, sobre las consultas con respuesta, del % "
        "de fragmentos recuperados que son del mismo usuario y del mismo tema que la consulta.",
        "",
        "## Notas",
        "",
        *[f"- {nota}" for nota in reporte["notas"]],
        "",
        "## Tabla LaTeX",
        "",
        "```latex",
        _latex(reporte),
        "```",
        "",
    ]
    return "\n".join(lineas)


def _markdown_respuestas(cfg: dict, r: dict | None) -> list[str]:
    if not r:
        return []
    exacta, cruce, abst, lat = r["exactitud_pct"], r["cruce"], r["abstencion"], r["latencia_agente_ms"]
    lineas = [
        f"#### Exactitud de respuesta del agente ({cfg['modelo_tokens']}, temperatura 0)",
        "",
        f"Respuestas correctas: **{exacta['media']:.1f} %** (IC 95 % {exacta['ic95'][0]:.1f}–{exacta['ic95'][1]:.1f}, "
        f"n = {exacta['n']} consultas con respuesta).",
        "",
        "| Nivel | Consultas | Exactitud (IC 95 %) |",
        "|---|---|---|",
        *[
            f"| {nivel} | {e['n']} | {e['media']:.1f} % ({e['ic95'][0]:.1f}–{e['ic95'][1]:.1f}) |"
            for nivel, e in r["exactitud_por_nivel_pct"].items()
        ],
        "",
        "Cruce entre recuperación y respuesta (consultas):",
        "",
        "| | Respuesta correcta | Respuesta incorrecta |",
        "|---|---|---|",
        f"| Llegó un fragmento relevante al prompt | {cruce['relevante_y_correcta']} | {cruce['relevante_e_incorrecta']} |",
        f"| No llegó ningún fragmento relevante | {cruce['sin_relevante_y_correcta']} "
        f"| {cruce['sin_relevante_e_incorrecta']} |",
        "",
    ]
    if abst["consultas"]:
        lineas += [
            f"Consultas sin respuesta en el historial ({abst['consultas']}): el agente dijo no tener el dato en el "
            f"{abst['se_abstiene_pct']:.0f} % y respondió algo en el {abst['responde_algo_pct']:.0f} % "
            "(revisar en el JSON si inventó).",
            "",
        ]
    lineas += [
        f"Latencia de extremo a extremo del agente: media {lat['media']:.0f} ms, p95 {lat['p95']:.0f} ms. "
        f"Pidió tools en el {r['con_tools_pct']:.0f} % de las consultas. Errores: {r['errores']}.",
        "",
    ]
    return lineas


def _latex(reporte: dict) -> str:
    cfg = reporte["configuracion"]
    k = str(cfg["top_k_produccion"]) if str(cfg["top_k_produccion"]) in reporte["kpis"] else list(reporte["kpis"])[-1]
    kpi = reporte["kpis"][k]
    clase = kpi["clasificacion"]
    lat, prec, tok = kpi["latencia_bd_ms"], kpi["precision_pct"], kpi["tokens_total"]
    tokens = f"{tok['media']:.0f} $\\pm$ {tok['desv']:.0f}" if tok else "n/d"
    return "\n".join(
        [
            r"\begin{table}[h]",
            r"\centering",
            rf"\caption{{Resultados de los indicadores de almacenamiento y recuperación "
            rf"(top-$k$ = {k}; latencia: $n$ = {lat['n']} mediciones; tokens: $n$ = {tok['n'] if tok else 0} "
            rf"consultas; precisión: $n$ = {prec['n']} consultas con respuesta)}}",
            r"\label{tab:kpi-obj2-resultados}",
            r"\footnotesize",
            r"\begin{tabular}{p{3.4cm} p{2.4cm} p{1.9cm}}",
            r"\hline",
            r"\textbf{Indicador (KPI)} & \textbf{Valor medido} & \textbf{Clasificación} \\",
            r"\hline",
            rf"Latencia de consulta a la base vectorial (p95) & {lat['p95']:.2f} ms & {clase['latencia']} \\",
            rf"Consumo de tokens por operación de recuperación (media) & {tokens} & {clase['tokens'] or 'n/d'} \\",
            rf"Precisión de recuperación (\% de fragmentos relevantes) & {prec['media']:.1f} $\pm$ {prec['desv']:.1f}\% "
            rf"& {clase['precision']} \\",
            r"\hline",
            r"\end{tabular}",
            r"\end{table}",
            *_latex_respuestas(reporte),
        ]
    )


def _latex_respuestas(reporte: dict) -> list[str]:
    filas = [(k, kpi) for k, kpi in reporte["kpis"].items() if kpi["respuestas"]]
    if not filas:
        return []
    lineas = [
        "",
        r"\begin{table}[h]",
        r"\centering",
        rf"\caption{{Exactitud de respuesta del agente por top-$k$ ({reporte['configuracion']['modelo_tokens']}, "
        rf"$n$ = {filas[0][1]['respuestas']['exactitud_pct']['n']} consultas con respuesta)}}",
        r"\label{tab:kpi-obj2-respuestas}",
        r"\footnotesize",
        r"\begin{tabular}{p{1.2cm} p{2.6cm} p{2.6cm} p{2.2cm}}",
        r"\hline",
        r"\textbf{top-$k$} & \textbf{Precisión de recuperación} & \textbf{Exactitud de respuesta} "
        r"& \textbf{Se abstiene sin dato} \\",
        r"\hline",
    ]
    for k, kpi in filas:
        exacta = kpi["respuestas"]["exactitud_pct"]
        abstiene = kpi["respuestas"]["abstencion"]["se_abstiene_pct"]
        abstiene_txt = rf"{abstiene:.0f}\%" if abstiene is not None else "n/d"
        lineas.append(
            rf"{k} & {kpi['precision_pct']['media']:.1f}\% & {exacta['media']:.1f}\% "
            rf"({exacta['ic95'][0]:.1f}--{exacta['ic95'][1]:.1f}) & {abstiene_txt} \\"
        )
    return [*lineas, r"\hline", r"\end{tabular}", r"\end{table}"]


def main() -> None:
    args = _args()
    os.chdir(AGENT_DIR)  # config.py lee .env relativo al directorio actual
    sys.path.insert(0, str(AGENT_DIR))
    from tests.support.entorno import configurar_entorno

    configurar_entorno(COLECCION_EVAL, qdrant_url=args.qdrant_url, conservar_gemini=args.embeddings == "gemini")

    reporte = asyncio.run(evaluar(args))

    RESULTADOS.mkdir(exist_ok=True)
    nombre = f"obj2_{datetime.now():%Y%m%d_%H%M%S}_{args.embeddings}"
    ruta_json = RESULTADOS / f"{nombre}.json"
    ruta_md = RESULTADOS / f"{nombre}.md"
    ruta_json.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = _markdown(reporte)
    ruta_md.write_text(markdown, encoding="utf-8")

    print()
    print(markdown.split("## Estadísticos")[0])
    print(f"Reporte: {ruta_md}\nDatos:   {ruta_json}")


if __name__ == "__main__":
    main()
