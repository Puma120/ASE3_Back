"""KPI del Objetivo 4 (Tabla tab:kpi-obj4 de la tesina): respuestas sin
alucinaciones ni contradicciones frente a historiales simulados.

Gemini, el grafo, las heuristicas y el RAG son reales; las respuestas de las tools
y los datos de cada usuario son simulados. Mongo y Qdrant corren en memoria.

Uso, desde agent_service/:
    .venv\\Scripts\\python -m tests.kpi.eval_obj4 --casos 5        # ensayo gratis con Ollama
    .venv\\Scripts\\python -m tests.kpi.eval_obj4                  # ensayo completo gratis
    .venv\\Scripts\\python -m tests.kpi.eval_obj4 --llm gemini --verificar  # solo gasta embeddings
    .venv\\Scripts\\python -m tests.kpi.eval_obj4 --llm gemini --confirmar-gasto  # max. 100 peticiones
    .venv\\Scripts\\python -m tests.kpi.eval_obj4 --solo-calificar <corrida>  # no gasta

Las reglas no detectan afirmaciones en texto libre: el KPI final requiere llenar
`veredicto` ("coherente" o "falla") y `justificacion` en obj4_<corrida>_revision.json
y volver a correr --solo-calificar.
"""

import argparse
import asyncio
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[2]
RESULTADOS = Path(__file__).resolve().parent / "resultados"
COLECCION_EVAL = "tdah_agent_memory_eval_obj4"
RAG_MIN_SCORE_PRODUCCION = "0.5"  # configurar_entorno lo pone en -1 (sin umbral)
UMBRAL_CONTEXTO_RECORTADO = 0.98  # fraccion de num_ctx a partir de la cual se considera recortado


def clasificar(porcentaje: float) -> str:
    return "Óptimo" if porcentaje >= 98 else "Aceptable" if porcentaje >= 90 else "No aceptable"


def wilson(aciertos: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """IC 95 % de una proporcion, en %."""
    if not n:
        return (0.0, 0.0)
    p = aciertos / n
    denominador = 1 + z**2 / n
    centro = (p + z**2 / (2 * n)) / denominador
    margen = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominador
    return (max(0.0, centro - margen) * 100, min(1.0, centro + margen) * 100)


def _args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="KPI del Objetivo 4 (coherencia del agente)")
    parser.add_argument("--llm", choices=["ollama", "gemini"], default="ollama")
    parser.add_argument("--confirmar-gasto", action="store_true", help="obligatorio para correr con Gemini")
    parser.add_argument("--verificar", action="store_true", help="solo siembra el RAG y revisa los fragmentos requeridos")
    parser.add_argument("--casos", type=int, help="solo los primeros N casos (solo con Ollama)")
    parser.add_argument("--solo-calificar", metavar="CORRIDA", help="recalifica una corrida guardada, sin gastar")
    args = parser.parse_args(argv)
    if args.llm == "gemini" and not (args.verificar or args.solo_calificar) and not args.confirmar_gasto:
        parser.error("--llm gemini cobra: confirma con --confirmar-gasto")
    if args.llm == "gemini" and args.casos:
        parser.error("--casos solo aplica a Ollama")
    return args


class _Medido:
    def __init__(self, llm, contador, limite_ctx: int | None = None):
        self.llm, self.contador, self.limite_ctx = llm, contador, limite_ctx

    async def ainvoke(self, mensajes, **kwargs):
        self.contador["llamadas_llm"] += 1
        respuesta = await self.llm.ainvoke(mensajes, **kwargs)
        uso = getattr(respuesta, "usage_metadata", None) or {}
        entrada = uso.get("input_tokens", 0)
        self.contador["tokens_entrada"] += entrada
        self.contador["tokens_salida"] += uso.get("output_tokens", 0)
        # Ollama recorta sin avisar: un prompt que llega al limite ya no es el prompt real.
        if self.limite_ctx and entrada >= self.limite_ctx * UMBRAL_CONTEXTO_RECORTADO:
            raise RuntimeError(f"Contexto recortado: {entrada} tokens de entrada con num_ctx={self.limite_ctx}")
        return respuesta


