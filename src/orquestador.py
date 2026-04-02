# ─────────────────────────────────────────────────
# TROY — Orquestador v1.0
# Infima Foundation A.C.
#
# Implementa tres patrones de Claude Code:
# 1. Tool Registry — catálogo dinámico de herramientas
# 2. Turn Loop — ciclo de razonamiento y ejecución
# 3. Persistent Memory — contexto entre conversaciones
# ─────────────────────────────────────────────────

import sys, os, json, asyncio, traceback, re
from datetime import datetime
from typing import TypedDict, Annotated
import operator
sys.path.insert(0, os.path.dirname(__file__))

from ollama import Client
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

ollama_client = Client(host="http://localhost:11434")
MODELO = "llama3.2"
MAX_PASOS = 6  # Máximo de herramientas por tarea

# ─────────────────────────────────────────────────
# PATRÓN 1 — TOOL REGISTRY
# Catálogo de herramientas disponibles.
# El LLM lee esto para decidir qué usar.
# ─────────────────────────────────────────────────

def _extraer_json(texto: str) -> str:
    """Extrae el primer objeto JSON del texto del LLM.

    Cubre los casos que produce llama3.2:
      1. ```json ... ```  o  ``` ... ```
      2. JSON limpio desde el inicio
      3. JSON embebido con texto antes y/o después
    """
    texto = texto.strip()

    # Caso 1: bloque de código con backticks
    if "```" in texto:
        for bloque in texto.split("```"):
            bloque = bloque.strip()
            if bloque.startswith("json"):
                bloque = bloque[4:].strip()
            if bloque.startswith("{"):
                return bloque

    # Caso 2: JSON directo sin preámbulo
    if texto.startswith("{"):
        return texto

    # Caso 3: JSON embebido — extraer desde el primer { hasta el último }
    match = re.search(r'\{.*\}', texto, re.DOTALL)
    if match:
        return match.group(0)

    return texto


