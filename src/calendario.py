# ─────────────────────────────────────────────────
# TROY — Módulo de Calendario Completo (CalDAV)
# Infima Foundation A.C.
# Soporta: leer, crear, editar, borrar eventos y tareas
# ─────────────────────────────────────────────────

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
import caldav
from icalendar import Calendar, Event, Todo
from datetime import datetime, timedelta
import uuid

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

EMAIL    = os.getenv("GOOGLE_EMAIL")
PASSWORD = os.getenv("GOOGLE_APP_PASSWORD")
CALDAV_URL = f"https://www.google.com/calendar/dav/{EMAIL}/events"

def obtener_cliente():
    return caldav.DAVClient(
        url=CALDAV_URL,
        username=EMAIL,
        password=PASSWORD
    )

def obtener_calendarios():
    client = obtener_cliente()
    principal = client.principal()
    return principal.calendars()

# ── EVENTOS ──────────────────────────────────────

def obtener_eventos(dias: int = 7) -> list:
    try:
        calendarios = obtener_calendarios()
        ahora = datetime.now()
        fin = ahora + timedelta(days=dias)
        eventos = []

        for cal in calendarios:
            try:
                resultados = cal.date_search(start=ahora, end=fin, expand=True)
                for evento in resultados:
                    comp = Calendar.from_ical(evento.data)
                    for componente in comp.walk():
                        if componente.name == "VEVENT":
                            titulo = str(componente.get("SUMMARY", "Sin título"))
                            inicio = componente.get("DTSTART")
                            descripcion = str(componente.get("DESCRIPTION", ""))
                            uid = str(componente.get("UID", ""))

                            if inicio:
                                inicio_dt = inicio.dt
                                inicio_str = inicio_dt.strftime("%Y-%m-%d %H:%M") if hasattr(inicio_dt, 'strftime') else str(inicio_dt)
                            else:
                                inicio_str = "Sin fecha"

                            eventos.append({
                                "titulo": titulo,
                                "inicio": inicio_str,
                                "descripcion": descripcion,
                                "uid": uid,
                                "objeto": evento
                            })
            except Exception:
                continue

        eventos.sort(key=lambda x: x["inicio"])
        return eventos

    except Exception as e:
        print(f"Error obteniendo eventos: {e}")
        return []

def crear_evento(titulo: str, fecha: str, hora: str = "09:00",
                 duracion_horas: int = 1, descripcion: str = "",
                 invitados: list = None) -> bool:
    try:
        calendarios = obtener_calendarios()
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

        # Agregar invitados si se especifican
        if invitados:
            from icalendar import vCalAddress, vText
            for email_invitado in invitados:
                attendee = vCalAddress(f"MAILTO:{email_invitado}")
                attendee.params["ROLE"] = vText("REQ-PARTICIPANT")
                attendee.params["PARTSTAT"] = vText("NEEDS-ACTION")
                attendee.params["RSVP"] = vText("TRUE")
                evento.add("attendee", attendee, encode=0)

        cal.add_component(evento)
        cal_principal.add_event(cal.to_ical())
        return True

    except Exception as e:
        print(f"Error creando evento: {e}")
        return False

def editar_evento(titulo_busqueda: str, nuevo_titulo: str = None,
                  nueva_fecha: str = None, nueva_hora: str = None,
                  nueva_descripcion: str = None) -> bool:
    """
    Busca un evento por título y lo edita.
    Solo actualiza los campos que se especifiquen.
    """
    try:
        eventos = obtener_eventos(dias=30)
        evento_obj = None

        for e in eventos:
            if titulo_busqueda.lower() in e["titulo"].lower():
                evento_obj = e["objeto"]
                break

        if not evento_obj:
            return False

        comp = Calendar.from_ical(evento_obj.data)
        for componente in comp.walk():
            if componente.name == "VEVENT":
                if nuevo_titulo:
                    componente["SUMMARY"] = nuevo_titulo
                if nueva_descripcion:
                    componente["DESCRIPTION"] = nueva_descripcion
                if nueva_fecha or nueva_hora:
                    inicio_actual = componente.get("DTSTART").dt
                    fecha_str = nueva_fecha or inicio_actual.strftime("%Y-%m-%d")
                    hora_str = nueva_hora or inicio_actual.strftime("%H:%M")
                    nuevo_inicio = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
                    duracion = componente.get("DTEND").dt - inicio_actual
                    componente["DTSTART"].dt = nuevo_inicio
                    componente["DTEND"].dt = nuevo_inicio + duracion

        evento_obj.data = comp.to_ical()
        evento_obj.save()
        return True

    except Exception as e:
        print(f"Error editando evento: {e}")
        return False

