# ─────────────────────────────────────────────────
# TROY — Conector de Telegram v1.0
# Infima Foundation A.C.
# Orquestador integrado con Tool Registry + Turn Loop
# + Resumen Diario a las 8am
# ─────────────────────────────────────────────────

import sys, os, asyncio
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))

from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from calendario import obtener_eventos
import orquestador

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8703220225")

# ── RESUMEN DIARIO ───────────────────────────────

async def enviar_resumen_diario(bot, chat_id: str):
    try:
        resumen = "Buenos días, Mauricio\n\n"
        loop = asyncio.get_event_loop()
        eventos = await loop.run_in_executor(None, lambda: obtener_eventos(dias=1))

        if eventos:
            resumen += "Agenda de hoy:\n"
            for e in eventos:
                resumen += f"- {e['titulo']} — {e['inicio']}\n"
        else:
            resumen += "No tienes eventos hoy.\n"

        resumen += "\n¿En qué te puedo ayudar?"
        await bot.send_message(chat_id=chat_id, text=resumen)

    except Exception as e:
        print(f"Error enviando resumen diario: {e}")

# ── RESPONDER ────────────────────────────────────

async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_usuario = update.message.text
    sesion_id = str(update.effective_user.id)

    loop = asyncio.get_running_loop()

    # Los pensamientos intermedios del LLM son internos — no llegan al usuario.
    def callback_pensamiento(pensamiento: str):
        pass

    # El orquestador es blocking — lo corremos en un thread.
    tarea = loop.run_in_executor(
        None,
        lambda: orquestador.procesar(texto_usuario, sesion_id, callback_pensamiento)
    )

    # "Pensando..." solo si la tarea tarda más de 2 segundos.
    try:
        respuesta = await asyncio.wait_for(asyncio.shield(tarea), timeout=2.0)
    except asyncio.TimeoutError:
        await update.message.reply_text("Pensando...")
        try:
            respuesta = await tarea
        except Exception as e:
            respuesta = f"Error en el orquestador: {e}"
    except Exception as e:
        respuesta = f"Error en el orquestador: {e}"

    await update.message.reply_text(respuesta)

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

    print("TROY Bot activo — Orquestador integrado (Tool Registry + Turn Loop + Memoria)...")
    app.run_polling()

if __name__ == "__main__":
    iniciar_bot()
