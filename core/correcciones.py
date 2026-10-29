"""Correcciones de datos de un actor después de enviada la solicitud.

Reglas:
- Si el actor aún no está creado en ningún sistema, la corrección se aplica de inmediato
  y se avisa a quien tiene la solicitud en su bandeja.
- Si ya está creado en Hermes, queda pendiente en la bandeja de Hermes; al aplicarse allí,
  pasa a Cíclope si el actor también está creado en Cíclope.
- Si solo está creado en Cíclope, queda pendiente en la bandeja de Cíclope.
"""
from __future__ import annotations

import json
import secrets as _secrets

import pandas as pd

from .config import (
    APP_AMBOS, APP_CICLOPE, COLA_HERMES, E_CREADO, E_PEND_CICLOPE, ROL_CICLOPE, ROL_HERMES,
    TAB_HISTORIAL, TAB_NOTIFICACIONES, TAB_SOLICITUDES,
)
from .flujo import _hist, ahora

C_PEND_HERMES = "Pendiente en Hermes"
C_PEND_CICLOPE = "Pendiente en Cíclope"

CAMPOS = {
    "nombre_organizacion": "Nombre", "identificacion": "Identificación", "tipo_entidad": "Tipo de entidad",
    "direccion": "Dirección", "departamento": "Departamento / estado", "municipio": "Municipio / ciudad",
    "email": "Correo", "telefono_fijo": "Teléfono fijo", "telefono_movil": "Teléfono móvil",
}


def creado_en_hermes(r: dict) -> bool:
    if r.get("fecha_creado_hermes"):
        return True
    return r.get("aplicativo") != APP_CICLOPE and (
        r.get("estado") == E_CREADO or (r.get("estado") == E_PEND_CICLOPE and r.get("aplicativo") == APP_AMBOS))


def creado_en_ciclope(r: dict) -> bool:
    if r.get("fecha_creado_ciclope"):
        return True
    return r.get("aplicativo") in (APP_CICLOPE, APP_AMBOS) and r.get("estado") == E_CREADO


def diferencias(r: dict, nuevos: dict) -> dict:
    return {k: [str(r.get(k, "")), str(v)] for k, v in nuevos.items()
            if k in CAMPOS and str(r.get(k, "")) != str(v)}


def texto_diferencias(diff: dict) -> str:
    return "; ".join(f"{CAMPOS.get(k, k)}: «{a or '—'}» → «{b or '—'}»" for k, (a, b) in diff.items())


def leer_diff(r: dict) -> dict:
    try:
        return json.loads(r.get("correccion_detalle") or "{}")
    except json.JSONDecodeError:
        return {}


def correos_rol(usuarios: pd.DataFrame, rol: str) -> list[tuple[str, str]]:
    if usuarios.empty:
        return []
    u = usuarios[usuarios["activo"].str.upper() == "SI"]
    u = u[u["roles"].str.lower().str.contains(rol)]
    return list(zip(u["correo"], u["nombre"]))


def _aviso(correo, nombre, tipo, r, mensaje):
    return {"id": _secrets.token_hex(6), "fecha": ahora(), "correo_destino": correo, "nombre_destino": nombre,
            "tipo": tipo, "radicado": r["radicado"], "lote": r.get("lote", ""),
            "nombre_organizacion": r.get("nombre_organizacion", ""), "mensaje": mensaje,
            "estado_envio": "pendiente", "fecha_envio": ""}