class _EmbeddingsMedidos:
    def __init__(self, embeddings, contador):
        self.embeddings, self.contador, self.precalculados = embeddings, contador, {}

    async def aembed_query(self, texto):
        if texto in self.precalculados:
            return self.precalculados[texto]
        self.contador["embeddings"] += 1
        return await self.embeddings.aembed_query(texto)

    async def precalcular(self, textos):
        for texto in textos:
            self.precalculados[texto] = await self.aembed_query(texto)


def _preparar(llm: str, contador: Counter) -> str:
    """Conecta el grafo al modelo elegido y a Qdrant en memoria. Devuelve el nombre del modelo."""
    from qdrant_client import QdrantClient

    from app.core.config import settings
    from app.graph import nodes
    from app.memory import vector_store
    from tests.support import local_models
    from tests.support.entorno import verificar_entorno

    verificar_entorno(settings)
    vector_store.qdrant_client = QdrantClient(":memory:")
    if llm == "gemini":
        if not settings.gemini_api_key:
            raise SystemExit("Falta GEMINI_API_KEY en agent_service/.env")
        obtener, modelo, limite_ctx = nodes._get_llm, settings.gemini_chat_model, None
        embeddings = vector_store._get_embeddings()
    else:
        if motivo := local_models.motivo_no_disponible(local_models.OLLAMA_CHAT_MODEL, local_models.OLLAMA_EMBEDDING_MODEL):
            raise SystemExit(motivo)
        obtener, modelo, limite_ctx = local_models.get_llm_local(), local_models.OLLAMA_CHAT_MODEL, local_models.OLLAMA_NUM_CTX
        embeddings = local_models.build_embeddings()
        vector_store._EMBEDDING_SIZE = local_models.OLLAMA_EMBEDDING_SIZE
    vector_store._embeddings = _EmbeddingsMedidos(embeddings, contador)
    nodes._get_llm = lambda *a, **k: _Medido(obtener(*a, **k), contador, limite_ctx)
    return modelo


async def _correr(args: argparse.Namespace) -> str | None:
    from tests.support import coherencia_eval as ev

    contador: Counter = Counter()
    modelo = _preparar(args.llm, contador)
    casos = ev.cargar_casos()[: args.casos] if args.casos else ev.cargar_casos()

    print(f"Sembrando chats en el RAG ({args.llm})...", flush=True)
    chats = await ev.sembrar_chats()
    faltan = await ev.fragmentos_faltantes(casos)
    print(f"{chats} chats sembrados. Casos cuyo chat requerido no se recupera: {faltan or 'ninguno'}")
    if args.verificar:
        print(f"Embeddings usados: {contador['embeddings']}. No se hizo ninguna peticion al LLM.")
        return None
    if faltan and args.llm == "gemini":
        raise SystemExit("Revision previa fallida: no salio ninguna peticion. Ajusta esos casos.")
    if args.llm == "ollama":
        # Chat y embeddings no caben juntos en la GPU: el chat se reparte con la CPU y cada caso se alenta.
        from app.memory import vector_store
        from tests.support import local_models

        print("Precalculando embeddings y liberando la GPU...", flush=True)
        await vector_store._embeddings.precalcular(ev.mensajes_posibles(casos, datetime.now()))
        local_models.descargar(local_models.OLLAMA_EMBEDDING_MODEL, local_models.OLLAMA_CHAT_MODEL)

    RESULTADOS.mkdir(exist_ok=True)
    corrida = f"{datetime.now():%Y%m%d_%H%M%S}_{args.llm}"
    bitacora = ev.Bitacora(RESULTADOS / f"obj4_{corrida}.jsonl")
    bitacora.anotar(tipo="inicio", llm=args.llm, modelo=modelo, casos=len(casos), chats=chats, fecha=datetime.now().isoformat(timespec="seconds"))

    async def ejecutar(caso):
        antes = Counter(contador)
        try:
            resultado = await ev.ejecutar_caso(caso)
        except Exception:
            bitacora.anotar(tipo="consumo_error", id=caso["id"], consumo=dict(contador - antes))
            raise
        return {**resultado, "consumo": dict(contador - antes)}

    estado = await ev.correr(casos, bitacora, ejecutar)
    bitacora.anotar(tipo="fin", estado=estado, consumo=dict(contador))
    print(f"Corrida {estado}: {bitacora.peticiones} peticiones, consumo {dict(contador)}")
    return corrida


