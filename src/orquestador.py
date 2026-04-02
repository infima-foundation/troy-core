# ─────────────────────────────────────────────────
# TROY — Orquestador v1.0
# Infima Foundation A.C.
#
# Implementa tres patrones de Claude Code:
# 1. Tool Registry — catálogo dinámico de herramientas
# 2. Turn Loop — ciclo de razonamiento y ejecución
# 3. Persistent Memory — contexto entre conversaciones
# ─────────────────────────────────────────────────

import sys, os, json, asyncio, traceback
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

PROMPT_SISTEMA = """Eres TROY, un agente personal soberano de Infima Foundation.
Corres completamente en el dispositivo del usuario. Sus datos nunca salen de su control.

Tu personalidad es directa, cálida y eficiente — como un colaborador de confianza.

HERRAMIENTAS DISPONIBLES:
{catalogo}

CONTEXTO DEL USUARIO:
{contexto}

INSTRUCCIONES DE RAZONAMIENTO:
Cuando el usuario te pida algo, analiza si necesitas usar herramientas.

Si necesitas usar una herramienta, responde EXACTAMENTE en este formato JSON:
{{
  "pensamiento": "explica brevemente qué vas a hacer y por qué",
  "accion": "nombre_de_la_herramienta",
  "parametros": {{"param1": "valor1", "param2": "valor2"}}
}}

Si ya tienes toda la información para responder al usuario, responde EXACTAMENTE en este formato JSON:
{{
  "pensamiento": "tengo toda la información necesaria",
  "respuesta_final": "tu respuesta completa al usuario en {idioma}"
}}

REGLAS:
1. Siempre responde en JSON válido, sin texto antes ni después.
2. Usa herramientas solo cuando sean necesarias.
3. Nunca inventes datos — si no sabes algo, dilo.
4. Si una herramienta falla, intenta una alternativa o explica el problema.
5. Máximo {max_pasos} pasos antes de dar una respuesta final.
6. Responde siempre en {idioma}.
7. Para preguntas sobre resultados de partidos, marcadores, scores o quién ganó un juego,
   usa SIEMPRE buscar_resultado_deportivo. NUNCA uses buscar_web para esto.
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

    # Agregar historial de la sesión
    for msg in memoria.historial_sesion[-6:]:
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

        # Limpiar y parsear JSON
        texto_limpio = texto.strip()
        if texto_limpio.startswith("```"):
            texto_limpio = texto_limpio.split("```")[1]
            if texto_limpio.startswith("json"):
                texto_limpio = texto_limpio[4:]
        texto_limpio = texto_limpio.strip()

        try:
            decision = json.loads(texto_limpio)
        except json.JSONDecodeError:
            # Si no es JSON válido, tratar como respuesta final
            return texto.strip()

        pensamiento = decision.get("pensamiento", "")

        # Notificar al usuario qué está pensando
        if callback_pensamiento and pensamiento:
            callback_pensamiento(pensamiento)

        # ¿Tiene respuesta final?
        if "respuesta_final" in decision:
            respuesta = decision["respuesta_final"]
            # Guardar en memoria
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

            # Agregar resultado al contexto para el siguiente turno
            mensajes.append({
                "role": "assistant",
                "content": texto_limpio
            })
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
    """
    Punto de entrada principal del orquestador.
    Reemplaza la lógica de detección de patrones del bot.
    """
    return turn_loop(instruccion, sesion_id, callback_pensamiento)


def herramientas_disponibles() -> list:
    """Lista las herramientas cargadas."""
    return list(HERRAMIENTAS.keys())