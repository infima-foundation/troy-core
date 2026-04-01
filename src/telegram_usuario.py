# ─────────────────────────────────────────────────
# TROY — Cliente de Telegram como Usuario
# Infima Foundation A.C.
# ─────────────────────────────────────────────────

import os
import sys
import asyncio
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API_ID   = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
SESSION  = os.path.join(os.path.dirname(__file__), "..", "troy_telegram_session")

async def mandar_mensaje(destinatario: str, mensaje: str) -> bool:
    """
    Manda un mensaje a un contacto.
    destinatario: @username o número +521234567890
    """
    try:
        client = TelegramClient(SESSION, API_ID, API_HASH)
        await client.start()
        await client.send_message(destinatario, mensaje)
        await client.disconnect()
        return True
    except Exception as e:
        print(f"Error mandando mensaje: {e}")
        return False

async def obtener_contactos() -> list:
    """Lista todos los contactos del usuario."""
    try:
        client = TelegramClient(SESSION, API_ID, API_HASH)
        await client.start()
        from telethon.tl.functions.contacts import GetContactsRequest
        resultado = await client(GetContactsRequest(hash=0))
        contactos = []
        for u in resultado.users:
            nombre = f"{u.first_name or ''} {u.last_name or ''}".strip()
            contactos.append({
                "nombre": nombre,
                "username": u.username,
                "id": u.id
            })
        await client.disconnect()
        return contactos
    except Exception as e:
        print(f"Error obteniendo contactos: {e}")
        return []

def enviar(destinatario: str, mensaje: str) -> bool:
    """Wrapper síncrono para mandar mensajes."""
    return asyncio.run(mandar_mensaje(destinatario, mensaje))