def borrar_evento(titulo_busqueda: str) -> bool:
    """Busca un evento por título y lo borra."""
    try:
        eventos = obtener_eventos(dias=30)

        for e in eventos:
            if titulo_busqueda.lower() in e["titulo"].lower():
                e["objeto"].delete()
                return True

        return False

    except Exception as e:
        print(f"Error borrando evento: {e}")
        return False

# ── TAREAS ───────────────────────────────────────

TASKS_URL = f"https://www.google.com/calendar/dav/{EMAIL}/tasks/"

def obtener_cliente_tareas():
    return caldav.DAVClient(
        url=TASKS_URL,
        username=EMAIL,
        password=PASSWORD
    )

def crear_tarea(titulo: str, descripcion: str = "",
                fecha_limite: str = None) -> bool:
    """
    Crea una tarea en Google Tasks.
    fecha_limite formato: YYYY-MM-DD
    """
    try:
        client = obtener_cliente_tareas()
        principal = client.principal()
        calendarios = principal.calendars()

        if not calendarios:
            return False

        cal_tareas = calendarios[0]

        cal = Calendar()
        cal.add("prodid", "-//TROY//Infima Foundation//ES")
        cal.add("version", "2.0")

        tarea = Todo()
        tarea.add("summary", titulo)
        tarea.add("description", descripcion)
        tarea.add("uid", str(uuid.uuid4()))
        tarea.add("status", "NEEDS-ACTION")

        if fecha_limite:
            fecha_dt = datetime.strptime(fecha_limite, "%Y-%m-%d")
            tarea.add("due", fecha_dt)

        cal.add_component(tarea)
        cal_tareas.add_todo(cal.to_ical())
        return True

    except Exception as e:
        print(f"Error creando tarea: {e}")
        return False

def obtener_tareas() -> list:
    """Obtiene todas las tareas pendientes."""
    try:
        client = obtener_cliente_tareas()
        principal = client.principal()
        calendarios = principal.calendars()

        tareas = []
        for cal in calendarios:
            try:
                todos = cal.todos()
                for todo in todos:
                    comp = Calendar.from_ical(todo.data)
                    for componente in comp.walk():
                        if componente.name == "VTODO":
                            titulo = str(componente.get("SUMMARY", "Sin título"))
                            descripcion = str(componente.get("DESCRIPTION", ""))
                            estado = str(componente.get("STATUS", "NEEDS-ACTION"))
                            due = componente.get("DUE")
                            fecha_limite = due.dt.strftime("%Y-%m-%d") if due else "Sin fecha"

                            tareas.append({
                                "titulo": titulo,
                                "descripcion": descripcion,
                                "estado": estado,
                                "fecha_limite": fecha_limite,
                                "objeto": todo
                            })
            except Exception:
                continue

        return tareas

    except Exception as e:
        print(f"Error obteniendo tareas: {e}")
        return []

# ── FORMATEO ─────────────────────────────────────

def formatear_eventos(eventos: list, idioma: str = "Spanish") -> str:
    if not eventos:
        return "No tienes eventos próximos." if idioma == "Spanish" else "No upcoming events."

    texto = f"📅 Tienes {len(eventos)} evento(s):\n\n"
    for e in eventos:
        texto += f"📌 {e['titulo']}\n"
        texto += f"   🕐 {e['inicio']}\n"
        if e['descripcion']:
            texto += f"   📝 {e['descripcion'][:80]}\n"
        texto += "\n"
    return texto.strip()

def formatear_tareas(tareas: list, idioma: str = "Spanish") -> str:
    if not tareas:
        return "No tienes tareas pendientes." if idioma == "Spanish" else "No pending tasks."

    texto = f"✅ Tienes {len(tareas)} tarea(s):\n\n"
    for t in tareas:
        estado_emoji = "✅" if t["estado"] == "COMPLETED" else "⏳"
        texto += f"{estado_emoji} {t['titulo']}\n"
        if t["descripcion"]:
            texto += f"   📝 {t['descripcion'][:80]}\n"
        if t["fecha_limite"] != "Sin fecha":
            texto += f"   📆 Límite: {t['fecha_limite']}\n"
        texto += "\n"
    return texto.strip()