"""Acceso con correo + contraseña.

- La contraseña nunca se guarda: solo su huella cifrada (PBKDF2-SHA256, 120.000 iteraciones,
  con una sal secreta + el correo).
- Política: mínimo 10 caracteres, con mayúscula, minúscula, número y carácter especial.
- Bloqueo: 5 intentos fallidos bloquean el usuario 15 minutos (queda registrado en la hoja).
- Las contraseñas temporales (usuario nuevo o restablecido) obligan a crear una propia al entrar.
"""
from __future__ import annotations

import hashlib
import secrets as _secrets
from datetime import datetime, timedelta

import pandas as pd

from .config import ROL_SOLICITANTE, TAB_USUARIOS
from .flujo import TZ

MIN_LARGO = 10
MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15
ESPECIALES = "!@#$%&*()-_=+[]{};:,.?/"
MENSAJE_GENERICO = "El correo o la contraseña no coinciden, o el usuario está inactivo."


def hash_clave(clave: str, correo: str, sal: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", str(clave).encode(), (sal + correo.lower().strip()).encode(), 120_000)
    return dk.hex()


hash_pin = hash_clave  # compatibilidad con la versión anterior


def errores_clave(clave: str, correo: str = "") -> list[str]:
    err = []
    if len(clave) < MIN_LARGO:
        err.append(f"Debe tener al menos {MIN_LARGO} caracteres.")
    if not any(c.isupper() for c in clave):
        err.append("Debe tener al menos una letra mayúscula.")
    if not any(c.islower() for c in clave):
        err.append("Debe tener al menos una letra minúscula.")
    if not any(c.isdigit() for c in clave):
        err.append("Debe tener al menos un número.")
    if not any(not c.isalnum() and not c.isspace() for c in clave):
        err.append("Debe tener al menos un carácter especial, por ejemplo ! @ # $ % & * ? -")
    if any(c.isspace() for c in clave):
        err.append("No debe tener espacios.")
    usuario = correo.split("@")[0].lower() if correo else ""
    if usuario and len(usuario) >= 4 and usuario in clave.lower():
        err.append("No debe contener tu usuario de correo.")
    return err


def generar_clave_temporal() -> str:
    """12 caracteres con todos los tipos exigidos, sin caracteres que se confunden (0/O, 1/l/I)."""
    may = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    minu = "abcdefghijkmnopqrstuvwxyz"
    num = "23456789"
    esp = "!@#$%&*?-"
    base = [_secrets.choice(may), _secrets.choice(minu), _secrets.choice(num), _secrets.choice(esp)]
    todos = may + minu + num + esp
    base += [_secrets.choice(todos) for _ in range(8)]
    _secrets.SystemRandom().shuffle(base)
    return "".join(base)


def _ahora() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def _fecha(v: str):
    try:
        return datetime.strptime(str(v), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def autenticar(store, usuarios: pd.DataFrame, correo: str, clave: str, sal: str) -> tuple[dict | None, str]:
    """Devuelve (usuario, "") si entra, o (None, mensaje) si no."""
    correo = correo.lower().strip()
    filas = usuarios[usuarios["correo"].str.lower().str.strip() == correo]
    if not correo or filas.empty:
        return None, MENSAJE_GENERICO
    u = filas.iloc[0].to_dict()
    if str(u.get("activo", "SI")).upper() != "SI":
        return None, MENSAJE_GENERICO

    bloqueo = _fecha(u.get("bloqueado_hasta", ""))
    if bloqueo and bloqueo > _ahora():
        minutos = max(1, int((bloqueo - _ahora()).total_seconds() // 60) + 1)
        return None, (f"Este usuario está bloqueado por demasiados intentos fallidos. "
                      f"Intenta de nuevo en {minutos} minuto(s) o pide al administrador que restablezca tu contraseña.")

    if not _secrets.compare_digest(str(u.get("pin_hash", "")), hash_clave(clave, correo, sal)):
        intentos = int(u.get("intentos_fallidos") or 0) + 1
        if intentos >= MAX_INTENTOS:
            hasta = (_ahora() + timedelta(minutes=MINUTOS_BLOQUEO)).strftime("%Y-%m-%d %H:%M:%S")
            store.update(TAB_USUARIOS, "correo", correo, {"intentos_fallidos": 0, "bloqueado_hasta": hasta})
            return None, (f"Demasiados intentos fallidos. El usuario quedó bloqueado {MINUTOS_BLOQUEO} minutos.")
        store.update(TAB_USUARIOS, "correo", correo, {"intentos_fallidos": intentos})
        restantes = MAX_INTENTOS - intentos
        return None, f"{MENSAJE_GENERICO} Te quedan {restantes} intento(s) antes del bloqueo."

    store.update(TAB_USUARIOS, "correo", correo, {
        "intentos_fallidos": 0, "bloqueado_hasta": "", "ultimo_ingreso": _ahora().strftime("%Y-%m-%d %H:%M:%S")})
    usuario = usuario_desde_fila(u)
    # Obliga a cambiarla si es temporal o si no cumple la política (p. ej. un PIN antiguo de 6 dígitos)
    usuario["debe_cambiar"] = str(u.get("debe_cambiar", "")).upper() == "SI" or bool(errores_clave(clave))
    return usuario, ""


def verificar_clave(usuarios: pd.DataFrame, correo: str, clave: str, sal: str) -> bool:
    correo = correo.lower().strip()
    filas = usuarios[usuarios["correo"].str.lower().str.strip() == correo]
    return (not filas.empty) and _secrets.compare_digest(
        str(filas.iloc[0].get("pin_hash", "")), hash_clave(clave, correo, sal))


def usuario_desde_fila(u: dict) -> dict:
    roles = {r.strip().lower() for r in str(u.get("roles", "")).replace(",", ";").split(";") if r.strip()}
    roles.add(ROL_SOLICITANTE)  # todos pueden solicitar
    return {"correo": u["correo"].lower().strip(), "nombre": u["nombre"], "roles": roles}


def nuevo_usuario(store, correo, nombre, roles: list[str], sal: str, notificaciones="inmediato",
                  clave: str | None = None, pin: str | None = None) -> str:
    """Crea el usuario. Sin clave, genera una temporal que deberá cambiar al entrar."""
    clave = clave or pin
    temporal = clave is None
    clave = clave or generar_clave_temporal()
    store.append(TAB_USUARIOS, [{
        "correo": correo.lower().strip(), "nombre": nombre.strip(), "roles": ";".join(roles),
        "pin_hash": hash_clave(clave, correo, sal), "activo": "SI", "notificaciones": notificaciones,
        "debe_cambiar": "SI" if temporal else "NO", "intentos_fallidos": 0, "bloqueado_hasta": "",
        "ultimo_ingreso": "",
    }])
    return clave


def cambiar_clave(store, correo, clave, sal):
    store.update(TAB_USUARIOS, "correo", correo.lower().strip(),
                 {"pin_hash": hash_clave(clave, correo, sal), "debe_cambiar": "NO"})


cambiar_pin = cambiar_clave  # compatibilidad


def restablecer_clave(store, correo, sal) -> str:
    """Genera una contraseña temporal, desbloquea al usuario y lo obliga a cambiarla al entrar."""
    temporal = generar_clave_temporal()
    store.update(TAB_USUARIOS, "correo", correo.lower().strip(), {
        "pin_hash": hash_clave(temporal, correo, sal), "debe_cambiar": "SI",
        "intentos_fallidos": 0, "bloqueado_hasta": ""})
    return temporal


def enmascarar_correo(correo: str) -> str:
    """ngomez@apccolombia.gov.co -> n****z@apccolombia.gov.co"""
    if "@" not in str(correo):
        return str(correo)
    usuario, dominio = str(correo).split("@", 1)
    if len(usuario) <= 2:
        return f"{usuario[:1]}*@{dominio}"
    return f"{usuario[0]}{'*' * min(6, len(usuario) - 2)}{usuario[-1]}@{dominio}"
