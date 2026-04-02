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
        from busqueda import buscar_web
        tools["buscar_web"] = {
            "descripcion": "Busca información actual en internet",
            "ejemplo": "buscar_web('precio Tesla hoy')",
            "parametros": {"query": "texto a buscar"},
            "funcion": lambda p: buscar_web(p["query"])
        }
    except ImportError:
        pass

    try:
        from browser_use import navegar, buscar_resultado_deportivo as _buscar_deportivo_async
        tools["navegar_url"] = {
            "descripcion": "Abre una URL y extrae su contenido",
            "ejemplo": "navegar_url('https://espn.com')",
            "parametros": {"url": "URL a visitar"},
            "funcion": lambda p: navegar(p["url"])
        }
        tools["buscar_resultado_deportivo"] = {
            "descripcion": "Busca resultados de partidos deportivos",
            "ejemplo": "buscar_resultado_deportivo('Mexico vs Belgica 2026')",
            "parametros": {"query": "equipos y fecha"},
            # Usamos _run_async_in_thread con la coroutine directamente para evitar
            # el conflicto de event loop que causa asyncio.run() dentro de un thread
            # que Playwright ya puede haber inicializado con su propio loop.
            "funcion": lambda p: _run_async_in_thread(_buscar_deportivo_async(p["query"]))
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


def _parsear_decision(texto: str) -> dict:
    """Parsea el formato simplificado USAR/PARAMETROS/RESPUESTA del LLM.

    Formatos esperados:
      USAR: nombre_herramienta
      PARAMETROS: {"key": "value"}

      RESPUESTA: texto de respuesta al usuario
    """
    texto = texto.strip()

    # Caso RESPUESTA
    if texto.upper().startswith("RESPUESTA:"):
        return {"respuesta_final": texto[len("RESPUESTA:"):].strip()}

    # Caso USAR + PARAMETROS (puede haber texto extra antes/después)
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
        if "parametros" not in resultado:
            resultado["parametros"] = {}
        return resultado

    # Fallback: tratar todo el texto como respuesta directa
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
- Tienes acceso a internet en tiempo real via buscar_web y buscar_resultado_deportivo.
  Para CUALQUIER pregunta sobre datos actuales, noticias, deportes, precios, recetas,
  personas, eventos, lugares — usa buscar_web primero. NUNCA digas que no tienes acceso
  a internet o información actualizada — siempre puedes buscar.
- Para partidos/scores/marcadores usa SIEMPRE buscar_resultado_deportivo, nunca buscar_web.
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

            mensajes.append({"role": "assistant", "content": texto})
            mensajes.append({
                "role": "user",
                "content": f"Resultado de {herramienta}: {resultado}"
            })
            continue

        # Si llegó aquí sin acción ni respuesta, terminar
        break

    return f"No pude completar la tarea después de {pasos} pasos. El modelo no devolvió una acción ni respuesta final válida."


# ─────────────────────────────────────────────────
# INTERFAZ PÚBLICA
# ─────────────────────────────────────────────────

def procesar(instruccion: str, sesion_id: str = "default",
             callback_pensamiento=None) -> str:
    """Punto de entrada principal del orquestador."""
    # Fast path: solo saludos puros → LLM directo sin turn loop
    # Cualquier pregunta o dato del mundo real pasa por el turn loop con acceso a internet
    if _es_saludo_puro(instruccion):
        return _respuesta_directa(instruccion, sesion_id)
    return turn_loop(instruccion, sesion_id, callback_pensamiento)


def herramientas_disponibles() -> list:
    """Lista las herramientas cargadas."""
    return list(HERRAMIENTAS.keys())