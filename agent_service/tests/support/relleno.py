"""Historial de relleno para evaluar la recuperacion con volumen realista.

- Usuario A: intercambios generados por plantillas (semilla fija) sobre
  asuntos de organizacion que NO responden ninguna consulta del dataset
  (lavar ropa, tramites, salidas, pendientes de casa...). Hablan de dias y
  horas igual que los temas etiquetados, asi que compiten como distractores
  reales. Se embeben con el modelo real.
- Otros usuarios: puntos con vectores aleatorios. Solo cargan la coleccion
  para que el filtro por user_id trabaje entre muchos usuarios, como en
  produccion; nunca deben aparecer en los resultados del usuario A.
"""

import random
import uuid

from qdrant_client.http import models as qmodels

TEMA_RELLENO = "relleno"

# Ninguna coincide con los asuntos etiquetados (limpieza con la roomie, comida
# familiar, natacion...): si lo hiciera, un fragmento "irrelevante" podria
# responder la consulta y las etiquetas dejarian de ser validas.
_ACTIVIDADES = [
    "lavar la ropa", "regar las plantas", "recoger un paquete en la paquetería",
    "cortarme el cabello", "llamar a mi abuela", "ir por mi hermano a la secundaria",
    "cocinar la comida de la semana", "ir al cine con Mariana", "ver el partido con mis primos",
    "ir a correr al parque", "clase de guitarra", "renovar mi credencial de la biblioteca",
    "llevar la laptop a reparar", "comprar un regalo para la boda de mi prima", "ir a la lavandería",
    "arreglar la bicicleta", "cenar con mis amigos de la prepa", "devolver los libros a la biblioteca",
    "recoger la ropa de la tintorería", "ir al tianguis", "ordenar mi escritorio",
    "contestar los mensajes pendientes", "bañar al perro", "ir a la junta de vecinos",
    "comprar material para manualidades",
]
# Dias relativos, no de la semana: un relleno "el domingo" responderia
# consultas vagas como "que tengo los domingos" y romperia las etiquetas.
_DIAS = ["hoy", "mañana", "pasado mañana", "esta semana", "la próxima semana"]
_HORAS = ["7:30", "8:00", "9:00", "10:00", "11:30", "12:00", "13:00", "15:00", "16:30", "17:00", "18:00", "19:30", "20:00"]

_PLANTILLAS = [
    ("Quiero {act} {dia} a las {hora}.", "Anotado: **{act}, {dia} a las {hora}**. ¿Te pongo un recordatorio?"),
    ("Recuérdame {act} {dia}.", "Listo: recordatorio para **{act}** {dia} a las {hora}."),
    ("Otra vez no pude {act}, lo pospongo para {dia}.", "Pasa. Lo movimos a **{dia} a las {hora}**. Hazlo en 15 minutos."),
    ("Ya terminé de {act}.", "¡Bien hecho! Marqué **{act}** como completado."),
    ("¿Cuánto tiempo aparto para {act}?", "Aparta **45 minutos** para {act}. Te sugiero {dia} a las {hora}."),
    ("Se me olvidó {act}.", "No pasa nada. ¿Lo agendo de nuevo para {dia} a las {hora}?"),
    ("Divide en pasos lo de {act}.", "Pasos para {act}:\n1. Preparar lo necesario\n2. Hacerlo {dia} a las {hora}\n3. Revisar que quedó listo"),
    ("Cambia {act} para {dia} a las {hora}.", "Hecho: **{act}** quedó {dia} a las {hora}."),
]


def intercambios_de_relleno(cantidad: int, semilla: int = 2026) -> list[dict]:
    """`cantidad` intercambios distintos y reproducibles, con tema 'relleno'."""
    rng = random.Random(semilla)
    vistos: set[str] = set()
    intercambios = []
    while len(intercambios) < cantidad:
        usuario, asistente = rng.choice(_PLANTILLAS)
        datos = {"act": rng.choice(_ACTIVIDADES), "dia": rng.choice(_DIAS), "hora": rng.choice(_HORAS)}
        texto_usuario = usuario.format(**datos)
        texto_asistente = asistente.format(**datos)
        if (clave := texto_usuario + texto_asistente) in vistos:
            continue
        vistos.add(clave)
        intercambios.append(
            {
                "id": f"rel-{len(intercambios) + 1}",
                "temas": [TEMA_RELLENO],
                "usuario": texto_usuario,
                "asistente": texto_asistente,
            }
        )
    return intercambios


def ampliar_dataset(dataset: dict, relleno: int, semilla: int = 2026) -> dict:
    """Agrega relleno al historial del usuario A (el de las consultas)."""
    if relleno:
        dataset["usuarios"]["a"]["intercambios"] += intercambios_de_relleno(relleno, semilla)
    return dataset


def sembrar_otros_usuarios(
    cliente, coleccion: str, usuarios: int, puntos_por_usuario: int, dimension: int, semilla: int = 2026
) -> int:
    """Puntos con vectores aleatorios (normales, como un embedding) de
    `usuarios` usuarios ficticios, en lotes. Devuelve cuantos inserto."""
    rng = random.Random(semilla)
    lote: list[qmodels.PointStruct] = []
    total = 0
    for _ in range(usuarios):
        user_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        for _ in range(puntos_por_usuario):
            vector = [rng.gauss(0, 1) for _ in range(dimension)]
            lote.append(
                qmodels.PointStruct(
                    id=str(uuid.UUID(int=rng.getrandbits(128), version=4)),
                    vector=vector,
                    payload={"user_id": user_id, "text": "relleno de otro usuario"},
                )
            )
            if len(lote) == 500:
                cliente.upsert(coleccion, points=lote)
                total += len(lote)
                lote = []
    if lote:
        cliente.upsert(coleccion, points=lote)
        total += len(lote)
    return total