def _run_async_in_thread(coro):
    """Ejecuta una coroutine en un event loop fresco.
    Seguro desde cualquier thread — evita conflictos con loops existentes."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _importar_herramientas():
    """Importa herramientas disponibles de forma lazy."""
    tools = {}

    try:
        from browser_use import navegar, buscar_reciente as _buscar_reciente_async
        tools["buscar_reciente"] = {
            "descripcion": (
                "Busca información actual en internet via Google — noticias, resultados, "
                "precios, eventos de hoy o esta semana. "
                "Úsala cuando la pregunta implique datos recientes o del mundo actual."
            ),
            "ejemplo": "buscar_reciente('resultado Mexico vs Belgica 2026')",
            "parametros": {"query": "texto a buscar"},
            "funcion": lambda p: _run_async_in_thread(_buscar_reciente_async(p["query"]))
        }
        tools["navegar_url"] = {
            "descripcion": "Abre una URL y extrae su contenido",
            "ejemplo": "navegar_url('https://espn.com')",
            "parametros": {"url": "URL a visitar"},
            "funcion": lambda p: navegar(p["url"])
        }
    except ImportError:
        pass

    try:
        from busqueda import buscar_web
        tools["buscar_info"] = {
            "descripcion": (
                "Busca información general via DuckDuckGo — recetas, conceptos, historia, "
                "definiciones, cómo hacer algo. "
                "Úsala cuando no se necesiten datos de hoy."
            ),
            "ejemplo": "buscar_info('receta de pozole rojo')",
            "parametros": {"query": "texto a buscar"},
            "funcion": lambda p: buscar_web(p["query"])
        }
    except ImportError:
        pass

    try:
        from email_agent import obtener_correos, mandar_correo, buscar_correos
        tools["leer_correos"] = {
            "descripcion": "Lee correos no leídos de Gmail",
            "ejemplo": "leer_correos(5)",
            "parametros": {"limite": "número de correos (1-10)"},
            "funcion": lambda p: obtener_correos(
                limite=int(p.get("limite", 5))
            )
        }
        tools["mandar_correo"] = {
            "descripcion": "Manda un correo desde Gmail",
            "ejemplo": "mandar_correo('juan@gmail.com', 'Asunto', 'Cuerpo')",
            "parametros": {
                "destinatario": "email del destinatario",
                "asunto": "asunto del correo",
                "cuerpo": "contenido del correo"
            },
            "funcion": lambda p: mandar_correo(
                p["destinatario"], p["asunto"], p["cuerpo"]
            )
        }
        tools["buscar_correos"] = {
            "descripcion": "Busca correos por asunto o remitente",
            "ejemplo": "buscar_correos('factura')",
            "parametros": {"query": "término a buscar"},
            "funcion": lambda p: buscar_correos(p["query"])
        }
    except ImportError:
        pass

    try:
        from calendario import (obtener_eventos, crear_evento,
                                borrar_evento, crear_tarea, obtener_tareas)
        tools["leer_calendario"] = {
            "descripcion": "Lee eventos del calendario de los próximos N días",
            "ejemplo": "leer_calendario(7)",
            "parametros": {"dias": "número de días a consultar"},
            "funcion": lambda p: obtener_eventos(dias=int(p.get("dias", 7)))
        }
        tools["crear_evento"] = {
            "descripcion": "Crea un evento en Google Calendar",
            "ejemplo": "crear_evento('Reunión', '2026-04-10', '10:00', 1)",
            "parametros": {
                "titulo": "nombre del evento",
                "fecha": "YYYY-MM-DD",
                "hora": "HH:MM",
                "duracion": "horas de duración"
            },
            "funcion": lambda p: crear_evento(
                p["titulo"], p["fecha"],
                p.get("hora", "09:00"),
                int(p.get("duracion", 1))
            )
        }
        tools["borrar_evento"] = {
            "descripcion": "Borra un evento del calendario por nombre",
            "ejemplo": "borrar_evento('Reunión de equipo')",
            "parametros": {"titulo": "nombre del evento a borrar"},
            "funcion": lambda p: borrar_evento(p["titulo"])
        }
        tools["crear_tarea"] = {
            "descripcion": "Crea una tarea en Google Tasks",
            "ejemplo": "crear_tarea('Comprar leche', 'En el super', '2026-04-10')",
            "parametros": {
                "titulo": "nombre de la tarea",
                "descripcion": "descripción opcional",
                "fecha": "fecha límite YYYY-MM-DD opcional"
            },
            "funcion": lambda p: crear_tarea(
                p["titulo"],
                p.get("descripcion", ""),
                p.get("fecha")
            )
        }
        tools["leer_tareas"] = {
            "descripcion": "Lista todas las tareas pendientes",
            "ejemplo": "leer_tareas()",
            "parametros": {},
            "funcion": lambda p: obtener_tareas()
        }
    except ImportError:
        pass

    try:
        from telegram_usuario import mandar_mensaje
        import asyncio
        tools["mandar_mensaje_telegram"] = {
            "descripcion": "Manda un mensaje de Telegram desde la cuenta del usuario",
            "ejemplo": "mandar_mensaje_telegram('8703220225', 'Hola!')",
            "parametros": {
                "destinatario": "username o ID de Telegram",
                "mensaje": "texto del mensaje"
            },
            "funcion": lambda p: asyncio.run(
                mandar_mensaje(p["destinatario"], p["mensaje"])
            )
        }
    except ImportError:
        pass

    try:
        from rag import buscar_contexto
        tools["buscar_documentos"] = {
            "descripcion": "Busca información en los documentos personales del usuario",
            "ejemplo": "buscar_documentos('presupuesto 2026')",
            "parametros": {"query": "qué buscar en los documentos"},
            "funcion": lambda p: buscar_contexto(p["query"])
        }
    except ImportError:
        pass

    return tools

HERRAMIENTAS = _importar_herramientas()


def catalogo_para_llm() -> str:
    """Genera el catálogo de herramientas en formato legible para el LLM."""
    catalogo = []
    for nombre, info in HERRAMIENTAS.items():
        params = ", ".join(
            f'"{k}": {v}' for k, v in info["parametros"].items()
        )
        catalogo.append(
            f'- {nombre}: {info["descripcion"]}\n'
            f'  Parámetros: {{{params}}}\n'
            f'  Ejemplo: {info["ejemplo"]}'
        )
    return "\n".join(catalogo)


# ─────────────────────────────────────────────────
# PATRÓN 3 — PERSISTENT MEMORY
# Tres capas de memoria para el agente.
# ─────────────────────────────────────────────────

class Memoria:
    """Memoria persistente del agente en tres capas."""

    def __init__(self, sesion_id: str):
        self.sesion_id = sesion_id
        self._cargar()

    def _cargar(self):
        try:
            from memoria import obtener_historial
            self.historial_sesion = obtener_historial(
                self.sesion_id, limite=10
            )
        except Exception:
            self.historial_sesion = []

        self.perfil_usuario = {
            "nombre": "Mauricio",
            "idioma": "Spanish",
            "zona_horaria": "America/Mexico_City"
        }
        self.acciones_recientes = []

    def registrar_accion(self, herramienta: str, parametros: dict,
                         resultado: str, exitosa: bool):
        self.acciones_recientes.append({
            "herramienta": herramienta,
            "parametros": parametros,
            "resultado": resultado[:200],
            "exitosa": exitosa,
            "timestamp": datetime.now().isoformat()
        })

    def contexto_para_llm(self) -> str:
        ctx = f"Usuario: {self.perfil_usuario['nombre']}\n"
        ctx += f"Idioma: {self.perfil_usuario['idioma']}\n"
        ctx += f"Fecha/hora actual: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        if self.acciones_recientes:
            ctx += "\nAcciones ejecutadas en esta tarea:\n"
            for a in self.acciones_recientes[-3:]:
                estado = "✅" if a["exitosa"] else "❌"
                ctx += f"  {estado} {a['herramienta']}: {a['resultado'][:100]}\n"
        return ctx


# ─────────────────────────────────────────────────
# PATRÓN 2 — TURN LOOP
# El ciclo de razonamiento y ejecución.
# ─────────────────────────────────────────────────

# Saludos puros — los únicos que van por fast path sin turn loop.
# Todo lo demás (preguntas, peticiones, datos del mundo) pasa por el turn loop
# para tener acceso a buscar_web y herramientas.
_SALUDOS_PUROS = {
    "hola", "hi", "hello", "hey", "buenas", "buenos días", "buenas tardes",
    "buenas noches", "good morning", "good afternoon", "good evening",
    "gracias", "thank you", "thanks", "de nada", "ok", "okey", "okay",
    "entendido", "perfecto", "listo", "dale", "bien", "genial", "adiós",
    "bye", "hasta luego", "chao", "nos vemos", "qué tal", "cómo estás",
    "how are you", "qué onda",
}


def _es_saludo_puro(texto: str) -> bool:
    """True solo si el texto completo normalizado es un saludo reconocido."""
    normalizado = texto.strip().lower().rstrip("!?,.")
    return normalizado in _SALUDOS_PUROS


# Indicadores de actualidad — activan buscar_reciente (Google/Playwright)
_PALABRAS_RECIENTE = {
    "hoy", "ayer", "ahora", "2024", "2025", "2026",
    "reciente", "último", "ultima", "últimos", "ultimos", "latest",
    "resultado", "partido", "score", "marcador", "ganó", "gano",
    "perdió", "perdio", "empató", "empato", "juego", "liga", "copa", "gol",
    "noticia", "noticias", "news",
    "precio", "cotización", "cotizacion", "dólar", "dollar", "bitcoin", "euro",
    "clima", "temperatura", "pronóstico", "pronostico", "weather",
    "today", "yesterday",
}
# Frases de actualidad (multi-palabra)
_FRASES_RECIENTE = [
    "qué pasó", "que paso", "quién ganó", "quien gano",
    "cómo quedó", "como quedo", "esta semana", "este año", "este mes",
    "qué hay de", "que hay de", "cómo va", "como va",
]

# Indicadores de conocimiento general — activan buscar_info (DuckDuckGo)
_PALABRAS_INFO = {
    "receta", "ingredientes", "cocinar", "preparar",
    "define", "definición", "definicion", "significado", "significa",
    "historia", "origen", "etymology",
    "how", "meaning",
}
# Frases de conocimiento general (multi-palabra)
_FRASES_INFO = [
    "qué es", "que es", "what is", "cómo se hace", "como se hace",
    "cómo hacer", "como hacer", "cómo funciona", "como funciona",
    "quién fue", "quien fue", "cuál es", "cual es",
]


def _decidir_herramienta(texto: str):
    """Decide qué herramienta de búsqueda usar basándose en keywords.

    Retorna ('buscar_reciente', query), ('buscar_info', query), o None.
    buscar_reciente tiene prioridad sobre buscar_info cuando hay señales de actualidad.
    """
    t = texto.lower()
    palabras = set(t.split())

    # Actualidad tiene prioridad
    if palabras & _PALABRAS_RECIENTE or any(f in t for f in _FRASES_RECIENTE):
        return ("buscar_reciente", texto)

    if palabras & _PALABRAS_INFO or any(f in t for f in _FRASES_INFO):
        return ("buscar_info", texto)

    return None


def _contiene_formato_interno(texto: str) -> bool:
    """True si el texto contiene el formato interno del agente (nunca debe llegar al usuario)."""
    t = texto.upper()
    return "USAR:" in t or "PARAMETROS:" in t


def _parsear_decision(texto: str) -> dict:
    """Parsea la respuesta del LLM. Soporta tres formatos:

      1. Formato estructurado (preferido):
           USAR: nombre_herramienta
           PARAMETROS: {"key": "value"}
           RESPUESTA: texto al usuario

      2. Llamada a función en texto plano (fallback):
           buscar_resultado_deportivo("Mexico vs Belgica 2026")

      3. Texto libre → respuesta directa al usuario.

    INVARIANTE: si el texto contiene 'USAR:' o 'PARAMETROS:', nunca
    se devuelve como respuesta_final — siempre se trata como acción.
    """
    texto = texto.strip()

    # Caso RESPUESTA — solo si el contenido no tiene formato interno
    if texto.upper().startswith("RESPUESTA:"):
        respuesta = texto[len("RESPUESTA:"):].strip()
        if _contiene_formato_interno(respuesta):
            # El LLM metió una acción dentro de RESPUESTA: — re-parsear
            return _parsear_decision(respuesta)
        return {"respuesta_final": respuesta}

    # Caso USAR + PARAMETROS — buscar en líneas individuales
    resultado = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.upper().startswith("USAR:"):
            resultado["accion"] = linea[5:].strip()
        elif linea.upper().startswith("PARAMETROS:"):
            params_str = linea[11:].strip()
            try:
                resultado["parametros"] = json.loads(params_str)
            except json.JSONDecodeError:
                resultado["parametros"] = {}

    if "accion" in resultado:
        resultado.setdefault("parametros", {})
        return resultado

    # USAR: embebido en medio de texto (no al inicio de línea)
    usar_match = re.search(r'USAR:\s*(\w+)', texto, re.IGNORECASE)
    if usar_match:
        nombre = usar_match.group(1)
        if nombre in HERRAMIENTAS:
            params = {}
            param_match = re.search(r'PARAMETROS:\s*(\{[^}]+\})', texto, re.IGNORECASE | re.DOTALL)
            if param_match:
                try:
                    params = json.loads(param_match.group(1))
                except json.JSONDecodeError:
                    pass
            return {"accion": nombre, "parametros": params}

    # Llamada a función en texto plano — nombre_herramienta("arg")
    fn_match = re.search(r'\b(\w+)\s*\(\s*([^)]*)\s*\)', texto)
    if fn_match:
        nombre = fn_match.group(1)
        if nombre in HERRAMIENTAS:
            args_raw = fn_match.group(2).strip()
            arg_match = re.search(r'["\'](.+?)["\']', args_raw)
            arg_val = arg_match.group(1) if arg_match else args_raw
            primer_param = next(iter(HERRAMIENTAS[nombre]["parametros"]), "query")
            return {"accion": nombre, "parametros": {primer_param: arg_val}}

    # Guardia final: si el texto libre contiene formato interno, no mandarlo al usuario
    if _contiene_formato_interno(texto):
        print(f"[TROY] formato interno detectado en fallback — descartando: {repr(texto[:120])}")
        return {}  # ni acción ni respuesta → turn loop usará ultimo_resultado

    return {"respuesta_final": texto}


PROMPT_SISTEMA = """Eres TROY, agente personal de Infima Foundation. Corres 100% local.
Tu personalidad: directa, cálida, eficiente.

