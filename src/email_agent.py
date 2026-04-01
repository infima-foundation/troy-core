# ─────────────────────────────────────────────────
# TROY — Módulo de Email (IMAP + SMTP)
# Infima Foundation A.C.
# Lee y manda correos desde Gmail
# ─────────────────────────────────────────────────

import os
import sys
import re
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

EMAIL    = os.getenv("GOOGLE_EMAIL")
PASSWORD = os.getenv("GOOGLE_APP_PASSWORD")

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# ── HELPERS ──────────────────────────────────────

def decodificar_header(valor):
    if not valor:
        return ""
    partes = decode_header(valor)
    resultado = ""
    for parte, encoding in partes:
        if isinstance(parte, bytes):
            try:
                resultado += parte.decode(encoding or "utf-8", errors="ignore")
            except:
                resultado += parte.decode("latin-1", errors="ignore")
        else:
            resultado += str(parte)
    return resultado

def limpiar_html(texto: str) -> str:
    texto = re.sub(r'<style[^>]*>.*?</style>', ' ', texto, flags=re.DOTALL)
    texto = re.sub(r'<script[^>]*>.*?</script>', ' ', texto, flags=re.DOTALL)
    texto = re.sub(r'<[^>]+>', ' ', texto)
    texto = re.sub(r'&nbsp;', ' ', texto)
    texto = re.sub(r'&amp;', '&', texto)
    texto = re.sub(r'&lt;', '<', texto)
    texto = re.sub(r'&gt;', '>', texto)
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()

def obtener_cuerpo(mensaje) -> str:
    if mensaje.is_multipart():
        # Preferir texto plano
        for parte in mensaje.walk():
            if parte.get_content_type() == "text/plain":
                try:
                    return parte.get_payload(decode=True).decode("utf-8", errors="ignore")
                except:
                    return ""
        # Si no hay texto plano, limpiar HTML
        for parte in mensaje.walk():
            if parte.get_content_type() == "text/html":
                try:
                    html = parte.get_payload(decode=True).decode("utf-8", errors="ignore")
                    return limpiar_html(html)
                except:
                    return ""
    else:
        try:
            cuerpo = mensaje.get_payload(decode=True).decode("utf-8", errors="ignore")
            if "<html" in cuerpo.lower() or "<div" in cuerpo.lower():
                return limpiar_html(cuerpo)
            return cuerpo
        except:
            return ""
    return ""

# ── LEER CORREOS ─────────────────────────────────

def obtener_correos(carpeta: str = "INBOX", limite: int = 5,
                    solo_no_leidos: bool = True) -> list:
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(EMAIL, PASSWORD)
        mail.select(carpeta)

        criterio = "UNSEEN" if solo_no_leidos else "ALL"
        _, ids = mail.search(None, criterio)

        ids_lista = ids[0].split()
        if not ids_lista:
            return []

        ids_recientes = ids_lista[-limite:]
        correos = []

        for uid in reversed(ids_recientes):
            _, data = mail.fetch(uid, "(RFC822)")
            mensaje = email.message_from_bytes(data[0][1])

            remitente = decodificar_header(mensaje.get("From", ""))
            asunto    = decodificar_header(mensaje.get("Subject", "Sin asunto"))
            fecha     = mensaje.get("Date", "")
            cuerpo    = obtener_cuerpo(mensaje)

            correos.append({
                "id": uid.decode(),
                "remitente": remitente,
                "asunto": asunto,
                "fecha": fecha,
                "cuerpo": cuerpo[:500]
            })

        mail.logout()
        return correos

    except Exception as e:
        print(f"Error leyendo correos: {e}")
        return []

def buscar_correos(query: str, limite: int = 5) -> list:
    try:
        mail = imaplib.IMAP4_SSL(IMAP_HOST)
        mail.login(EMAIL, PASSWORD)
        mail.select("INBOX")

        _, ids = mail.search(None, f'SUBJECT "{query}"')
        ids_lista = ids[0].split()

        if not ids_lista:
            _, ids = mail.search(None, f'FROM "{query}"')
            ids_lista = ids[0].split()

        if not ids_lista:
            return []

        ids_recientes = ids_lista[-limite:]
        correos = []

        for uid in reversed(ids_recientes):
            _, data = mail.fetch(uid, "(RFC822)")
            mensaje = email.message_from_bytes(data[0][1])

            remitente = decodificar_header(mensaje.get("From", ""))
            asunto    = decodificar_header(mensaje.get("Subject", "Sin asunto"))
            fecha     = mensaje.get("Date", "")
            cuerpo    = obtener_cuerpo(mensaje)

            correos.append({
                "id": uid.decode(),
                "remitente": remitente,
                "asunto": asunto,
                "fecha": fecha,
                "cuerpo": cuerpo[:500]
            })

        mail.logout()
        return correos

    except Exception as e:
        print(f"Error buscando correos: {e}")
        return []

# ── MANDAR CORREOS ───────────────────────────────

def mandar_correo(destinatario: str, asunto: str, cuerpo: str) -> bool:
    try:
        mensaje = MIMEMultipart()
        mensaje["From"]    = EMAIL
        mensaje["To"]      = destinatario
        mensaje["Subject"] = asunto
        mensaje.attach(MIMEText(cuerpo, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL, PASSWORD)
            server.send_message(mensaje)

        return True

    except Exception as e:
        print(f"Error mandando correo: {e}")
        return False

# ── FORMATEO ─────────────────────────────────────

def formatear_correos(correos: list, idioma: str = "Spanish") -> str:
    if not correos:
        return "No tienes correos nuevos." if idioma == "Spanish" else "No new emails."

    texto = f"📧 Tienes {len(correos)} correo(s):\n\n"
    for c in correos:
        texto += f"✉️ De: {c['remitente'][:50]}\n"
        texto += f"   📌 {c['asunto']}\n"
        texto += f"   📅 {c['fecha'][:25]}\n"
        if c['cuerpo']:
            cuerpo_corto = c['cuerpo'][:150].replace('\n', ' ')
            texto += f"   💬 {cuerpo_corto}...\n"
        texto += "\n"

    return texto.strip()