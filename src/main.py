# ─────────────────────────────────────────────────
# TROY Core — v0.1.0
# Infima Foundation A.C.
# Agente Personal Soberano
# ─────────────────────────────────────────────────

from fastapi import FastAPI
from pydantic import BaseModel
import ollama
import psutil
import platform
from datetime import datetime

app = FastAPI(
    title="TROY Core",
    version="0.1.0",
    description="Agente Personal Soberano — Infima Foundation"
)

# ── HIPERVISOR ───────────────────────────────────
# Decide dónde procesa cada tarea según el estado
# del dispositivo en tiempo real.

def evaluar_recursos() -> dict:
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory().percent

    bateria = None
    enchufado = None
    if hasattr(psutil, "sensors_battery"):
        b = psutil.sensors_battery()
        if b:
            bateria = round(b.percent, 1)
            enchufado = b.power_plugged

    # Lógica de decisión del Hipervisor
    if bateria is None or enchufado:
        # Mac de escritorio o enchufada — sin restricción
        decision = "local"
    elif bateria > 50 and cpu < 75:
        decision = "local"
    elif bateria > 20:
        decision = "nodo"   # Deriva al Nodo Nano si existe
    else:
        decision = "remoto" # Pregunta al usuario antes de enviar

    return {
        "cpu": cpu,
        "ram": ram,
        "bateria": bateria,
        "enchufado": enchufado,
        "decision": decision
    }


# ── MODELOS DE DATOS ─────────────────────────────

class MensajeEntrada(BaseModel):
    texto: str
    modelo: str = "phi3:mini"

class RespuestaTROY(BaseModel):
    respuesta: str
    modelo_usado: str
    procesado_en: str
    timestamp: str
    recursos: dict


# ── ENDPOINTS ────────────────────────────────────

@app.get("/")
def raiz():
    """Estado general de TROY Core."""
    return {
        "nombre": "TROY Core",
        "version": "0.1.0",
        "estado": "activo",
        "sistema": platform.system(),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/estado")
def estado():
    """Estado del Hipervisor en tiempo real."""
    recursos = evaluar_recursos()
    return {
        "hipervisor": recursos["decision"],
        "cpu_porcentaje": recursos["cpu"],
        "ram_porcentaje": recursos["ram"],
        "bateria_porcentaje": recursos["bateria"],
        "enchufado": recursos["enchufado"]
    }


@app.post("/chat", response_model=RespuestaTROY)
def chat(mensaje: MensajeEntrada):
    """
    Endpoint principal de conversación.
    El Hipervisor evalúa los recursos antes de procesar.
    Por ahora siempre procesa local — en versiones
    posteriores aquí se agrega el enrutamiento al Nodo.
    """
    recursos = evaluar_recursos()

    # Si el Hipervisor dice 'remoto', aún así procesamos
    # local en esta versión — en v0.2 se agrega la
    # lógica de autorización del usuario para enviar fuera
    respuesta_ollama = ollama.chat(
        model=mensaje.modelo,
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres TROY, un agente personal soberano. "
                    "Corres completamente en el dispositivo del usuario. "
                    "Sus datos nunca salen de su control. "
                    "Eres conciso, útil, y honesto."
                )
            },
            {
                "role": "user",
                "content": mensaje.texto
            }
        ]
    )

    return RespuestaTROY(
        respuesta=respuesta_ollama["message"]["content"],
        modelo_usado=mensaje.modelo,
        procesado_en="local",
        timestamp=datetime.now().isoformat(),
        recursos=recursos
    )