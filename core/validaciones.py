"""Validaciones de campos, normalización y detección de duplicados."""
from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process
from unidecode import unidecode

from .config import (
    E_ANULADA, NO_APLICA, PAIS_COLOMBIA, TI_DESIGNADO, TI_NIT, TO_COLOMBIANA,
    TO_EXT_DOMICILIADA,
)

PESOS_DIAN = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def solo_digitos(v: str) -> str:
    return re.sub(r"\D", "", str(v or ""))


def digito_verificacion(nit_base: str) -> int:
    """Dígito de verificación del NIT según el algoritmo de la DIAN."""
    nit_base = solo_digitos(nit_base)
    total = sum(int(d) * PESOS_DIAN[i] for i, d in enumerate(reversed(nit_base)))
    r = total % 11
    return r if r in (0, 1) else 11 - r


def validar_nit(nit: str) -> str | None:
    """Devuelve un mensaje de error o None si el NIT es válido (10 dígitos con DV)."""
    d = solo_digitos(nit)
    if len(d) != 10:
        if len(d) == 9:
            return (f"El NIT debe tener 10 dígitos, incluido el dígito de verificación. "
                    f"Para {d} sería {d}{digito_verificacion(d)}.")
        return "El NIT debe tener 10 dígitos (9 del número + dígito de verificación)."
    base, dv = d[:9], int(d[9])
    esperado = digito_verificacion(base)
    if dv != esperado:
        return (f"El dígito de verificación no coincide: para {base} debería ser {esperado} "
                f"(NIT completo {base}{esperado}). Revisa el RUT o el RUES.")
    return None


def limpiar_texto(v: str) -> str:
    return re.sub(r"\s+", " ", str(v or "").replace("\n", " ")).strip()


def normalizar_nombre(nombre: str) -> str:
    """Para comparar nombres: sin tildes, mayúsculas, sin puntuación ni palabras genéricas."""
    s = unidecode(limpiar_texto(nombre)).upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    genericas = {"LA", "EL", "DE", "DEL", "LOS", "LAS", "Y", "S", "A", "SAS", "S A",
                 "LTDA", "THE", "OF", "AND", "FOR"}
    tokens = [t for t in s.split() if t not in genericas]
    return " ".join(tokens)


def clave_identificacion(tipo: str, ident: str) -> str:
    """Clave para comparar identificaciones; en NIT ignora el dígito de verificación."""
    d = solo_digitos(ident) if tipo == TI_NIT else re.sub(r"[^A-Za-z0-9]", "", str(ident or "")).upper()
    if tipo == TI_NIT and len(d) == 10:
        d = d[:9]
    return d


def validar_actor(a: dict) -> list[str]:
    """Reglas de la plantilla. Devuelve la lista de errores (vacía si todo está bien)."""
    err = []
    req = {
        "tipo_organizacion": "Tipo de organización", "tipo_entidad": "Tipo de entidad",
        "tipo_identificacion": "Tipo de identificación", "nombre_organizacion": "Nombre de la organización",
        "direccion": "Dirección", "continente": "Continente", "pais": "País",
        "departamento": "Departamento / estado", "municipio": "Municipio / ciudad", "email": "Correo electrónico",
    }
    for k, nombre in req.items():
        if not limpiar_texto(a.get(k)):
            err.append(f"Falta: {nombre}.")

    ti = a.get("tipo_identificacion")
    ident = limpiar_texto(a.get("identificacion"))
    if ti != TI_DESIGNADO and not ident:
        err.append("Falta: Identificación (sin puntos ni guiones).")
    if ti == TI_NIT and ident:
        e = validar_nit(ident)
        if e:
            err.append(e)
    if ti == TI_DESIGNADO and ident:
        err.append("Con 'Designado APC Colombia - GIT de TI' deja la identificación vacía: la asigna TI.")

    to = a.get("tipo_organizacion")
    pais = a.get("pais")
    if to == TO_COLOMBIANA and ti != TI_NIT:
        err.append("Una organización colombiana debe identificarse con NIT.")
    if to in (TO_COLOMBIANA, TO_EXT_DOMICILIADA) and pais and pais != PAIS_COLOMBIA:
        err.append("Una organización colombiana o domiciliada en Colombia debe tener país COLOMBIA.")

    email = limpiar_texto(a.get("email"))
    if email and not EMAIL_RE.match(email):
        err.append("El correo electrónico no tiene un formato válido.")

    fijo, movil = solo_digitos(a.get("telefono_fijo")), solo_digitos(a.get("telefono_movil"))
    if not fijo and not movil:
        err.append("Registra al menos un teléfono (fijo o móvil), solo números.")
    for nombre, raw, dig in (("fijo", a.get("telefono_fijo"), fijo), ("móvil", a.get("telefono_movil"), movil)):
        if raw and dig and not (7 <= len(dig) <= 15):
            err.append(f"El teléfono {nombre} debe tener entre 7 y 15 dígitos.")
    if pais == PAIS_COLOMBIA and a.get("departamento") == NO_APLICA:
        err.append("Para Colombia selecciona el departamento.")
    return err