HERRAMIENTAS:
{catalogo}

CONTEXTO:
{contexto}

INSTRUCCIONES:
Si necesitas una herramienta, responde exactamente así (dos líneas):
USAR: nombre_herramienta
PARAMETROS: {{"param1": "valor1"}}

Si ya puedes responder, responde exactamente así (una línea):
RESPUESTA: tu respuesta completa en {idioma}

REGLAS:
- Tienes acceso a internet en tiempo real. NUNCA digas que no tienes información actualizada.
- Para información del mundo actual (noticias, resultados, precios, eventos recientes): usa buscar_reciente.
- Para información general que no cambia (recetas, conceptos, historia): usa buscar_info.
- Nunca pidas permiso antes de buscar — busca de inmediato.
- Nunca inventes datos. Si no encuentras algo con las herramientas, dilo.
- Si una herramienta falla, intenta una alternativa o explica el problema.
- Máximo {max_pasos} usos de herramientas.
- Responde siempre en {idioma}.
"""

def detectar_idioma(texto: str) -> str:
    try:
        import langdetect
        codigo = langdetect.detect(texto)
        return "Spanish" if codigo == "es" else "English"
    except Exception:
        return "Spanish"

def ejecutar_herramienta(nombre: str, parametros: dict,
                          memoria: Memoria) -> tuple[str, bool]:
    """Ejecuta una herramienta del registry y registra el resultado."""
    if nombre not in HERRAMIENTAS:
        return f"Herramienta '{nombre}' no encontrada.", False

    try:
        resultado = HERRAMIENTAS[nombre]["funcion"](parametros)
        if isinstance(resultado, list):
            resultado_str = json.dumps(resultado, ensure_ascii=False)[:500]
        elif isinstance(resultado, bool):
            resultado_str = "exitoso" if resultado else "falló"
        else:
            resultado_str = str(resultado)[:500]

        memoria.registrar_accion(nombre, parametros, resultado_str, True)
        return resultado_str, True

    except Exception as e:
        error = f"Error: {str(e)}"
        memoria.registrar_accion(nombre, parametros, error, False)
        return error, False


def _respuesta_directa(instruccion: str, sesion_id: str) -> str:
    """LLM directo sin turn loop — para saludos y preguntas simples."""
    idioma = detectar_idioma(instruccion)
    memoria = Memoria(sesion_id)

    mensajes = [{"role": "system", "content": (
        f"Eres TROY, un agente personal de Infima Foundation. "
        f"Responde de forma natural y directa en {idioma}. "
        f"Usuario: {memoria.perfil_usuario['nombre']}."
    )}]
    for msg in memoria.historial_sesion[-4:]:
        mensajes.append(msg)
    mensajes.append({"role": "user", "content": instruccion})

    resp = ollama_client.chat(model=MODELO, messages=mensajes,
                              options={"num_predict": 150, "temperature": 0.7})
    texto = resp.message.content if hasattr(resp, "message") else resp["message"]["content"]

    try:
        from memoria import guardar_mensaje
        guardar_mensaje(sesion_id, "user", instruccion)
        guardar_mensaje(sesion_id, "assistant", texto)
    except Exception:
        pass

    return texto


def _ejecutar_y_redactar(instruccion: str, sesion_id: str,
                          herramienta: str, query: str) -> str:
    """Ejecuta una herramienta directamente y usa el LLM solo para redactar la respuesta.

    El LLM no decide herramientas — solo convierte el resultado en lenguaje natural.
    """
    idioma = detectar_idioma(instruccion)
    memoria = Memoria(sesion_id)

    resultado, exitosa = ejecutar_herramienta(herramienta, {"query": query}, memoria)

    if not exitosa or not resultado.strip():
        # Si la herramienta falló, responder directamente sin mencionar la búsqueda
        return _respuesta_directa(instruccion, sesion_id)

    mensajes = [
        {"role": "system", "content": (
            f"Eres TROY, agente personal de Infima Foundation. "
            f"Responde en {idioma} de forma directa y concisa. "
            f"Usa los resultados de búsqueda para responder la pregunta. "
            f"No menciones que hiciste una búsqueda ni cites fuentes a menos que sea relevante."
        )},
        {"role": "user", "content": (
            f"Pregunta: {instruccion}\n\n"
            f"Resultados:\n{resultado}"
        )}
    ]

    resp = ollama_client.chat(model=MODELO, messages=mensajes,
                              options={"num_predict": 400, "temperature": 0.3})
    texto = resp.message.content if hasattr(resp, "message") else resp["message"]["content"]

    try:
        from memoria import guardar_mensaje
        guardar_mensaje(sesion_id, "user", instruccion)
        guardar_mensaje(sesion_id, "assistant", texto)
    except Exception:
        pass

    return texto


def turn_loop(instruccion: str, sesion_id: str,
              callback_pensamiento=None) -> str:
    """
    El ciclo principal del agente.

    callback_pensamiento: función opcional que recibe el pensamiento
    del LLM en tiempo real (para mostrar al usuario qué está haciendo).
    """
    try:
        return _turn_loop_interno(instruccion, sesion_id, callback_pensamiento)
    except Exception as e:
        traceback.print_exc()
        return f"Error en el orquestador: {type(e).__name__}: {e}"


def _turn_loop_interno(instruccion: str, sesion_id: str,
                       callback_pensamiento=None) -> str:
    idioma = detectar_idioma(instruccion)
    memoria = Memoria(sesion_id)

    mensajes = [
        {
            "role": "system",
            "content": PROMPT_SISTEMA.format(
                catalogo=catalogo_para_llm(),
                contexto=memoria.contexto_para_llm(),
                idioma=idioma,
                max_pasos=MAX_PASOS
            )
        }
    ]

    # Historial limitado a 4 mensajes para no contaminar el contexto
    for msg in memoria.historial_sesion[-4:]:
        mensajes.append(msg)

    mensajes.append({"role": "user", "content": instruccion})

    pasos = 0
    ultimo_resultado = None  # último resultado de herramienta ejecutada

    while pasos < MAX_PASOS:
        pasos += 1

        resp = ollama_client.chat(
            model=MODELO,
            messages=mensajes,
            options={"num_predict": 300, "temperature": 0.1}
        )

        texto = resp.message.content if hasattr(resp, "message") \
            else resp["message"]["content"]

        print(f"[TROY paso {pasos}] raw: {repr(texto)}")

        decision = _parsear_decision(texto)

        # ¿Tiene respuesta final?
        if "respuesta_final" in decision:
            respuesta = decision["respuesta_final"]
            try:
                from memoria import guardar_mensaje
                guardar_mensaje(sesion_id, "user", instruccion)
                guardar_mensaje(sesion_id, "assistant", respuesta)
            except Exception:
                pass
            return respuesta

        # ¿Quiere usar una herramienta?
        if "accion" in decision:
            herramienta = decision["accion"]
            parametros = decision.get("parametros", {})

            resultado, exitosa = ejecutar_herramienta(
                herramienta, parametros, memoria
            )
            ultimo_resultado = resultado

            mensajes.append({"role": "assistant", "content": texto})
            mensajes.append({
                "role": "user",
                "content": f"Resultado de {herramienta}: {resultado}"
            })
            continue

        # El LLM no produjo ni acción ni respuesta estructurada.
        # Si acabamos de ejecutar una herramienta, devolver su resultado directamente.
        if ultimo_resultado is not None:
            print(f"[TROY paso {pasos}] LLM no produjo RESPUESTA tras herramienta — usando resultado directo")
            try:
                from memoria import guardar_mensaje
                guardar_mensaje(sesion_id, "user", instruccion)
                guardar_mensaje(sesion_id, "assistant", ultimo_resultado)
            except Exception:
                pass
            return ultimo_resultado

        break

    return f"No pude completar la tarea después de {pasos} pasos. El modelo no devolvió una acción ni respuesta final válida."


# ─────────────────────────────────────────────────
# INTERFAZ PÚBLICA
# ─────────────────────────────────────────────────

def procesar(instruccion: str, sesion_id: str = "default",
             callback_pensamiento=None) -> str:
    """Punto de entrada principal del orquestador.

    Flujo de tres ramas:
    1. Saludo puro → LLM directo (sin herramientas, sin formato)
    2. Búsqueda detectada por keywords → ejecutar herramienta + LLM redacta
    3. Tarea compleja (calendario, email, Telegram) → turn loop
    """
    if _es_saludo_puro(instruccion):
        return _respuesta_directa(instruccion, sesion_id)

    decision = _decidir_herramienta(instruccion)
    if decision:
        herramienta, query = decision
        print(f"[TROY] routing automático → {herramienta}: {repr(query[:60])}")
        return _ejecutar_y_redactar(instruccion, sesion_id, herramienta, query)

    return turn_loop(instruccion, sesion_id, callback_pensamiento)


def herramientas_disponibles() -> list:
    """Lista las herramientas cargadas."""
    return list(HERRAMIENTAS.keys())