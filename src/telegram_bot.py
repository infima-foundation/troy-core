# ─────────────────────────────────────────────────
# TROY — Conector de Telegram v0.6
# Infima Foundation A.C.
# RAG + Web + Mensajería + Calendario + Email
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
from calendario import (obtener_eventos, crear_evento, editar_evento,
                        borrar_evento, crear_tarea, obtener_tareas,
                        formatear_eventos, formatear_tareas)
from email_agent import (obtener_correos, buscar_correos,
                         mandar_correo, formatear_correos)
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

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    sesion_id = str(update.effective_user.id)
    idioma = detectar_idioma(texto_usuario)

    guardar_mensaje(sesion_id, "user", texto_usuario)

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

    # ── Email ────────────────────────────────────
    accion_email = detectar_accion_email(texto_usuario)

    if accion_email == "leer":
        await update.message.reply_text("📧 Revisando tu correo...")
        correos = obtener_correos(limite=5)
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
        correos = buscar_correos(query, limite=3)
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
                exito = mandar_correo(para, asunto, cuerpo)
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
        eventos = obtener_eventos(dias=7)
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
            exito = crear_evento(titulo, fecha, hora, duracion)
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
            exito = borrar_evento(titulo_busqueda)
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
            exito = editar_evento(
                lineas.get("BUSCAR", ""),
                lineas.get("TITULO") or None,
                lineas.get("FECHA") or None,
                lineas.get("HORA") or None
            )
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
            exito = crear_tarea(
                lineas.get("TITULO", "Nueva tarea"),
                lineas.get("DESCRIPCION", ""),
                lineas.get("FECHA") or None
            )
            respuesta = (f"✅ Tarea creada: {lineas.get('TITULO', 'Nueva tarea')}"
                        if exito else "❌ No pude crear la tarea.")
        except Exception:
            respuesta = "❌ No pude procesar la tarea."
        guardar_mensaje(sesion_id, "assistant", respuesta)
        await update.message.reply_text(respuesta)
        return

    elif accion == "ver_tareas":
        await update.message.reply_text("📋 Revisando tus tareas...")
        respuesta = formatear_tareas(obtener_tareas(), idioma)
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

def iniciar_bot():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    print("TROY Bot activo — RAG + Web + Mensajería + Calendario + Email...")
    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()