def solicitar_correccion(store, r: dict, nuevos: dict, motivo: str, usuario: dict,
                         usuarios: pd.DataFrame) -> str:
    """Registra la corrección. Devuelve un texto que explica qué pasó."""
    diff = diferencias(r, nuevos)
    if not diff:
        raise ValueError("No cambiaste ningún dato.")
    ts = ahora()
    texto = texto_diferencias(diff)
    base = {"fecha_actualizacion": ts}
    if not r.get("correo_solicitante"):
        base["correo_solicitante"] = usuario["correo"]  # liga los registros históricos a quien corrige

    if creado_en_hermes(r):
        destino, rol, mensaje_final = C_PEND_HERMES, ROL_HERMES, "Quedó pendiente en la bandeja de Hermes."
    elif creado_en_ciclope(r):
        destino, rol, mensaje_final = C_PEND_CICLOPE, ROL_CICLOPE, "Quedó pendiente en la bandeja de Cíclope."
    else:
        destino = ""
        rol = ROL_HERMES if r.get("estado") in COLA_HERMES else ROL_CICLOPE
        mensaje_final = "Se aplicó de inmediato, porque el actor aún no estaba creado."

    if destino:  # el actor ya existe en un sistema: la corrección espera a que la apliquen
        upd = {**base, "correccion_estado": destino, "correccion_detalle": json.dumps(diff, ensure_ascii=False),
               "correccion_motivo": motivo, "correccion_fecha": ts}
        accion, aviso_tipo = "Corrección solicitada", "Corrección por aplicar"
        aviso_txt = f"{usuario['nombre']} pidió corregir datos de un actor ya creado. Motivo: {motivo}. Cambios: {texto}"
    else:  # aún no existe: se corrige directamente
        upd = {**base, **{k: b for k, (_, b) in diff.items()}}
        accion, aviso_tipo = "Corregida por el solicitante", "Datos corregidos"
        aviso_txt = f"{usuario['nombre']} corrigió datos de una solicitud en tu bandeja. Motivo: {motivo}. Cambios: {texto}"

    store.update(TAB_SOLICITUDES, "radicado", r["radicado"], upd)
    store.append(TAB_HISTORIAL, [_hist(r["radicado"], r.get("lote", ""), usuario["nombre"], accion,
                                       r["estado"], r["estado"], f"{motivo}. {texto}")])
    store.append(TAB_NOTIFICACIONES, [_aviso(c, n, aviso_tipo, r, aviso_txt) for c, n in correos_rol(usuarios, rol)])
    return mensaje_final


def aplicar_correccion(store, r: dict, sistema: str, usuario: dict, usuarios: pd.DataFrame) -> str:
    """Quien crea en Hermes o en Cíclope confirma que aplicó la corrección en su sistema."""
    diff = leer_diff(r)
    ts = ahora()
    upd = {"fecha_actualizacion": ts, **{k: b for k, (_, b) in diff.items()}}
    avisos = []
    if sistema == ROL_HERMES and creado_en_ciclope(r):
        upd["correccion_estado"] = C_PEND_CICLOPE
        avisos += [_aviso(c, n, "Corrección por aplicar", r,
                          f"La corrección ya se aplicó en Hermes; falta aplicarla en Cíclope. "
                          f"Cambios: {texto_diferencias(diff)}") for c, n in correos_rol(usuarios, ROL_CICLOPE)]
        resultado = "Aplicada en Hermes. Pasó a la bandeja de Cíclope."
    else:
        upd.update({"correccion_estado": "", "correccion_detalle": "", "correccion_motivo": "", "correccion_fecha": ""})
        if r.get("correo_solicitante"):
            avisos.append(_aviso(r["correo_solicitante"], r.get("solicitante", ""), "Corrección aplicada", r,
                                 f"Tu corrección quedó aplicada. Cambios: {texto_diferencias(diff)}"))
        resultado = "Corrección aplicada y cerrada."
    sist = "Hermes" if sistema == ROL_HERMES else "Cíclope"
    store.update(TAB_SOLICITUDES, "radicado", r["radicado"], upd)
    store.append(TAB_HISTORIAL, [_hist(r["radicado"], r.get("lote", ""), usuario["nombre"],
                                       f"Corrección aplicada en {sist}", r["estado"], r["estado"],
                                       texto_diferencias(diff))])
    store.append(TAB_NOTIFICACIONES, avisos)
    return resultado


def rechazar_correccion(store, r: dict, sistema: str, usuario: dict, motivo: str):
    sist = "Hermes" if sistema == ROL_HERMES else "Cíclope"
    store.update(TAB_SOLICITUDES, "radicado", r["radicado"],
                 {"fecha_actualizacion": ahora(), "correccion_estado": "", "correccion_detalle": "",
                  "correccion_motivo": "", "correccion_fecha": ""})
    store.append(TAB_HISTORIAL, [_hist(r["radicado"], r.get("lote", ""), usuario["nombre"],
                                       f"Corrección rechazada en {sist}", r["estado"], r["estado"], motivo)])
    if r.get("correo_solicitante"):
        store.append(TAB_NOTIFICACIONES, [_aviso(r["correo_solicitante"], r.get("solicitante", ""),
                                                 "Corrección rechazada", r, f"No se aplicó tu corrección. Motivo: {motivo}")])
