# ─────────────────────────────────────────────────
# TROY Core — Memoria Persistente v0.1
# Infima Foundation A.C.
# Guarda el historial de conversaciones en SQLite
# local. Nunca sale del dispositivo del usuario.
# ─────────────────────────────────────────────────

from sqlalchemy import create_engine, Column, String, Text, DateTime
from sqlalchemy.orm import DeclarativeBase, Session
from datetime import datetime
import uuid

# Base de datos local — archivo en el dispositivo
engine = create_engine("sqlite:///troy_memoria.db")

class Base(DeclarativeBase):
    pass

class Mensaje(Base):
    __tablename__ = "mensajes"

    id          = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sesion_id   = Column(String, nullable=False)
    rol         = Column(String, nullable=False)  # "user" o "assistant"
    contenido   = Column(Text, nullable=False)
    timestamp   = Column(DateTime, default=datetime.now)

# Crear la tabla si no existe
Base.metadata.create_all(engine)


def guardar_mensaje(sesion_id: str, rol: str, contenido: str):
    """Guarda un mensaje en la base de datos local."""
    with Session(engine) as session:
        mensaje = Mensaje(
            sesion_id=sesion_id,
            rol=rol,
            contenido=contenido
        )
        session.add(mensaje)
        session.commit()


def obtener_historial(sesion_id: str, limite: int = 20) -> list:
    """
    Recupera los últimos N mensajes de una sesión.
    Se usan como contexto para el siguiente mensaje.
    """
    with Session(engine) as session:
        mensajes = (
            session.query(Mensaje)
            .filter(Mensaje.sesion_id == sesion_id)
            .order_by(Mensaje.timestamp.desc())
            .limit(limite)
            .all()
        )
        # Invertir para orden cronológico
        mensajes.reverse()
        return [
            {"role": m.rol, "content": m.contenido}
            for m in mensajes
        ]


def listar_sesiones() -> list:
    """Lista todas las sesiones con su último mensaje."""
    with Session(engine) as session:
        from sqlalchemy import text
        resultado = session.execute(text("""
            SELECT sesion_id,
                   MAX(timestamp) as ultimo,
                   COUNT(*) as total_mensajes
            FROM mensajes
            GROUP BY sesion_id
            ORDER BY ultimo DESC
        """)).fetchall()
        return [
            {
                "sesion_id": r[0],
                "ultimo_mensaje": str(r[1]),
                "total_mensajes": r[2]
            }
            for r in resultado
        ]