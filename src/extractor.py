# ─────────────────────────────────────────────────
# TROY — Extractor de Datos Estructurados
# Infima Foundation A.C.
#
# Extrae datos concretos del texto de búsqueda
# sin pasar por el LLM — determinista y exacto.
# ─────────────────────────────────────────────────

import re


# ── PATRONES ─────────────────────────────────────

# Score: "1-1", "2 - 0", "2:1", "1–0", "2 a 1"
_RE_SCORE = re.compile(
    r'\b(\d{1,2})\s*[-:–]\s*(\d{1,2})\b'
    r'|(?<!\w)(\d{1,2})\s+a\s+(\d{1,2})(?!\w)',
    re.IGNORECASE
)

# Palabras de contexto que indican que hay un resultado cerca
_CONTEXTO_RESULTADO = {
    "empate", "empató", "empataron", "firmaron", "igualaron",
    "quedó", "quedo", "terminó", "termino", "finalizó", "finalizo",
    "resultado", "marcador", "score", "ganó", "gano", "venció", "vencio",
    "derrota", "victoria", "goles",
}

# Palabras que activan el extractor (contexto deportivo en la query)
_PALABRAS_PARTIDO = {
    "vs", "contra", "partido", "juego", "marcador", "resultado",
    "empate", "empató", "ganó", "gano", "perdió", "perdio",
    "score", "final", "amistoso", "liga", "copa", "quedó", "quedo",
}

# Fecha en español: "31 de marzo 2026" o "31 de marzo de 2026"
_RE_FECHA = re.compile(
    r'\b(\d{1,2})\s+de\s+'
    r'(enero|febrero|marzo|abril|mayo|junio|julio|agosto'
    r'|septiembre|octubre|noviembre|diciembre)'
    r'(?:\s+de\s+|\s+)(\d{4})\b',
    re.IGNORECASE
)

# Sede/estadio: "en el Soldier Field", "at Camp Nou", etc.
_RE_VENUE = re.compile(
    r'(?:en\s+el\s+|en\s+la\s+|at\s+the\s+|at\s+)'
    r'([A-ZÁÉÍÓÚ][^,.\n]{2,40})',
    re.IGNORECASE
)


# ── INTERFAZ PÚBLICA ──────────────────────────────

def extraer_datos(texto: str, query: str) -> str | None:
    """Extrae datos concretos del texto de búsqueda sin pasar por el LLM.

    Retorna un string formateado si encuentra el dato con confianza.
    Retorna None si no encuentra nada concluyente — el LLM toma el control.
    """
    return _extraer_marcador(texto, query)


# ── MARCADORES DEPORTIVOS ─────────────────────────

def _extraer_marcador(texto: str, query: str) -> str | None:
    query_lower = query.lower()
    palabras_query = set(query_lower.split())

    # Solo activar en contexto deportivo
    if not (palabras_query & _PALABRAS_PARTIDO or
            re.search(r'\bvs\.?\b', query_lower)):
        return None

    equipos = _extraer_equipos(query_lower)
    lineas = texto.split("\n")

    # Puntuar cada línea que contiene un score
    candidatos = []
    for i, linea in enumerate(lineas):
        m = _RE_SCORE.search(linea)
        if not m:
            continue

        if m.group(1) is not None:
            g1, g2 = int(m.group(1)), int(m.group(2))
        else:
            g1, g2 = int(m.group(3)), int(m.group(4))

        linea_lower = linea.lower()
        pts = sum(1 for e in equipos if e in linea_lower)
        pts += sum(1 for p in _CONTEXTO_RESULTADO if p in linea_lower)

        ventana = "\n".join(lineas[max(0, i-2):i+3]).lower()
        pts += sum(1 for e in equipos if e in ventana) // 2
        pts += sum(1 for p in _CONTEXTO_RESULTADO if p in ventana) // 2

        if pts >= 1:
            candidatos.append((pts, g1, g2, linea.strip(), i))

    if not candidatos:
        return None

    candidatos.sort(key=lambda x: x[0], reverse=True)
    _, g1, g2, mejor_linea, idx = candidatos[0]

    # Determinar tipo de resultado
    tipo = _tipo_resultado(g1, g2, equipos)

    # Intentar extraer fecha del bloque completo
    fecha = _buscar_fecha(texto)

    # Intentar extraer sede de las líneas cercanas
    bloque_cercano = "\n".join(lineas[max(0, idx-3):idx+4])
    sede = _buscar_sede(bloque_cercano)

    # Construir nombre de equipos desde la query
    nombre_partido = _nombre_partido(query_lower, equipos)

    # Armar respuesta formateada
    partes = [f"{nombre_partido}: {g1}-{g2} ({tipo})"]
    if fecha:
        partes.append(fecha)
    if sede:
        partes.append(sede)

    respuesta = " — ".join(partes)
    print(f"[EXTRACTOR] resultado: {respuesta}")
    return respuesta


def _tipo_resultado(g1: int, g2: int, equipos: list[str]) -> str:
    if g1 == g2:
        return "empate"
    return "victoria"


def _buscar_fecha(texto: str) -> str | None:
    m = _RE_FECHA.search(texto)
    if m:
        return f"{m.group(1)} de {m.group(2).lower()} {m.group(3)}"
    return None


def _buscar_sede(texto: str) -> str | None:
    # Buscar nombres conocidos de estadios primero
    conocidos = re.search(
        r'(Soldier Field|Azteca|Camp Nou|Wembley|Maracaná|Santiago Bernabéu'
        r'|Rose Bowl|MetLife|AT&T Stadium)',
        texto, re.IGNORECASE
    )
    if conocidos:
        return conocidos.group(1)
    m = _RE_VENUE.search(texto)
    if m:
        sede = m.group(1).strip().rstrip(",.")
        if len(sede) > 4:
            return sede
    return None


_STOPWORDS_QUERY = {
    "resultado", "partido", "juego", "marcador", "score", "amistoso",
    "quién", "quien", "ganó", "gano", "cómo", "como", "quedó", "quedo",
    "cuánto", "cuanto", "2024", "2025", "2026", "hoy", "ayer", "final",
    "cuanto", "quedo", "termino", "terminó",
}


def _limpiar_palabra(p: str) -> str:
    """Quita signos de puntuación pegados a la palabra."""
    return re.sub(r'^[¿¡\'"()\[\]]+|[?!\'".,()\[\]]+$', '', p)


def _nombre_partido(query: str, equipos: list[str]) -> str:
    vs_match = re.search(r'\bvs\.?\b', query)
    if vs_match:
        antes = query[:vs_match.start()]
        despues = re.sub(r'\d{4}', '', query[vs_match.end():])
        e1 = " ".join(
            _limpiar_palabra(w).capitalize()
            for w in antes.split()
            if _limpiar_palabra(w).lower() not in _STOPWORDS_QUERY
            and len(_limpiar_palabra(w)) >= 3
        ).strip()
        e2 = " ".join(
            _limpiar_palabra(w).capitalize()
            for w in despues.split()
            if _limpiar_palabra(w).lower() not in _STOPWORDS_QUERY
            and len(_limpiar_palabra(w)) >= 3
        ).strip()
        if e1 and e2:
            return f"{e1} vs {e2}"
    if len(equipos) >= 2:
        return f"{equipos[0].capitalize()} vs {equipos[1].capitalize()}"
    return "Partido"


def _extraer_equipos(query: str) -> list[str]:
    return [
        _limpiar_palabra(p) for p in query.split()
        if len(_limpiar_palabra(p)) >= 4
        and _limpiar_palabra(p).lower() not in _STOPWORDS_QUERY
    ]
