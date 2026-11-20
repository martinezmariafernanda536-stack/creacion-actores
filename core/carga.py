"""Cruce de una carga masiva con lo que ya está en el sistema.

- Los actores que no existen se agregan como nuevos.
- Los que ya existen (por identificación o, si no tienen, por nombre) pueden actualizarse: solo se cambian los
  datos de la plantilla que vienen llenos en el Excel y son distintos. Una celda vacía nunca borra un dato.
- El estado, los responsables, los códigos y las fechas del flujo nunca se tocan desde una carga masiva.
"""
from __future__ import annotations

import pandas as pd

from .config import E_ANULADA
from .validaciones import clave_identificacion, limpiar_texto, normalizar_nombre

# Datos de la plantilla que una carga masiva puede actualizar, en el orden en que se muestran
CAMPOS_ACTUALIZABLES = {
    "nombre_organizacion": "Nombre", "tipo_organizacion": "Tipo de organización", "tipo_entidad": "Tipo de entidad",
    "tipo_identificacion": "Tipo de identificación", "identificacion": "Identificación",
    "continente": "Continente", "pais": "País", "departamento": "Departamento / estado",
    "municipio": "Municipio / ciudad", "direccion": "Dirección", "email": "Correo",
    "telefono_fijo": "Teléfono fijo", "telefono_movil": "Teléfono móvil",
}


def _clave(fila: dict) -> str:
    if fila.get("identificacion"):
        return "I:" + clave_identificacion(fila.get("tipo_identificacion", ""), fila["identificacion"])
    return "N:" + normalizar_nombre(fila.get("nombre_organizacion", ""))


def _igual(a, b) -> bool:
    return limpiar_texto(a).upper() == limpiar_texto(b).upper()


def cruzar_carga(filas: list[dict], existentes: pd.DataFrame):
    """Devuelve (nuevas, actualizaciones, sin_cambios, repetidas_en_archivo).

    actualizaciones: lista de dicts con radicado, nombre, estado actual y cambios {campo: [antes, ahora]}.
    """
    vivos = existentes[existentes["estado"] != E_ANULADA] if not existentes.empty else existentes
    por_clave: dict[str, dict] = {}
    if not vivos.empty:
        orden = vivos.sort_values("fecha_actualizacion")  # si hay varios, gana el más reciente
        for r in orden.to_dict("records"):
            if r.get("identificacion"):
                por_clave["I:" + clave_identificacion(r.get("tipo_identificacion", ""), r["identificacion"])] = r
            if r.get("nombre_organizacion"):
                por_clave["N:" + normalizar_nombre(r["nombre_organizacion"])] = r
    nuevas, actualizaciones, sin_cambios, repetidas = [], [], [], []
    vistas: set[str] = set()
    for f in filas:
        c = _clave(f)
        if c in vistas:
            repetidas.append(f)
            continue
        vistas.add(c)
        actual = por_clave.get(c)
        if actual is None:
            nuevas.append(f)
            continue
        cambios = {k: [str(actual.get(k, "")), limpiar_texto(f.get(k, ""))] for k in CAMPOS_ACTUALIZABLES
                   if limpiar_texto(f.get(k, "")) and not _igual(actual.get(k, ""), f.get(k, ""))}
        if cambios:
            actualizaciones.append({"radicado": actual["radicado"], "lote": actual.get("lote", ""),
                                    "nombre": actual.get("nombre_organizacion", ""),
                                    "estado": actual.get("estado", ""), "cambios": cambios})
        else:
            sin_cambios.append(f)
    return nuevas, actualizaciones, sin_cambios, repetidas


def tabla_cambios(actualizaciones: list[dict]) -> pd.DataFrame:
    """Una fila por dato que cambia, para revisarlo antes de guardar."""
    return pd.DataFrame([
        {"Actor": a["nombre"], "Radicado": a["radicado"], "Estado": a["estado"],
         "Dato": CAMPOS_ACTUALIZABLES[k], "Antes": antes or "—", "Ahora": ahora}
        for a in actualizaciones for k, (antes, ahora) in a["cambios"].items()
    ])
