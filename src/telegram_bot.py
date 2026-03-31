# ─────────────────────────────────────────────────
# TROY — Conector de Telegram v0.2
# Infima Foundation A.C.
# Con RAG + Búsqueda Web
# ─────────────────────────────────────────────────

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from memoria import guardar_mensaje, obtener_historial
from rag import buscar_contexto
from busqueda import buscar_web, necesita_busqueda
from ollama import Client
import langdetect

ollama_client = Client(host='http://localhost:11434')

TELEGRAM_TOKEN = "8706487749:AAFIDEmKKtppU6AcNpOComdzPn_-BGdmXvk"
MODELO = "llama3.2"

def detectar_idioma(texto: str) -> str:
    try:
        codigo = langdetect.detect(texto)
        return "Spanish" if codigo == "es" else "English"
    except:
        return "English"

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    sesion_id = str(update.effective_user.id)
    idioma = detectar_idioma(texto_usuario)

    historial = obtener_historial(sesion_id)
    guardar_mensaje(sesion_id, "user", texto_usuario)

    # Buscar en documentos locales
    contexto_docs = buscar_contexto(texto_usuario)

    # Buscar en internet si es necesario
    contexto_web = ""
    uso_web = False
    if necesita_busqueda(texto_usuario):
        await update.message.reply_text("🔍 Buscando...")
        contexto_web = buscar_web(texto_usuario)
        if contexto_web:
            uso_web = True

    # Construir el prompt
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
        contenido_sistema += (
            f"\n\nDOCUMENT CONTEXT:\n{contexto_docs}\n"
        )

    if contexto_web:
        contenido_sistema += (
            f"\n\nWEB SEARCH RESULTS:\n{contexto_web}\n"
            "Use the web results to answer current or real-time questions. "
            "Mention the source when relevant."
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
    print("TROY Bot activo con RAG + Búsqueda Web...")
    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()