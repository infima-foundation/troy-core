# ─────────────────────────────────────────────────
# TROY Core — v0.1.0
# Infima Foundation A.C.
# Agente Personal Soberano
# ─────────────────────────────────────────────────

from fastapi import FastAPI
from pydantic import BaseModel
from ollama import Client
import psutil
import platform
from datetime import datetime
import langdetect
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from memoria import guardar_mensaje, obtener_historial, listar_sesiones

ollama_client = Client(host='http://localhost:11434')

app = FastAPI(
    title="TROY Core",
    version="0.1.0",
    description="Agente Personal Soberano — Infima Foundation"
)

# ── HIPERVISOR ───────────────────────────────────
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

    if bateria is None or enchufado:
        decision = "local"
    elif bateria > 50 and cpu < 75:
        decision = "local"
    elif bateria > 20:
        decision = "nodo"
    else:
        decision = "remoto"

    return {
        "cpu": cpu,
        "ram": ram,
        "bateria": bateria,
        "enchufado": enchufado,
        "decision": decision
    }

def detectar_idioma(texto: str) -> str:
    try:
        codigo = langdetect.detect(texto)
        if codigo == "es":
            return "Spanish"
        elif codigo == "en":
            return "English"
        else:
            return "English"
    except:
        return "English"

# ── MODELOS DE DATOS ─────────────────────────────
class MensajeEntrada(BaseModel):
    texto: str
    modelo: str = "llama3.2"
    sesion_id: str = "default"

class RespuestaTROY(BaseModel):
    respuesta: str
    modelo_usado: str
    procesado_en: str
    timestamp: str
    recursos: dict

# ── ENDPOINTS ────────────────────────────────────
@app.get("/")
def raiz():
    return {
        "nombre": "TROY Core",
        "version": "0.1.0",
        "estado": "activo",
        "sistema": platform.system(),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/estado")
def estado():
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
    recursos = evaluar_recursos()

    idioma = detectar_idioma(mensaje.texto)

    historial = obtener_historial(mensaje.sesion_id)
    guardar_mensaje(mensaje.sesion_id, "user", mensaje.texto)

    mensajes = [
        {
            "role": "system",
            "content": (
                "You are TROY, a personal sovereign agent built by Infima Foundation. "
                "Your personality is warm, direct, and natural — like a trusted collaborator, not a robot. "
                f"IMPORTANT: The user is writing in {idioma}. You MUST respond in {idioma}. No exceptions. "
                "BEHAVIOR RULES: "
                "1. Only use information the user has explicitly given you in this conversation. "
                "2. Never invent names, data, organizations, or context. "
                "3. If you don't know something, ask naturally and briefly. "
                "4. Never say 'I don't have information about' — just ask or answer directly. "
                "5. Keep responses short and precise. No filler. "
                "6. Everything runs locally on the user's device. Their data never leaves their control."
            )
        }
    ]
    mensajes.extend(historial)
    mensajes.append({"role": "user", "content": mensaje.texto})

    respuesta_ollama = ollama_client.chat(
        model=mensaje.modelo,
        messages=mensajes
    )

    if hasattr(respuesta_ollama, "message"):
        texto_respuesta = respuesta_ollama.message.content
    else:
        texto_respuesta = respuesta_ollama["message"]["content"]

    guardar_mensaje(mensaje.sesion_id, "assistant", texto_respuesta)

    return RespuestaTROY(
        respuesta=texto_respuesta,
        modelo_usado=mensaje.modelo,
        procesado_en="local",
        timestamp=datetime.now().isoformat(),
        recursos=recursos
    )

@app.get("/sesiones")
def sesiones():
    return listar_sesiones()

@app.get("/historial/{sesion_id}")
def historial(sesion_id: str):
    return obtener_historial(sesion_id, limite=100)