def buscar_duplicados(nombre: str, tipo_id: str, ident: str, solicitudes: pd.DataFrame,
                      actores_ciclope: pd.DataFrame | None = None, excluir_radicado: str = "",
                      umbral: int = 88) -> pd.DataFrame:
    """Busca coincidencias exactas de identificación y aproximadas de nombre.

    Devuelve un DataFrame con: fuente, nombre, identificacion, estado, radicado, coincidencia, puntaje.
    """
    filas = []
    clave = clave_identificacion(tipo_id, ident) if ident else ""
    nom = normalizar_nombre(nombre) if nombre else ""

    def revisar(df, fuente, col_nom, col_id, col_tipo=None, col_estado=None, col_rad=None):
        if df is None or df.empty:
            return
        df = df.copy()
        if col_rad and excluir_radicado:
            df = df[df[col_rad] != excluir_radicado]
        if col_estado:
            df = df[df[col_estado] != E_ANULADA]
        if df.empty:
            return
        if clave and len(clave) >= 4:
            tipos = df[col_tipo] if col_tipo else pd.Series([TI_NIT] * len(df), index=df.index)
            claves = [clave_identificacion(t, i) for t, i in zip(tipos, df[col_id])]
            claves_alt = [clave_identificacion("", i) for i in df[col_id]]
            for idx, c, c2 in zip(df.index, claves, claves_alt):
                if c == clave or c2 == clave or (len(c2) == 10 and c2[:9] == clave):
                    filas.append(_fila(df.loc[idx], fuente, col_nom, col_id, col_estado, col_rad,
                                       "Misma identificación", 100))
        if nom and len(nom) >= 3:
            nombres = df[col_nom].map(normalizar_nombre)
            res = process.extract(nom, nombres.to_dict(), scorer=fuzz.token_sort_ratio,
                                  limit=5, score_cutoff=umbral)
            for _, puntaje, idx in res:
                filas.append(_fila(df.loc[idx], fuente, col_nom, col_id, col_estado, col_rad,
                                   "Nombre parecido", round(puntaje)))

    revisar(solicitudes, "Solicitudes", "nombre_organizacion", "identificacion",
            "tipo_identificacion", "estado", "radicado")
    revisar(actores_ciclope, "Base CICLOPE", "nombre", "identificacion")
    if not filas:
        return pd.DataFrame(columns=["fuente", "nombre", "identificacion", "estado",
                                     "radicado", "coincidencia", "puntaje"])
    out = pd.DataFrame(filas).sort_values("puntaje", ascending=False)
    return out.drop_duplicates(subset=["fuente", "nombre", "identificacion", "radicado"])


def _fila(r, fuente, col_nom, col_id, col_estado, col_rad, tipo, puntaje):
    return {
        "fuente": fuente, "nombre": r.get(col_nom, ""), "identificacion": r.get(col_id, ""),
        "estado": r.get(col_estado, "") if col_estado else "Registrado",
        "radicado": r.get(col_rad, "") if col_rad else "", "coincidencia": tipo, "puntaje": puntaje,
    }
