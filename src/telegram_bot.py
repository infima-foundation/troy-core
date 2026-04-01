# ─────────────────────────────────────────────────
# TROY — Conector de Telegram v0.8
# Infima Foundation A.C.
# RAG + Web + Mensajería + Calendario + Email
# + Resumen Diario + Browser Use
# ─────────────────────────────────────────────────

import sys, os, re, asyncio
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from memoria import guardar_mensaje, obtener_historial
from rag import buscar_contexto
from busqueda import buscar_web, necesita_busqueda
from telegram_usuario import mandar_mensaje
from calendario import (obtener_eventos, crear_evento, editar_evento,
                        borrar_evento, crear_tarea, obtener_tareas,
                        formatear_eventos, formatear_tareas)
from email_agent import (obtener_correos, buscar_correos,
                         mandar_correo, formatear_correos)
from browser_use import navegar, buscar_google
from ollama import Client
import langdetect

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

ollama_client = Client(host='http://localhost:11434')
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8703220225")
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
    if any(s in texto_lower for s in [
        "borra", "elimina", "cancela", "delete", "remove", "cancel"
    ]):
        return "borrar"
    elif any(s in texto_lower for s in [
        "edita", "cambia", "modifica", "mueve", "edit", "change", "move", "update", "actualiza"
    ]):
        return "editar"
    elif any(s in texto_lower for s in ["tarea", "task", "to-do", "todo", "pendiente"]):
        if any(s in texto_lower for s in ["crea", "agrega", "añade", "add", "nueva"]):
            return "crear_tarea"
        return "ver_tareas"
    elif any(s in texto_lower for s in [
        "agrega", "añade", "crea", "programa", "nuevo evento",
        "nueva cita", "add event", "create event", "schedule", "crea un"
    ]):
        return "crear"
    elif any(s in texto_lower for s in [
        "agenda", "calendario", "calendar", "eventos", "qué tengo",
        "que tengo", "what do i have", "citas", "reuniones", "meetings",
        "esta semana", "this week", "hoy", "today", "mañana", "tomorrow",
        "próximos", "upcoming"
    ]):
        return "consultar"
    return None

def detectar_accion_email(texto: str) -> str:
    texto_lower = texto.lower()
    if any(s in texto_lower for s in [
        "manda un correo", "envía un correo", "escríbele un correo",
        "manda correo", "envía correo", "send email", "send an email",
        "manda email", "envía email", "write an email"
    ]):
        return "mandar"
    elif any(s in texto_lower for s in [
        "busca correo", "busca en mi correo", "search email",
        "correos de", "emails from", "busca en correo"
    ]):
        return "buscar"
    elif any(s in texto_lower for s in [
        "correos", "emails", "inbox", "bandeja",
        "mensajes nuevos", "qué correos", "que correos",
        "revisa mi correo", "check my email", "check email"
    ]):
        return "leer"
    return None

def detectar_browser_use(texto: str):
    texto_lower = texto.lower()
    url_match = re.search(r'https?://\S+', texto)
    if url_match and any(s in texto_lower for s in [
        "abre", "navega", "entra a", "visita", "open", "go to", "browse",
        "dime qué dice", "qué dice", "lee", "extrae"
    ]):
        return "navegar", url_match.group(0)
    if any(s in texto_lower for s in [
        "busca en google", "search google",
        "encuentra en internet", "busca en la web"
    ]):
        return "buscar_google", texto
    return None

def extraer_con_llm(prompt_sistema: str, texto_usuario: str, tokens: int = 60) -> dict:
    resp = ollama_client.chat(
        model=MODELO,
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": texto_usuario}
        ],
        options={"num_predict": tokens}
    )
    texto = resp.message.content if hasattr(resp, "message") else resp["message"]["content"]
    lineas = {}
    for linea in texto.strip().split("\n"):
        if ":" in linea:
            k, v = linea.split(":", 1)
            lineas[k.strip().upper()] = v.strip()
    return lineas

def limpiar_titulo(titulo: str) -> str:
    palabras_extra = [
        "eliminado", "borrado", "cancelado", "deleted", "removed",
        "cancelled", "event", "evento", "the", "el", "la"
    ]
    resultado = titulo.strip().strip('"\'')
    for palabra in palabras_extra:
        resultado = re.sub(rf'\b{palabra}\b', '', resultado, flags=re.IGNORECASE).strip()
    return resultado.strip('"\'').strip()

# ── RESUMEN DIARIO ───────────────────────────────

async def enviar_resumen_diario(bot, chat_id: str):
    try:
        resumen = "🌅 *Buenos días, Mauricio*\n\n"
        loop = asyncio.get_event_loop()
        eventos = await loop.run_in_executor(None, lambda: obtener_eventos(dias=1))

        if eventos:
            resumen += "📅 *Tu agenda de hoy:*\n"
            for e in eventos:
                resumen += f"• {e['titulo']} — {e['inicio']}\n"
        else:
            resumen += "📅 No tienes eventos hoy.\n"

        resumen += "\n¿En qué te puedo ayudar hoy?"
        await bot.send_message(chat_id=chat_id, text=resumen, parse_mode="Markdown")

    except Exception as e:
        print(f"Error enviando resumen diario: {e}")

