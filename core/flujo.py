"""Reglas del flujo: creación de solicitudes, cambios de estado, historial y avisos."""
from __future__ import annotations

import secrets as _secrets
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from .config import (
    APP_AMBOS, APP_CICLOPE, APP_HERMES, E_ANULADA, E_CREADO, E_DEVUELTA, E_ITOP,
    E_PEND_CICLOPE, E_REVISION, E_SOLICITADA, TAB_HISTORIAL, TAB_NOTIFICACIONES,
    TAB_SOLICITUDES,
)

TZ = ZoneInfo("America/Bogota")


def ahora() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def hoy() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def nuevo_lote() -> str:
    return f"L{datetime.now(TZ).strftime('%y%m%d-%H%M')}-{_secrets.token_hex(2).upper()}"


def estado_inicial(aplicativo: str) -> str:
    return E_PEND_CICLOPE if aplicativo == APP_CICLOPE else E_SOLICITADA


def pasos_ruta(aplicativo: str) -> list[str]:
    """Pasos que ve el solicitante en la línea de tiempo."""
    if aplicativo == APP_CICLOPE:
        return ["Solicitud enviada", "Creado en Cíclope"]
    if aplicativo == APP_HERMES:
        return ["Solicitud enviada", "Revisión Hermes", "Creado en Hermes"]
    return ["Solicitud enviada", "Revisión Hermes", "Creado en Hermes", "Creado en Cíclope"]


def paso_actual(row: dict) -> int:
    """Índice del último paso completado en la línea de tiempo."""
    est, app = row.get("estado"), row.get("aplicativo")
    if est == E_CREADO:
        return len(pasos_ruta(app)) - 1
    if est == E_PEND_CICLOPE:
        return 2 if app == APP_AMBOS else 0
    if est in (E_REVISION, E_ITOP):
        return 1
    return 0


# ---------------------------------------------------------------------------
def crear_solicitudes(store, actores: list[dict], usuario: dict) -> str:
    lote = nuevo_lote()
    ts = ahora()
    filas, hist = [], []
    for i, a in enumerate(actores, start=1):
        rad = f"{lote}-{i:02d}"
        est = estado_inicial(a["aplicativo"])
        fila = {**a, "radicado": rad, "lote": lote, "fecha_solicitud": ts,
                "solicitante": usuario["nombre"], "correo_solicitante": usuario["correo"],
                "estado": est, "fecha_actualizacion": ts, "origen": "Formulario"}
        filas.append(fila)
        hist.append(_hist(rad, lote, usuario["nombre"], "Solicitud creada", "", est,
                          a.get("observaciones_solicitante", "")))
    store.append(TAB_SOLICITUDES, filas)
    store.append(TAB_HISTORIAL, hist)
    return lote


def aplicar_accion(store, filas: list[dict], accion: str, usuario: dict,
                   observacion: str = "", datos: dict | None = None) -> int:
    """Aplica una acción a una o varias solicitudes. Devuelve cuántas cambiaron."""
    datos = datos or {}
    ts = ahora()
    cambios, hist, avisos = {}, [], []
    for row in filas:
        prev = row["estado"]
        upd: dict = {"fecha_actualizacion": ts}
        if accion == "tomar":
            nuevo = E_REVISION
            upd["responsable_hermes"] = usuario["nombre"]
        elif accion == "itop":
            nuevo = E_ITOP
            upd["numero_itop"] = datos.get("numero_itop", "")
            upd["responsable_hermes"] = row.get("responsable_hermes") or usuario["nombre"]
        elif accion == "creado_hermes":
            nuevo = E_PEND_CICLOPE if row["aplicativo"] == APP_AMBOS else E_CREADO
            upd.update({"codigo_hermes": datos.get("codigo_hermes", ""), "fecha_creado_hermes": ts,
                        "responsable_hermes": row.get("responsable_hermes") or usuario["nombre"]})
            if datos.get("identificacion"):
                upd["identificacion"] = datos["identificacion"]
        elif accion == "creado_ciclope":
            nuevo = E_CREADO
            upd.update({"codigo_ciclope": datos.get("codigo_ciclope", ""), "fecha_creado_ciclope": ts,
                        "responsable_ciclope": usuario["nombre"]})
        elif accion == "devolver":
            nuevo = E_DEVUELTA
            upd["observaciones_revision"] = observacion
        elif accion == "anular":
            nuevo = E_ANULADA
            upd["observaciones_revision"] = observacion
        else:
            raise ValueError(accion)
        upd["estado"] = nuevo
        cambios[row["radicado"]] = upd
        hist.append(_hist(row["radicado"], row["lote"], usuario["nombre"], ETIQUETA_ACCION[accion],
                          prev, nuevo, observacion or _resumen_datos(datos)))
        if nuevo in (E_DEVUELTA, E_CREADO, E_ANULADA) and row.get("correo_solicitante"):
            avisos.append(_aviso(row, nuevo, observacion))
    store.update_many(TAB_SOLICITUDES, "radicado", cambios)
    store.append(TAB_HISTORIAL, hist)
    store.append(TAB_NOTIFICACIONES, avisos)
    return len(cambios)