def _calificar(corrida: str) -> None:
    from tests.support import coherencia_eval as ev

    lineas = [json.loads(l) for l in (RESULTADOS / f"obj4_{corrida}.jsonl").read_text(encoding="utf-8").splitlines()]
    inicio = next(l for l in lineas if l["tipo"] == "inicio")
    fin = next((l for l in lineas if l["tipo"] == "fin"), {"estado": "interrumpida", "consumo": {}})
    peticiones = sum(l["tipo"] == "peticion" for l in lineas)
    resultados = {l["id"]: l for l in lineas if l["tipo"] == "resultado"}
    pedidos = [l["id"] for l in lineas if l["tipo"] == "peticion"]
    casos = {c["id"]: c for c in ev.cargar_casos()}

    ruta_revision = RESULTADOS / f"obj4_{corrida}_revision.json"
    previas = {r["id"]: r for r in json.loads(ruta_revision.read_text(encoding="utf-8"))} if ruta_revision.exists() else {}

    filas, errores = [], []
    for id_ in pedidos:
        resultado = resultados.get(id_)
        if resultado is None or "error" in resultado:
            errores.append({"id": id_, "error": (resultado or {}).get("error", "sin resultado")})
            continue
        caso = casos[id_]
        fallos = ev.calificar(caso, resultado)
        previa = previas.get(id_, {})
        filas.append(
            {
                "id": id_,
                "estrato": caso["estrato"],
                "perfil": caso["perfil"],
                "mensaje": resultado["mensaje"],
                "respuesta": resultado["respuesta"],
                "heuristicas": resultado["heuristicas"],
                "rag_context": resultado["rag_context"],
                "tools": resultado["tools"],
                "fallos_reglas": fallos,
                "omisiones_heuristicas": ev.omisiones_heuristicas(caso, resultado),
                "veredicto": previa.get("veredicto"),
                "justificacion": previa.get("justificacion", ""),
            }
        )
    ruta_revision.write_text(json.dumps(filas, ensure_ascii=False, indent=1, default=str), encoding="utf-8")

    n = len(filas)
    ok_auto = sum(not f["fallos_reglas"] for f in filas)
    pendientes = sum(f["veredicto"] not in ("coherente", "falla") for f in filas)
    ok_final = sum(f["veredicto"] == "coherente" for f in filas)
    pct_auto = ok_auto / n * 100 if n else 0.0
    valido = inicio["llm"] == "gemini" and n + len(errores) == len(casos)

    por_estrato = defaultdict(lambda: [0, 0])
    for f in filas:
        por_estrato[f["estrato"]][0] += not f["fallos_reglas"]
        por_estrato[f["estrato"]][1] += 1
    por_regla = Counter(r for f in filas for r in {x["regla"] for x in f["fallos_reglas"]})
    con_rag = sum(bool(f["rag_context"]) for f in filas)

    md = [
        "# KPI del Objetivo 4: coherencia del agente",
        "",
        f"- Corrida: `{corrida}` ({fin['estado']}) | modelo: {inicio['modelo']} | fecha: {inicio['fecha']}",
        f"- **Válida para el KPI: {'sí' if valido else 'NO (ensayo o corrida incompleta)'}**",
        f"- Peticiones: {peticiones} | consumo: {fin['consumo']}",
        f"- Evaluadas: {n} | errores fuera del denominador: {len(errores)} | con fragmentos del RAG: {con_rag}",
        "",
        "| Medición | Resultado | IC 95 % (Wilson) | Clase |",
        "|---|---|---|---|",
        f"| Solo reglas (preliminar) | {ok_auto}/{n} = {pct_auto:.1f} % | {wilson(ok_auto, n)[0]:.1f}–{wilson(ok_auto, n)[1]:.1f} % | {clasificar(pct_auto)} |",
    ]
    if pendientes:
        md.append(f"| Final, tras revisión humana | faltan {pendientes} veredictos | n/d | n/d |")
    else:
        pct = ok_final / n * 100 if n else 0.0
        md.append(f"| Final, tras revisión humana | {ok_final}/{n} = {pct:.1f} % | {wilson(ok_final, n)[0]:.1f}–{wilson(ok_final, n)[1]:.1f} % | {clasificar(pct)} |")
    md += ["", "## Por estrato (reglas)", "", "| Estrato | Pasan |", "|---|---|"]
    md += [f"| {e} | {a}/{t} |" for e, (a, t) in por_estrato.items()]
    md += ["", f"Fallos por regla: {dict(por_regla) or 'ninguno'}", "", "## Fallos de reglas", ""]
    md += [f"- **{f['id']}** ({f['perfil']}): {[x['regla'] + ' ' + x['detalle'] for x in f['fallos_reglas']]}\n  - {f['respuesta']!r}" for f in filas if f["fallos_reglas"]] or ["Ninguno."]
    medibles = [
        f for f in filas
        if any(k in casos[f["id"]] for k in ("esperado_heuristica", "ofrece_dividir", "afirma_franja"))
    ]
    omitidas = [f for f in medibles if f["omisiones_heuristicas"]]
    md += ["", "## Uso de heurísticas (aparte, no cuenta para el KPI)", ""]
    md += [f"Las usa en {len(medibles) - len(omitidas)}/{len(medibles)} casos donde aplicaban.", ""]
    md += [f"- **{f['id']}** ({f['perfil']}): {f['omisiones_heuristicas']}" for f in omitidas] or ["Sin omisiones."]
    if errores:
        md += ["", "## Errores", "", *[f"- {e['id']}: {e['error']}" for e in errores]]
    md += [
        "",
        "## Limitaciones",
        "",
        "- Las respuestas de las tools son simuladas: se mide coherencia con el historial, no que los eventos se creen en Google.",
        "- Mongo y Qdrant corren en memoria. Una sola corrida por caso, y Gemini no es determinista.",
        "- Las reglas no detectan afirmaciones en texto libre: el resultado válido es el final, tras la revisión humana.",
        "- Con n = 100 el IC es amplio: 98/100 da aproximadamente 93–99,4 %.",
        "",
    ]
    ruta_md = RESULTADOS / f"obj4_{corrida}.md"
    ruta_md.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md[:12]))
    print(f"Reporte: {ruta_md}\nRevisión: {ruta_revision}")


def main() -> None:
    args = _args()
    os.chdir(AGENT_DIR)  # config.py lee .env relativo al directorio actual
    sys.path.insert(0, str(AGENT_DIR))
    from tests.support.entorno import configurar_entorno

    # Sin Gemini la key queda vacia: un error aqui falla en vez de cobrar.
    configurar_entorno(COLECCION_EVAL, conservar_gemini=args.llm == "gemini" and not args.solo_calificar)
    os.environ["RAG_MIN_SCORE"] = RAG_MIN_SCORE_PRODUCCION
    os.environ.setdefault("OLLAMA_CHAT_MODEL", "qwen3.8")

    if args.solo_calificar:
        _calificar(args.solo_calificar)
        return
    if corrida := asyncio.run(_correr(args)):
        _calificar(corrida)


if __name__ == "__main__":
    main()
