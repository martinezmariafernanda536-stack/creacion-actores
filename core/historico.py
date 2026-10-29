"""Lee la plantilla Excel actual y normaliza sus filas para cargarlas como histórico."""
from __future__ import annotations

import warnings
from datetime import datetime

import openpyxl
from unidecode import unidecode

from .catalogos import cargar_paises
from .config import (
    APP_AMBOS, APLICATIVOS, E_CREADO, E_PEND_CICLOPE, E_REVISION, E_SOLICITADA, TI_DESIGNADO,
    TI_NIT, TIPOS_ENTIDAD, TO_COLOMBIANA, TO_EXT_DOMICILIADA, TO_EXT_NO_DOMICILIADA,
)
from .validaciones import limpiar_texto, solo_digitos

ALIAS_PAIS = {
    "PAISES BAJOS": "HOLANDA", "NETHERLANDS": "HOLANDA",
    "ESTADOS UNIDOS": "ESTADOS UNIDOS DE AMERICA", "USA": "ESTADOS UNIDOS DE AMERICA",
    "UK": "REINO UNIDO", "INGLATERRA": "REINO UNIDO",
}
MAPA_ESTADO = {
    "creado": E_CREADO, "en revision": E_REVISION, "pendiente en ciclope": E_PEND_CICLOPE,
    "pendiente en hermes": E_SOLICITADA, "pendiente en ambos sistemas": E_SOLICITADA,
    "solicitud realizada": E_SOLICITADA, "itop en tramite": "Itop en trámite",
}


def _k(s):
    return unidecode(limpiar_texto(s)).upper()


def leer_historico(ruta_excel, prefijo: str = "HIST", lote: str = "HISTORICO",
                   origen: str = "Plantilla Excel") -> list[dict]:
    paises = cargar_paises()
    pais_por_clave = {_k(p): p for p in paises["pais"]}
    cont_por_pais = dict(zip(paises["pais"], paises["continente"]))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(ruta_excel, read_only=True, data_only=True)
    ws = wb["Organización"]
    filas = []
    for n, r in enumerate(ws.iter_rows(min_row=8, max_row=5000, max_col=17, values_only=True)):
        r = list(r) + [None] * (17 - len(r))
        if not limpiar_texto(r[8]):
            continue
        val = lambda i: "" if r[i] in (None, "#VALUE!") else limpiar_texto(r[i])  # noqa: E731

        fecha = r[1]
        fecha = fecha.strftime("%Y-%m-%d 00:00:00") if isinstance(fecha, datetime) else ""

        to = val(4).lower()
        if "no domici" in to:
            tipo_org = TO_EXT_NO_DOMICILIADA
        elif "domici" in to:
            tipo_org = TO_EXT_DOMICILIADA
        elif "colombiana" in to:
            tipo_org = TO_COLOMBIANA
        else:
            tipo_org = val(4)

        te = val(5).lower()
        tipo_ent = next((t for t, clave in zip(TIPOS_ENTIDAD, ("blica", "rivada", "ixta")) if clave in te), val(5))

        ti = val(6)
        if "signado" in ti.lower():
            ti = TI_DESIGNADO
        ident = val(7)
        if ti == TI_NIT:
            ident = solo_digitos(ident)

        pais_raw = _k(val(11))
        pais_raw = ALIAS_PAIS.get(pais_raw, pais_raw)
        pais = pais_por_clave.get(pais_raw, val(11).upper())
        continente = cont_por_pais.get(pais) or {
            "SUDAMERICA": "Sudamérica", "AMERICA DEL NORTE": "América del Norte",
        }.get(_k(val(10)), val(10))

        app = val(2) if val(2) in APLICATIVOS else APP_AMBOS
        estado = MAPA_ESTADO.get(unidecode(val(3)).lower(), E_SOLICITADA)

        filas.append({
            "radicado": f"{prefijo}-{len(filas) + 1:04d}", "lote": lote,
            "fecha_solicitud": fecha, "solicitante": val(0) or "Sin registro", "correo_solicitante": "",
            "existe_en_hermes": "", "referencia_hermes_existente": "",
            "aplicativo": app, "estado": estado,
            "tipo_organizacion": tipo_org, "tipo_entidad": tipo_ent, "tipo_identificacion": ti,
            "identificacion": ident, "nombre_organizacion": val(8), "direccion": val(9),
            "continente": continente, "pais": pais, "departamento": val(12), "municipio": val(13),
            "email": val(14), "telefono_fijo": val(15), "telefono_movil": val(16),
            "fuente_dato": "", "observaciones_solicitante": "",
            "fecha_actualizacion": fecha, "origen": f"{origen} (fila {n + 8})",
        })
    return filas