# ── RESPONDER ────────────────────────────────────

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    sesion_id = str(update.effective_user.id)
    idioma = detectar_idioma(texto_usuario)

    guardar_mensaje(sesion_id, "user", texto_usuario)

    # ── Resumen diario manual ────────────────────
    if any(s in texto_usuario.lower() for s in [
        "resumen del día", "resumen de hoy", "daily summary",
        "qué tengo hoy", "que tengo hoy", "resumen diario"
    ]):
        await update.message.reply_text("⏳ Preparando tu resumen...")
        await enviar_resumen_diario(update.get_bot(), sesion_id)
        return

    # ── Mensajería Telegram ──────────────────────
    envio = detectar_envio_mensaje(texto_usuario)
    if envio:
        destinatario, mensaje_a_enviar = envio
        await update.message.reply_text(f"📤 Mandando mensaje a {destinatario}...")
        exito = await mandar_mensaje(destinatario, mensaje_a_enviar)
        respuesta = (f"✅ Mensaje enviado a {destinatario}: '{mensaje_a_enviar}'"
                     if exito else f"❌ No pude mandar el mensaje a {destinatario}.")
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    # ── Browser Use ──────────────────────────────
    browser_accion = detectar_browser_use(texto_usuario)
    if browser_accion:
        accion, parametro = browser_accion
        if accion == "navegar":
            await update.message.reply_text(f"🌐 Navegando {parametro}...")
            loop = asyncio.get_event_loop()
            contenido = await loop.run_in_executor(None, lambda: navegar(parametro))
            # Resumir con LLM
            mensajes_resumen = [
                {
                    "role": "system",
                    "content": (
                        f"Summarize this webpage content in {idioma} in 3-5 sentences. "
                        "Be concise and focus on the most important information."
                    )
                },
                {"role": "user", "content": contenido[:2000]}
            ]
            resp = ollama_client.chat(model=MODELO, messages=mensajes_resumen,
                                     options={"num_predict": 150})
            respuesta = resp.message.content if hasattr(resp, "message") else resp["message"]["content"]
            respuesta = f"🌐 *{parametro}*\n\n{respuesta}"

        elif accion == "buscar_google":
            query = re.sub(
                r'busca en google|search google|encuentra en internet|busca en la web',
                '', parametro, flags=re.IGNORECASE
            ).strip()
            await update.message.reply_text(f"🔍 Buscando en Google: {query}...")
            loop = asyncio.get_event_loop()
            respuesta = await loop.run_in_executor(None, lambda: buscar_google(query))

        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta, parse_mode="Markdown")
        return

    # ── Email ────────────────────────────────────
    accion_email = detectar_accion_email(texto_usuario)

    if accion_email == "leer":
        await update.message.reply_text("📧 Revisando tu correo...")
        loop = asyncio.get_event_loop()
        correos = await loop.run_in_executor(None, lambda: obtener_correos(limite=5))
        respuesta = formatear_correos(correos, idioma)
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion_email == "buscar":
        await update.message.reply_text("🔍 Buscando en tu correo...")
        lineas = extraer_con_llm(
            "Extract the search query for email. Reply ONLY:\nQUERY: search term",
            texto_usuario, tokens=15
        )
        query = lineas.get("QUERY", texto_usuario)
        loop = asyncio.get_event_loop()
        correos = await loop.run_in_executor(None, lambda: buscar_correos(query, limite=3))
        respuesta = formatear_correos(correos, idioma)
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion_email == "mandar":
        await update.message.reply_text("📧 Preparando el correo...")
        try:
            lineas = extraer_con_llm(
                "Extract email details. Reply ONLY:\n"
                "PARA: email@address.com\n"
                "ASUNTO: subject\n"
                "CUERPO: email body",
                texto_usuario, tokens=80
            )
            para   = lineas.get("PARA", "")
            asunto = lineas.get("ASUNTO", "Mensaje de TROY")
            cuerpo = lineas.get("CUERPO", "")
            if not para:
                respuesta = "❌ No entendí el destinatario. Intenta: 'Manda un correo a juan@ejemplo.com sobre la reunión'"
            else:
                loop = asyncio.get_event_loop()
                exito = await loop.run_in_executor(None, lambda: mandar_correo(para, asunto, cuerpo))
                respuesta = (f"✅ Correo enviado a {para}\n📌 Asunto: {asunto}"
                            if exito else "❌ No pude mandar el correo.")
        except Exception:
            respuesta = "❌ No entendí los detalles del correo."
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    # ── Calendario ───────────────────────────────
    accion = detectar_consulta_calendario(texto_usuario)

    if accion == "consultar":
        await update.message.reply_text("📅 Revisando tu calendario...")
        loop = asyncio.get_event_loop()
        eventos = await loop.run_in_executor(None, lambda: obtener_eventos(dias=7))
        respuesta = formatear_eventos(eventos, idioma)
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion == "crear":
        await update.message.reply_text("📅 Procesando el evento...")
        try:
            lineas = extraer_con_llm(
                f"Today is {datetime.now().strftime('%Y-%m-%d')}. "
                "Extract event info. Reply ONLY:\n"
                "TITULO: title\nFECHA: YYYY-MM-DD\nHORA: HH:MM\nDURACION: 1",
                texto_usuario, tokens=50
            )
            titulo   = lineas.get("TITULO", "Nuevo evento")
            fecha    = lineas.get("FECHA", datetime.now().strftime("%Y-%m-%d"))
            hora     = lineas.get("HORA", "09:00")
            duracion = int(lineas.get("DURACION", "1"))
            loop = asyncio.get_event_loop()
            exito = await loop.run_in_executor(None, lambda: crear_evento(titulo, fecha, hora, duracion))
            respuesta = (f"✅ Evento creado:\n📅 {titulo}\n🗓 {fecha} a las {hora}"
                        if exito else "❌ No pude crear el evento.")
        except Exception:
            respuesta = "❌ No entendí los detalles. Intenta: 'Crea un evento el 7 de abril a las 3pm llamado Reunión'"
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion == "borrar":
        await update.message.reply_text("🗑 Buscando el evento para borrar...")
        try:
            match = re.search(
                r"(?:borra|elimina|cancela|delete|remove|cancel)\s+(?:el\s+evento\s+)?[\"']?(.+?)[\"']?\s*$",
                texto_usuario.lower()
            )
            titulo_busqueda = (match.group(1).strip().strip('"\'') if match
                              else limpiar_titulo(extraer_con_llm(
                                  "Extract ONLY the event name to delete. Reply ONLY:\nTITULO: name",
                                  texto_usuario, tokens=15).get("TITULO", "")))
            loop = asyncio.get_event_loop()
            exito = await loop.run_in_executor(None, lambda: borrar_evento(titulo_busqueda))
            respuesta = (f"✅ Evento '{titulo_busqueda}' borrado."
                        if exito else f"❌ No encontré un evento llamado '{titulo_busqueda}'.")
        except Exception:
            respuesta = "❌ No pude procesar la solicitud."
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion == "editar":
        await update.message.reply_text("✏️ Procesando edición...")
        try:
            lineas = extraer_con_llm(
                f"Today is {datetime.now().strftime('%Y-%m-%d')}. "
                "Extract edit info. Reply ONLY:\n"
                "BUSCAR: original title\nTITULO: new title or empty\n"
                "FECHA: YYYY-MM-DD or empty\nHORA: HH:MM or empty",
                texto_usuario, tokens=60
            )
            loop = asyncio.get_event_loop()
            exito = await loop.run_in_executor(None, lambda: editar_evento(
                lineas.get("BUSCAR", ""),
                lineas.get("TITULO") or None,
                lineas.get("FECHA") or None,
                lineas.get("HORA") or None
            ))
            respuesta = ("✅ Evento actualizado." if exito
                        else f"❌ No encontré el evento '{lineas.get('BUSCAR', '')}'.")
        except Exception:
            respuesta = "❌ No pude procesar la edición."
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion == "crear_tarea":
        await update.message.reply_text("📝 Creando tarea...")
        try:
            lineas = extraer_con_llm(
                f"Today is {datetime.now().strftime('%Y-%m-%d')}. "
                "Extract task info. Reply ONLY:\n"
                "TITULO: task title\nDESCRIPCION: description or empty\nFECHA: YYYY-MM-DD or empty",
                texto_usuario, tokens=60
            )
            loop = asyncio.get_event_loop()
            exito = await loop.run_in_executor(None, lambda: crear_tarea(
                lineas.get("TITULO", "Nueva tarea"),
                lineas.get("DESCRIPCION", ""),
                lineas.get("FECHA") or None
            ))
            respuesta = (f"✅ Tarea creada: {lineas.get('TITULO', 'Nueva tarea')}"
                        if exito else "❌ No pude crear la tarea.")
        except Exception:
            respuesta = "❌ No pude procesar la tarea."
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion == "ver_tareas":
        await update.message.reply_text("📋 Revisando tus tareas...")
        loop = asyncio.get_event_loop()
        tareas = await loop.run_in_executor(None, obtener_tareas)
        respuesta = formatear_tareas(tareas, idioma)
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    # ── Conversación general ─────────────────────
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

    respuesta_ollama = ollama_client.chat(model=MODELO, messages=mensajes)
    texto_respuesta = (respuesta_ollama.message.content
                      if hasattr(respuesta_ollama, "message")
                      else respuesta_ollama["message"]["content"])

    guardar_mensaje(sesion_id, "assistant", texto_respuesta)
    await update.message.reply_text(texto_respuesta)

# ── INICIAR BOT ──────────────────────────────────

def iniciar_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    async def post_init(application):
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            enviar_resumen_diario,
            CronTrigger(hour=8, minute=0),
            args=[application.bot, CHAT_ID],
            id="resumen_diario",
            replace_existing=True
        )
        scheduler.start()
        print(f"📅 Resumen diario programado para las 8:00am → {CHAT_ID}")

    app.post_init = post_init

    print("TROY Bot activo — RAG + Web + Mensajería + Calendario + Email + Browser Use...")
    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()