# ─────────────────────────────────────────────────
# TROY — Módulo de Calendario (CalDAV)
# Infima Foundation A.C.
# Compatible con Google Calendar, iCloud, Outlook
# ─────────────────────────────────────────────────

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
import caldav
from icalendar import Calendar, Event
from datetime import datetime, timedelta
import uuid

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

EMAIL    = os.getenv("GOOGLE_EMAIL")
PASSWORD = os.getenv("GOOGLE_APP_PASSWORD")

# URL CalDAV de Google Calendar
CALDAV_URL = f"https://www.google.com/calendar/dav/{EMAIL}/events"

def obtener_cliente():
    return caldav.DAVClient(
        url=CALDAV_URL,
        username=EMAIL,
        password=PASSWORD
    )

def obtener_eventos(dias: int = 7) -> list:
    """
    Obtiene los eventos de los próximos N días.
    """
    try:
        client = obtener_cliente()
        principal = client.principal()
        calendarios = principal.calendars()

        if not calendarios:
            return []

        ahora = datetime.now()
        fin = ahora + timedelta(days=dias)
        eventos = []

        for cal in calendarios:
            try:
                resultados = cal.date_search(
                    start=ahora,
                    end=fin,
                    expand=True
                )
                for evento in resultados:
                    comp = Calendar.from_ical(evento.data)
                    for componente in comp.walk():
                        if componente.name == "VEVENT":
                            titulo = str(componente.get("SUMMARY", "Sin título"))
                            inicio = componente.get("DTSTART")
                            fin_evento = componente.get("DTEND")
                            descripcion = str(componente.get("DESCRIPTION", ""))

                            if inicio:
                                inicio_dt = inicio.dt
                                if hasattr(inicio_dt, 'strftime'):
                                    inicio_str = inicio_dt.strftime("%Y-%m-%d %H:%M")
                                else:
                                    inicio_str = str(inicio_dt)
                            else:
                                inicio_str = "Sin fecha"

                            eventos.append({
                                "titulo": titulo,
                                "inicio": inicio_str,
                                "descripcion": descripcion
                            })
            except Exception:
                continue

        # Ordenar por fecha
        eventos.sort(key=lambda x: x["inicio"])
        return eventos

    except Exception as e:
        print(f"Error obteniendo eventos: {e}")
        return []

def crear_evento(titulo: str, fecha: str, hora: str = "09:00",
                 duracion_horas: int = 1, descripcion: str = "") -> bool:
    """
    Crea un evento en Google Calendar.
    fecha formato: YYYY-MM-DD
    hora formato: HH:MM
    """
    try:
        client = obtener_cliente()
        principal = client.principal()
        calendarios = principal.calendars()

        if not calendarios:
            return False

        cal_principal = calendarios[0]

        inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        fin = inicio + timedelta(hours=duracion_horas)

        cal = Calendar()
        cal.add("prodid", "-//TROY//Infima Foundation//ES")
        cal.add("version", "2.0")

        evento = Event()
        evento.add("summary", titulo)
        evento.add("dtstart", inicio)
        evento.add("dtend", fin)
        evento.add("description", descripcion)
        evento.add("uid", str(uuid.uuid4()))

        cal.add_component(evento)

        cal_principal.add_event(cal.to_ical())
        return True

    except Exception as e:
        print(f"Error creando evento: {e}")
        return False

def formatear_eventos(eventos: list, idioma: str = "Spanish") -> str:
    """Formatea los eventos para presentarlos al usuario."""
    if not eventos:
        if idioma == "Spanish":
            return "No tienes eventos próximos."
        return "You have no upcoming events."

    if idioma == "Spanish":
        texto = f"Tienes {len(eventos)} evento(s) próximo(s):\n\n"
    else:
        texto = f"You have {len(eventos)} upcoming event(s):\n\n"

    for e in eventos:
        texto += f"📅 {e['titulo']}\n"
        texto += f"   {e['inicio']}\n"
        if e['descripcion']:
            texto += f"   {e['descripcion'][:100]}\n"
        texto += "\n"

    return texto.strip()