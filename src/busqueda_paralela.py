# ─────────────────────────────────────────────────
# TROY — Búsqueda Multi-Fuente
# Infima Foundation A.C.
#
# Ejecuta 3 variaciones de la query en paralelo
# via Google/Playwright y combina los resultados.
# ─────────────────────────────────────────────────

import asyncio
import sys, os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(__file__))

from busqueda import buscar_web


def _generar_variaciones(query: str) -> list[str]:
    anio = datetime.now().year
    return [
        f"{query} resultado final",
        f"{query} marcador final {anio}",
        f"{query} terminó",
    ]


def _deduplicar(textos: list[str]) -> str:
    """Combina múltiples resultados eliminando líneas duplicadas."""
    vistos = set()
    lineas_unicas = []

    for texto in textos:
        if not texto:
            continue
        for linea in texto.split("\n"):
            linea = linea.strip()
            if len(linea) < 15:
                continue
            # Clave de deduplicación: primeros 80 chars normalizados
            clave = linea.lower()[:80]
            if clave not in vistos:
                vistos.add(clave)
                lineas_unicas.append(linea)

    return "\n".join(lineas_unicas)


async def _buscar_multifuente_async(query: str) -> str:
    variaciones = _generar_variaciones(query)

    async def _una_busqueda(variacion: str, delay: float) -> str:
        # Delay escalonado para evitar rate-limiting de DuckDuckGo
        await asyncio.sleep(delay)
        return await asyncio.to_thread(buscar_web, variacion)

    resultados = await asyncio.gather(
        *[_una_busqueda(v, i * 1.0) for i, v in enumerate(variaciones)],
        return_exceptions=True
    )

    textos = [r for r in resultados if isinstance(r, str) and r.strip()]
    combinado = _deduplicar(textos)
    return combinado[:3000]


def buscar_multifuente(query: str) -> str:
    """Busca en 3 variaciones de la query en paralelo y consolida resultados.

    Usa DuckDuckGo via asyncio.to_thread con delays escalonados.
    Devuelve máximo 3000 caracteres deduplicados.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_buscar_multifuente_async(query))
    finally:
        loop.close()
