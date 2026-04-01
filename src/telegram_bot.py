# ─────────────────────────────────────────────────
# TROY — Conector de Telegram v0.4
# Infima Foundation A.C.
# Con RAG + Búsqueda Web + Mensajería + Calendario
# ─────────────────────────────────────────────────

import sys, os, re, asyncio
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from memoria import guardar_mensaje, obtener_historial
from rag import buscar_contexto
from busqueda import buscar_web, necesita_busqueda
from telegram_usuario import mandar_mensaje
from calendario import obtener_eventos, crear_evento, formatear_eventos
from ollama import Client
import langdetect

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

ollama_client = Client(host='http://localhost:11434')
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MODELO = "llama3.2"

def detectar_idioma(texto: str) -> str:
    try:
        codigo = langdetect.detect(texto)
        return "Spanish" if codigo == "es" else "English"
    except:
        return "English"

def detectar_envio_mensaje(texto: str):
    patrones = [
        r"mándale?\s+a\s+(@?[\w\d]+)\s+que\s+(.+)",
        r"mandal[ea]\s+a\s+(@?[\w\d]+)\s+que\s+(.+)",
        r"envíale?\s+a\s+(@?[\w\d]+)\s+que\s+(.+)",
        r"dile\s+a\s+(@?[\w\d]+)\s+que\s+(.+)",
        r"manda\s+mensaje\s+a\s+(@?[\w\d]+)\s+(?:que\s+)?(.+)",
        r"send\s+(?:a\s+message\s+to\s+)?(@?[\w\d]+)\s+(?:that\s+|saying\s+)?(.+)",
        r"message\s+(@?[\w\d]+)\s+(?:that\s+|saying\s+)?(.+)",
    ]
    texto_lower = texto.lower().strip()
    for patron in patrones:
        match = re.search(patron, texto_lower)
        if match:
            destinatario = match.group(1)
            mensaje = match.group(2)
            if destinatario.isdigit():
                return int(destinatario), mensaje
            if not destinatario.startswith("@"):
                destinatario = "@" + destinatario
            return destinatario, mensaje
    return None

def detectar_consulta_calendario(texto: str) -> str:
    texto_lower = texto.lower()
    señales_creacion = [
        "agrega", "añade", "crea un evento", "programa",
        "pon en mi calendario", "add to calendar",
        "create event", "schedule a meeting", "nueva cita",
        "nuevo evento", "crea evento", "crea un"
    ]
    señales_consulta = [
        "agenda", "calendario", "calendar", "eventos",
        "qué tengo", "que tengo", "what do i have",
        "citas", "reuniones", "meetings", "schedule",
        "esta semana", "this week", "hoy", "today",
        "mañana", "tomorrow", "próximos", "upcoming"
    ]
    if any(s in texto_lower for s in señales_creacion):
        return "crear"
    elif any(s in texto_lower for s in señales_consulta):
        return "consultar"
    return None

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    sesion_id = str(update.effective_user.id)
    idioma = detectar_idioma(texto_usuario)

    guardar_mensaje(sesion_id, "user", texto_usuario)

    # Detectar si quiere mandar un mensaje
    envio = detectar_envio_mensaje(texto_usuario)
    if envio:
        destinatario, mensaje_a_enviar = envio
        await update.message.reply_text(f"📤 Mandando mensaje a {destinatario}...")
        exito = await mandar_mensaje(destinatario, mensaje_a_enviar)
        if exito:
            respuesta = f"✅ Mensaje enviado a {destinatario}: '{mensaje_a_enviar}'"
        else:
            respuesta = f"❌ No pude mandar el mensaje a {destinatario}."
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    # Detectar consulta de calendario
    accion_calendario = detectar_consulta_calendario(texto_usuario)
    if accion_calendario == "consultar":
        await update.message.reply_text("📅 Revisando tu calendario...")
        eventos = obtener_eventos(dias=7)
        respuesta = formatear_eventos(eventos, idioma)
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion_calendario == "crear":
        await update.message.reply_text("📅 Procesando el evento...")

        mensajes_extraccion = [
            {
                "role": "system",
                "content": (
                    f"Today is {datetime.now().strftime('%Y-%m-%d')}. "
                    "Extract event info from the message. "
                    "Reply ONLY in this exact format with no extra text:\n"
                    "TITULO: title here\n"
                    "FECHA: YYYY-MM-DD\n"
                    "HORA: HH:MM\n"
                    "DURACION: 1"
                )
            },
            {"role": "user", "content": texto_usuario}
        ]

        try:
            resp = ollama_client.chat(
                model=MODELO,
                messages=mensajes_extraccion,
                options={"num_predict": 50}
            )
            texto_ext = resp.message.content if hasattr(resp, "message") else resp["message"]["content"]

            lineas = {}
            for linea in texto_ext.strip().split("\n"):
                if ":" in linea:
                    clave, valor = linea.split(":", 1)
                    lineas[clave.strip().upper()] = valor.strip()

            titulo   = lineas.get("TITULO", "Nuevo evento")
            fecha    = lineas.get("FECHA", datetime.now().strftime("%Y-%m-%d"))
            hora     = lineas.get("HORA", "09:00")
            duracion = int(lineas.get("DURACION", "1"))

            exito = crear_evento(titulo, fecha, hora, duracion)

            if exito:
                respuesta = f"✅ Evento creado:\n📅 {titulo}\n🗓 {fecha} a las {hora}"
            else:
                respuesta = "❌ No pude crear el evento."

        except Exception as e:
            respuesta = "❌ No entendí los detalles. Intenta: 'Crea un evento el 7 de abril a las 3pm llamado Reunión'"

        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    historial = obtener_historial(sesion_id)
    contexto_docs = buscar_contexto(texto_usuario)

    contexto_web = ""
    if necesita_busqueda(texto_usuario):
        await update.message.reply_text("🔍 Buscando...")
        contexto_web = buscar_web(texto_usuario)

    contenido_sistema = (
        "You are TROY, a personal sovereign agent built by Infima Foundation. "
        "Your personality is warm, direct, and natural — like a trusted collaborator, not a robot. "
        f"IMPORTANT: The user is writing in {idioma}. You MUST respond in {idioma}. No exceptions. "
        "BEHAVIOR RULES: "
        "1. Only use information from the conversation, documents, or web results below. "
        "2. Never invent data or context. "
        "3. If you don't know something, say so briefly. "
        "4. Keep responses short and precise. No filler. "
        "5. Everything runs locally on the user's device."
    )

    if contexto_docs:
        contenido_sistema += f"\n\nDOCUMENT CONTEXT:\n{contexto_docs}\n"

    if contexto_web:
        contenido_sistema += (
            f"\n\nWEB SEARCH RESULTS:\n{contexto_web}\n"
            "Use web results for current information. Mention source when relevant."
        )

    mensajes = [{"role": "system", "content": contenido_sistema}]
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": texto_usuario})

    respuesta_ollama = ollama_client.chat(
        model=MODELO,
        messages=mensajes
    )

    if hasattr(respuesta_ollama, "message"):
        texto_respuesta = respuesta_ollama.message.content
    else:
        texto_respuesta = respuesta_ollama["message"]["content"]

    guardar_mensaje(sesion_id, "assistant", texto_respuesta)
    await update.message.reply_text(texto_respuesta)

def iniciar_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    print("TROY Bot activo — RAG + Web + Mensajería + Calendario...")
    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()