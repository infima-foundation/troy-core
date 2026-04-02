# ─────────────────────────────────────────────────
# TROY — Extractor de Datos Estructurados
# Infima Foundation A.C.
#
# Extrae datos concretos del texto de búsqueda
# sin pasar por el LLM — directo y determinista.
# ─────────────────────────────────────────────────

import re


def extraer_datos(texto: str, query: str) -> str | None:
    """Intenta extraer datos concretos del texto de búsqueda.

    Si encuentra el dato directamente (marcador, precio, etc.),
    retorna un string conciso listo para formatear.
    Si no encuentra nada concluyente, retorna None y el LLM toma el control.
    """
    resultado = _extraer_marcador(texto, query)
    if resultado:
        return resultado
    return None


# ── MARCADORES DEPORTIVOS ─────────────────────────

# Patrones de score: "2-1", "2 - 1", "2:1", "(2-1)", "2 a 1"
_RE_SCORE = re.compile(
    r'\b(\d{1,2})\s*[-:–]\s*(\d{1,2})\b'
    r'|(\d{1,2})\s+a\s+(\d{1,2})\b',
    re.IGNORECASE
)

# Palabras que indican contexto deportivo
_PALABRAS_PARTIDO = {
    "vs", "contra", "partido", "juego", "marcador", "resultado",
    "empate", "empató", "ganó", "gano", "perdió", "perdio",
    "goles", "score", "final", "amistoso", "liga", "copa",
}


def _extraer_marcador(texto: str, query: str) -> str | None:
    """Busca el marcador final en el texto de búsqueda.

    Retorna una línea como 'México 1 - 1 Bélgica' si lo encuentra,
    None si no hay marcador concluyente.
    """
    query_lower = query.lower()
    palabras_query = set(query_lower.split())

    # Solo activar si la query tiene contexto deportivo
    if not (palabras_query & _PALABRAS_PARTIDO or
            re.search(r'\bvs\.?\b|\bvs\b', query_lower)):
        return None

    # Buscar líneas que contengan un score y términos de la query
    equipos = _extraer_equipos(query_lower)
    lineas_con_score = []

    for linea in texto.split("\n"):
        if not _RE_SCORE.search(linea):
            continue
        linea_lower = linea.lower()
        # Priorizar líneas que mencionan ambos equipos o palabras del partido
        relevancia = sum(1 for e in equipos if e in linea_lower)
        relevancia += sum(1 for p in _PALABRAS_PARTIDO if p in linea_lower)
        if relevancia >= 1:
            lineas_con_score.append((relevancia, linea.strip()))

    if not lineas_con_score:
        return None

    # Tomar la línea con mayor relevancia
    lineas_con_score.sort(key=lambda x: x[0], reverse=True)
    mejor_linea = lineas_con_score[0][1]

    # Limpiar y acortar
    mejor_linea = mejor_linea[:300].strip()
    print(f"[EXTRACTOR] Marcador detectado: {repr(mejor_linea[:120])}")
    return mejor_linea


def _extraer_equipos(query: str) -> list[str]:
    """Extrae nombres de equipos de la query (palabras de 4+ letras, no stopwords)."""
    stopwords = {
        "resultado", "partido", "juego", "marcador", "score",
        "quién", "quien", "ganó", "gano", "cómo", "como",
        "quedó", "quedo", "2024", "2025", "2026", "hoy", "ayer",
    }
    palabras = [
        p for p in query.split()
        if len(p) >= 4 and p not in stopwords
    ]
    return palabras
