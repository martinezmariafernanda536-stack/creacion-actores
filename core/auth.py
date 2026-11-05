"""Acceso con nombre de usuario + contraseña. El sistema no guarda correos electrónicos.

- La contraseña nunca se guarda: solo su huella cifrada (PBKDF2-SHA256, 120.000 iteraciones,
  con una sal secreta + el usuario).
- Política: mínimo 10 caracteres, con mayúscula, minúscula, número y carácter especial.
- Bloqueo: 5 intentos fallidos bloquean el usuario 15 minutos (queda registrado en la hoja).
- Las contraseñas temporales (usuario nuevo o restablecido) obligan a crear una propia al entrar.
- Migración: las cuentas creadas con la versión anterior (identificadas por correo) se convierten
  a nombre de usuario la primera vez que la persona ingresa, y el correo se borra de la hoja.
"""
from __future__ import annotations

import hashlib
import re
import secrets as _secrets
from datetime import datetime, timedelta

import pandas as pd

from .config import ROL_SOLICITANTE, TAB_USUARIOS
from .flujo import TZ

MIN_LARGO = 10
MAX_INTENTOS = 5
MINUTOS_BLOQUEO = 15
MENSAJE_GENERICO = "El usuario o la contraseña no coinciden, o el usuario está inactivo."
USUARIO_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")


def normalizar_usuario(v: str) -> str:
    return str(v or "").strip().lower()


def usuario_desde_correo(correo: str) -> str:
    """ngomez@apccolombia.gov.co -> ngomez (solo para convertir cuentas antiguas)."""
    return re.sub(r"[^a-z0-9._-]", "", str(correo or "").split("@")[0].lower())


def error_usuario(usuario: str) -> str | None:
    if not USUARIO_RE.match(normalizar_usuario(usuario)):
        return ("El usuario debe tener entre 3 y 30 caracteres: letras minúsculas sin tildes, números, punto, "
                "guion o guion bajo, sin espacios. Ejemplo: ngomez")
    return None


