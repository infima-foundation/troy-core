# ─────────────────────────────────────────────────
# TROY — Conector de Telegram
# Infima Foundation A.C.
# ─────────────────────────────────────────────────

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from memoria import guardar_mensaje, obtener_historial
from rag import buscar_contexto
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

    # Buscar contexto en los documentos
    contexto_docs = buscar_contexto(texto_usuario)

    contenido_sistema = (
        "You are TROY, a personal sovereign agent built by Infima Foundation. "
        "Your personality is warm, direct, and natural — like a trusted collaborator, not a robot. "
        f"IMPORTANT: The user is writing in {idioma}. You MUST respond in {idioma}. No exceptions. "
        "BEHAVIOR RULES: "
        "1. Only use information the user has explicitly given you or that appears in the documents below. "
        "2. Never invent names, data, organizations, or context. "
        "3. If you don't know something, say so briefly and directly. "
        "4. Keep responses short and precise. No filler. "
        "5. Everything runs locally on the user's device. Their data never leaves their control."
    )

    if contexto_docs:
        contenido_sistema += (
            f"\n\nDOCUMENT CONTEXT:\n{contexto_docs}\n"
            "Use ONLY the above document fragments to answer. "
            "If the answer is in the documents, use it. "
            "If not, say you don't have that information."
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
    print("TROY Bot de Telegram activo con RAG...")
    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()