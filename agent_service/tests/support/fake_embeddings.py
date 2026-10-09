"""Embeddings deterministas sin red para las pruebas unitarias: bolsa de
palabras con hashing estable (crc32). Textos que comparten palabras quedan
cerca en coseno, suficiente para probar el flujo de indexado/busqueda."""

import math
import re
import unicodedata
import zlib

_STOPWORDS = {
    "a", "al", "con", "de", "del", "el", "en", "es", "la", "las", "lo", "los", "me", "mi",
    "mis", "para", "por", "que", "se", "su", "te", "tu", "un", "una", "y", "yo", "era",
}


def _palabras(texto: str) -> list[str]:
    sin_acentos = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return [p for p in re.findall(r"\w+", sin_acentos) if p not in _STOPWORDS]


class HashingEmbeddings:
    def __init__(self, size: int = 256) -> None:
        self.size = size

    def embed_query(self, texto: str) -> list[float]:
        vector = [0.0] * self.size
        for palabra in _palabras(texto):
            vector[zlib.crc32(palabra.encode()) % self.size] += 1.0
        norma = math.sqrt(sum(v * v for v in vector))
        if norma == 0:
            vector[0], norma = 1.0, 1.0  # Qdrant no acepta el vector cero en coseno
        return [v / norma for v in vector]

    async def aembed_query(self, texto: str) -> list[float]:
        return self.embed_query(texto)


class SinEmbeddings:
    """Default de las pruebas: cualquier embedding no pedido explicitamente
    falla en vez de llamar a Gemini."""

    async def aembed_query(self, texto: str) -> list[float]:
        raise RuntimeError("Las pruebas no deben llamar a Gemini: usa fake_embeddings u ollama_embeddings")
