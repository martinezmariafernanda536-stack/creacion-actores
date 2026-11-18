"""Sesión que sobrevive a una recarga, a un corte de conexión o a que la plataforma reinicie la app.

Cómo funciona:
- Al ingresar, el navegador guarda una "ficha de sesión" firmada (cookie). No contiene la contraseña:
  solo el usuario y la hora, firmados con la frase secreta (PIN_SALT) y con la huella de la contraseña.
- La ficha vence a los 30 minutos sin actividad (igual que el cierre automático) y se renueva mientras
  la persona usa el sistema.
- Cambiar o restablecer la contraseña invalida las fichas anteriores (la firma incluye su huella).
- Cerrar sesión, o el cierre por inactividad, revoca la ficha en el servidor y la borra del navegador.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pandas as pd

NOMBRE_COOKIE = "ca_sesion"
VIGENCIA_SEG = 30 * 60
RENOVAR_CADA_SEG = 5 * 60


def _firma(datos: str, huella: str, sal: str) -> str:
    return hmac.new(sal.encode(), f"{datos}|{huella}".encode(), hashlib.sha256).hexdigest()[:40]


def crear_ficha(usuario: str, huella_clave: str, sal: str, ahora: float | None = None) -> str:
    datos = f"{usuario}|{int(ahora or time.time())}"
    cuerpo = base64.urlsafe_b64encode(datos.encode()).decode().rstrip("=")
    return f"{cuerpo}.{_firma(datos, str(huella_clave)[:24], sal)}"


def leer_ficha(ficha: str, usuarios: pd.DataFrame, sal: str, ahora: float | None = None) -> str | None:
    """Devuelve el usuario si la ficha es auténtica, está vigente y la cuenta sigue activa."""
    try:
        cuerpo, firma = str(ficha).split(".", 1)
        datos = base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)).decode()
        usuario, ts = datos.rsplit("|", 1)
        ts = int(ts)
    except Exception:  # noqa: BLE001  ficha dañada o inventada
        return None
    ahora = ahora or time.time()
    if not (0 <= ahora - ts <= VIGENCIA_SEG) or usuarios.empty or "usuario" not in usuarios:
        return None
    filas = usuarios[usuarios["usuario"].fillna("").str.lower().str.strip() == usuario]
    if filas.empty:
        return None
    f = filas.iloc[0]
    if str(f.get("activo", "SI")).upper() != "SI":
        return None
    if not hmac.compare_digest(firma, _firma(datos, str(f.get("pin_hash", ""))[:24], sal)):
        return None
    return usuario


def edad_ficha(ficha: str) -> float:
    try:
        cuerpo = str(ficha).split(".", 1)[0]
        datos = base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)).decode()
        return time.time() - int(datos.rsplit("|", 1)[1])
    except Exception:  # noqa: BLE001
        return 1e9


def script_guardar(ficha: str) -> str:
    """JavaScript que guarda la ficha en el navegador (cookie de la misma página, 30 minutos)."""
    valor = json.dumps(ficha)
    return ("<script>(function(){var s=location.protocol==='https:'?'; Secure':'';"
            f"document.cookie='{NOMBRE_COOKIE}='+encodeURIComponent({valor})+'; path=/; max-age={VIGENCIA_SEG}; "
            "SameSite=Strict'+s;})();</script>")


def script_borrar() -> str:
    return (f"<script>document.cookie='{NOMBRE_COOKIE}=; path=/; max-age=0; SameSite=Strict';</script>")