def hash_clave(clave: str, identidad: str, sal: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", str(clave).encode(), (sal + identidad.lower().strip()).encode(), 120_000)
    return dk.hex()


def _identidad_hash(fila: dict) -> str:
    """Cuentas antiguas: el hash se calculó con el correo. Cuentas nuevas: con el usuario."""
    correo = str(fila.get("correo") or "").strip()
    return correo if correo else normalizar_usuario(fila.get("usuario"))


def errores_clave(clave: str, usuario: str = "") -> list[str]:
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
    u = normalizar_usuario(usuario).split("@")[0]
    if u and len(u) >= 4 and u in clave.lower():
        err.append("No debe contener tu nombre de usuario.")
    return err


def generar_clave_temporal() -> str:
    """12 caracteres con todos los tipos exigidos, sin caracteres que se confunden (0/O, 1/l/I)."""
    may, minu, num, esp = "ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789", "!@#$%&*?-"
    base = [_secrets.choice(may), _secrets.choice(minu), _secrets.choice(num), _secrets.choice(esp)]
    base += [_secrets.choice(may + minu + num + esp) for _ in range(8)]
    _secrets.SystemRandom().shuffle(base)
    return "".join(base)


def _ahora() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def _fecha(v: str):
    try:
        return datetime.strptime(str(v), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _buscar(usuarios: pd.DataFrame, ingreso: str):
    """Encuentra la fila por usuario. Para cuentas antiguas acepta también el correo o su parte inicial."""
    ingreso = normalizar_usuario(ingreso)
    if not ingreso or usuarios.empty:
        return None, None
    col_u = usuarios["usuario"].fillna("").str.lower().str.strip() if "usuario" in usuarios else None
    if col_u is not None and (col_u == ingreso).any():
        return usuarios[col_u == ingreso].iloc[0].to_dict(), "usuario"
    if "correo" in usuarios:
        correos = usuarios["correo"].fillna("").str.lower().str.strip()
        coincide = (correos != "") & ((correos == ingreso) | (correos.map(usuario_desde_correo) == ingreso))
        if coincide.any():
            return usuarios[coincide].iloc[0].to_dict(), "correo"
    return None, None


def _clave_fila(fila: dict, por: str) -> tuple[str, str]:
    """Columna y valor para actualizar la fila en la hoja."""
    return ("usuario", normalizar_usuario(fila["usuario"])) if por == "usuario" else ("correo", fila["correo"])


def autenticar(store, usuarios: pd.DataFrame, ingreso: str, clave: str, sal: str) -> tuple[dict | None, str]:
    """Devuelve (usuario, "") si entra, o (None, mensaje) si no."""
    fila, por = _buscar(usuarios, ingreso)
    if fila is None or str(fila.get("activo", "SI")).upper() != "SI":
        return None, MENSAJE_GENERICO
    col, llave = _clave_fila(fila, por)

    bloqueo = _fecha(fila.get("bloqueado_hasta", ""))
    if bloqueo and bloqueo > _ahora():
        minutos = max(1, int((bloqueo - _ahora()).total_seconds() // 60) + 1)
        return None, (f"Este usuario está bloqueado por demasiados intentos fallidos. Intenta de nuevo en "
                      f"{minutos} minuto(s) o pide al administrador que restablezca tu contraseña.")

    if not _secrets.compare_digest(str(fila.get("pin_hash", "")), hash_clave(clave, _identidad_hash(fila), sal)):
        intentos = int(fila.get("intentos_fallidos") or 0) + 1
        if intentos >= MAX_INTENTOS:
            hasta = (_ahora() + timedelta(minutes=MINUTOS_BLOQUEO)).strftime("%Y-%m-%d %H:%M:%S")
            store.update(TAB_USUARIOS, col, llave, {"intentos_fallidos": 0, "bloqueado_hasta": hasta})
            return None, f"Demasiados intentos fallidos. El usuario quedó bloqueado {MINUTOS_BLOQUEO} minutos."
        store.update(TAB_USUARIOS, col, llave, {"intentos_fallidos": intentos})
        return None, f"{MENSAJE_GENERICO} Te quedan {MAX_INTENTOS - intentos} intento(s) antes del bloqueo."

    usuario = normalizar_usuario(fila.get("usuario")) or usuario_desde_correo(fila.get("correo"))
    upd = {"intentos_fallidos": 0, "bloqueado_hasta": "", "ultimo_ingreso": _ahora().strftime("%Y-%m-%d %H:%M:%S")}
    if str(fila.get("correo") or "").strip():
        # Cuenta antigua: se pasa a usuario y se borra el correo de la hoja
        upd.update({"usuario": usuario, "pin_hash": hash_clave(clave, usuario, sal), "correo": ""})
    store.update(TAB_USUARIOS, col, llave, upd)
    resultado = {"usuario": usuario, "nombre": fila["nombre"], "roles": _roles(fila)}
    resultado["debe_cambiar"] = str(fila.get("debe_cambiar", "")).upper() == "SI" or bool(errores_clave(clave))
    return resultado, ""


def verificar_clave(usuarios: pd.DataFrame, usuario: str, clave: str, sal: str) -> bool:
    fila, _ = _buscar(usuarios, usuario)
    return fila is not None and _secrets.compare_digest(
        str(fila.get("pin_hash", "")), hash_clave(clave, _identidad_hash(fila), sal))


def _roles(u: dict) -> set:
    roles = {r.strip().lower() for r in str(u.get("roles", "")).replace(",", ";").split(";") if r.strip()}
    roles.add(ROL_SOLICITANTE)  # todos pueden solicitar
    return roles


def nuevo_usuario(store, usuario, nombre, roles: list[str], sal: str, clave: str | None = None) -> str:
    """Crea el usuario. Sin clave, genera una temporal que deberá cambiar al entrar."""
    usuario = normalizar_usuario(usuario)
    temporal = clave is None
    clave = clave or generar_clave_temporal()
    store.append(TAB_USUARIOS, [{
        "usuario": usuario, "nombre": nombre.strip(), "roles": ";".join(roles),
        "pin_hash": hash_clave(clave, usuario, sal), "activo": "SI",
        "debe_cambiar": "SI" if temporal else "NO", "intentos_fallidos": 0, "bloqueado_hasta": "",
        "ultimo_ingreso": "",
    }])
    return clave


def cambiar_clave(store, usuario, clave, sal):
    usuario = normalizar_usuario(usuario)
    store.update(TAB_USUARIOS, "usuario", usuario,
                 {"pin_hash": hash_clave(clave, usuario, sal), "debe_cambiar": "NO", "correo": ""})


def restablecer_clave(store, usuario, sal) -> str:
    """Genera una contraseña temporal, desbloquea al usuario y lo obliga a cambiarla al entrar."""
    usuario = normalizar_usuario(usuario)
    temporal = generar_clave_temporal()
    store.update(TAB_USUARIOS, "usuario", usuario, {
        "pin_hash": hash_clave(temporal, usuario, sal), "debe_cambiar": "SI",
        "intentos_fallidos": 0, "bloqueado_hasta": "", "correo": ""})
    return temporal


def usuarios_con_correo(usuarios: pd.DataFrame) -> pd.DataFrame:
    """Cuentas antiguas que aún tienen un correo guardado en la hoja."""
    if "correo" not in usuarios:
        return usuarios.iloc[0:0]
    return usuarios[usuarios["correo"].fillna("").str.strip() != ""]


def borrar_correos_pendientes(store, usuarios: pd.DataFrame, sal: str) -> list[dict]:
    """Convierte las cuentas antiguas a usuario, borra su correo y les asigna contraseña temporal."""
    resultado = []
    for _, f in usuarios_con_correo(usuarios).iterrows():
        usuario = normalizar_usuario(f.get("usuario")) or usuario_desde_correo(f["correo"])
        temporal = generar_clave_temporal()
        store.update(TAB_USUARIOS, "correo", f["correo"], {
            "usuario": usuario, "pin_hash": hash_clave(temporal, usuario, sal), "correo": "",
            "debe_cambiar": "SI", "intentos_fallidos": 0, "bloqueado_hasta": ""})
        resultado.append({"Nombre": f["nombre"], "Usuario": usuario, "Contraseña temporal": temporal})
    return resultado


def recuperar_admin(store, usuarios: pd.DataFrame, ingreso: str, nueva: str, sal: str) -> str | None:
    """Permite a un administrador fijar una contraseña nueva si conoce la frase secreta (se valida en la app).

    Devuelve un mensaje de error o None si se cambió.
    """
    fila, por = _buscar(usuarios, ingreso)
    if fila is None or "admin" not in _roles(fila):
        return "Ese usuario no existe o no es administrador."
    col, llave = _clave_fila(fila, por)
    usuario = normalizar_usuario(fila.get("usuario")) or usuario_desde_correo(fila.get("correo"))
    store.update(TAB_USUARIOS, col, llave, {
        "usuario": usuario, "pin_hash": hash_clave(nueva, usuario, sal), "correo": "", "activo": "SI",
        "debe_cambiar": "NO", "intentos_fallidos": 0, "bloqueado_hasta": ""})
    return None
