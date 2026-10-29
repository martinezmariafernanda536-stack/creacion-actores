"""Acceso con correo + PIN. El PIN se guarda cifrado (hash), nunca en texto plano."""
from __future__ import annotations

import hashlib
import secrets as _secrets

import pandas as pd

from .config import ROL_SOLICITANTE, TAB_USUARIOS


def hash_pin(pin: str, correo: str, sal: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", str(pin).encode(), (sal + correo.lower().strip()).encode(), 120_000)
    return dk.hex()


def generar_pin() -> str:
    return f"{_secrets.randbelow(10**6):06d}"


def autenticar(usuarios: pd.DataFrame, correo: str, pin: str, sal: str) -> dict | None:
    correo = correo.lower().strip()
    u = usuarios[usuarios["correo"].str.lower().str.strip() == correo]
    if u.empty:
        return None
    u = u.iloc[0].to_dict()
    if u.get("activo", "SI").upper() != "SI":
        return None
    if not _secrets.compare_digest(u.get("pin_hash", ""), hash_pin(pin, correo, sal)):
        return None
    return usuario_desde_fila(u)


def usuario_desde_fila(u: dict) -> dict:
    roles = {r.strip().lower() for r in str(u.get("roles", "")).replace(",", ";").split(";") if r.strip()}
    roles.add(ROL_SOLICITANTE)  # todos pueden solicitar
    return {"correo": u["correo"].lower().strip(), "nombre": u["nombre"], "roles": roles}


def nuevo_usuario(store, correo, nombre, roles: list[str], sal: str, notificaciones="inmediato",
                  pin: str | None = None) -> str:
    pin = pin or generar_pin()
    store.append(TAB_USUARIOS, [{
        "correo": correo.lower().strip(), "nombre": nombre.strip(), "roles": ";".join(roles),
        "pin_hash": hash_pin(pin, correo, sal), "activo": "SI", "notificaciones": notificaciones,
    }])
    return pin


def cambiar_pin(store, correo, pin, sal):
    store.update(TAB_USUARIOS, "correo", correo.lower().strip(), {"pin_hash": hash_pin(pin, correo, sal)})