def reenviar_corregida(store, row: dict, nuevos_datos: dict, usuario: dict, comentario: str):
    """El solicitante corrige una solicitud devuelta y la reenvía a la cola que corresponde."""
    aplicativo = nuevos_datos.get("aplicativo") or row.get("aplicativo")
    ya_en_hermes = bool(row.get("fecha_creado_hermes")) or aplicativo == APP_CICLOPE
    nuevo = E_PEND_CICLOPE if ya_en_hermes else E_SOLICITADA
    upd = {**nuevos_datos, "estado": nuevo, "fecha_actualizacion": ahora()}
    if comentario:
        upd["observaciones_solicitante"] = comentario
    store.update(TAB_SOLICITUDES, "radicado", row["radicado"], upd)
    store.append(TAB_HISTORIAL, [_hist(row["radicado"], row["lote"], usuario["nombre"],
                                       "Corregida y reenviada", row["estado"], nuevo, comentario)])


ETIQUETA_ACCION = {
    "tomar": "Tomada en revisión",
    "itop": "Itop en trámite",
    "creado_hermes": "Creado en Hermes",
    "creado_ciclope": "Creado en Cíclope",
    "devolver": "Devuelta al solicitante",
    "anular": "Anulada",
}


def _hist(rad, lote, usuario, accion, prev, nuevo, obs=""):
    return {"fecha": ahora(), "radicado": rad, "lote": lote, "usuario": usuario, "accion": accion,
            "estado_anterior": prev, "estado_nuevo": nuevo, "observacion": obs}


def _aviso(row, nuevo, obs):
    textos = {
        E_DEVUELTA: f"La solicitud fue devuelta para corrección. Motivo: {obs}",
        E_CREADO: "El actor quedó creado en todos los sistemas solicitados.",
        E_ANULADA: f"La solicitud fue anulada. Motivo: {obs}",
    }
    return {"id": _secrets.token_hex(6), "fecha": ahora(), "correo_destino": row["correo_solicitante"],
            "nombre_destino": row.get("solicitante", ""), "tipo": nuevo, "radicado": row["radicado"],
            "lote": row["lote"], "nombre_organizacion": row.get("nombre_organizacion", ""),
            "mensaje": textos[nuevo], "estado_envio": "pendiente", "fecha_envio": ""}


def _resumen_datos(d: dict) -> str:
    return "; ".join(f"{k}: {v}" for k, v in d.items() if v)


def dias_sin_movimiento(df: pd.DataFrame) -> pd.Series:
    f = pd.to_datetime(df["fecha_actualizacion"].where(df["fecha_actualizacion"] != "",
                                                       df["fecha_solicitud"]), errors="coerce")
    hoy_ = pd.Timestamp(datetime.now(TZ).replace(tzinfo=None))
    return (hoy_ - f).dt.days.fillna(0).astype(int)
