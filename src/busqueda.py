# ─────────────────────────────────────────────────
# TROY — Módulo de Búsqueda Web
# Infima Foundation A.C.
# Usa DuckDuckGo — sin API key, sin tracking
# ─────────────────────────────────────────────────

from ddgs import DDGS

def buscar_web(query: str, max_resultados: int = 3) -> str:
    """
    Busca en DuckDuckGo y retorna un resumen
    de los resultados más relevantes.
    """
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(
                query,
                max_results=max_resultados
            ))

        if not resultados:
            return ""

        texto = ""
        for r in resultados:
            titulo = r.get("title", "")
            cuerpo = r.get("body", "")
            url    = r.get("href", "")
            texto += f"\n[{titulo}]\n{cuerpo}\nFuente: {url}\n"

        return texto.strip()

    except Exception as e:
        print(f"Error en búsqueda web: {e}")
        return ""


def necesita_busqueda(texto: str) -> bool:
    """
    Detecta si el mensaje del usuario requiere
    información actual de internet.
    """
    señales = [
        "busca", "buscar", "search", "encuentra",
        "qué pasó", "qué paso", "noticias", "news",
        "hoy", "today", "ahora", "now", "actual",
        "precio", "price", "cotización", "dólar",
        "clima", "weather", "tiempo en",
        "quién es", "quien es", "who is",
        "cuándo", "cuando", "when",
        "último", "ultimo", "latest", "reciente",
    ]
    texto_lower = texto.lower()
    return any(s in texto_lower for s in señales)