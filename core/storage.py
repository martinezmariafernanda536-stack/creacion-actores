"""Capa de almacenamiento.

- GSheetStore: Google Sheets mediante cuenta de servicio (producción).
- LocalStore: archivos CSV en una carpeta (pruebas en el computador).

Ambas leen todo como texto, para no perder ceros a la izquierda ni
convertir NIT o teléfonos en números.
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from .config import TABS


class BaseStore:
    def read(self, tab: str) -> pd.DataFrame: ...
    def append(self, tab: str, rows: list[dict]) -> None: ...
    def update(self, tab: str, key_col: str, key: str, updates: dict) -> None: ...
    def ensure_tabs(self) -> None: ...

    def update_many(self, tab: str, key_col: str, changes: dict[str, dict]) -> None:
        for key, upd in changes.items():
            self.update(tab, key_col, key, upd)


# ---------------------------------------------------------------------------
class LocalStore(BaseStore):
    def __init__(self, folder: str | Path):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def _path(self, tab):
        return self.folder / f"{tab}.csv"

    def ensure_tabs(self):
        for tab, cols in TABS.items():
            p = self._path(tab)
            if not p.exists():
                pd.DataFrame(columns=cols).to_csv(p, index=False)
            else:
                df = pd.read_csv(p, dtype=str, keep_default_na=False)
                if any(c not in df.columns for c in cols):
                    _completar(df, tab).to_csv(p, index=False)

    def read(self, tab):
        p = self._path(tab)
        if not p.exists():
            return pd.DataFrame(columns=TABS.get(tab, []))
        return _completar(pd.read_csv(p, dtype=str, keep_default_na=False), tab)

    def append(self, tab, rows):
        if not rows:
            return
        df = self.read(tab)
        cols = list(df.columns) or TABS[tab]
        new = pd.DataFrame([{c: _s(r.get(c, "")) for c in cols} for r in rows], columns=cols)
        pd.concat([df, new], ignore_index=True).to_csv(self._path(tab), index=False)

    def update(self, tab, key_col, key, updates):
        df = self.read(tab)
        mask = df[key_col] == key
        if not mask.any():
            raise KeyError(f"No existe {key_col}={key} en {tab}")
        for k, v in updates.items():
            if k in df.columns:
                df.loc[mask, k] = _s(v)
        df.to_csv(self._path(tab), index=False)


# ---------------------------------------------------------------------------
class GSheetStore(BaseStore):
    def __init__(self, credentials: dict, sheet_id: str):
        import gspread

        self._gspread = gspread
        gc = gspread.service_account_from_dict(dict(credentials))
        self.sh = gc.open_by_key(sheet_id)
        self._ws = {}
        self._headers = {}

    def _worksheet(self, tab):
        if tab not in self._ws:
            self._ws[tab] = self.sh.worksheet(tab)
        return self._ws[tab]

    def _header(self, tab):
        if tab not in self._headers:
            self._headers[tab] = self._worksheet(tab).row_values(1)
        return self._headers[tab]

    def ensure_tabs(self):
        existentes = {w.title: w for w in self.sh.worksheets()}
        for tab, cols in TABS.items():
            if tab not in existentes:
                ws = self.sh.add_worksheet(title=tab, rows=1000, cols=len(cols))
                ws.update([cols], "A1", value_input_option="RAW")
                ws.freeze(rows=1)
            else:
                ws = existentes[tab]
                actual = ws.row_values(1)
                faltan = [c for c in cols if c not in actual]
                if faltan:  # agrega columnas nuevas al final sin tocar las existentes
                    nuevo = actual + faltan
                    if ws.col_count < len(nuevo):
                        ws.add_cols(len(nuevo) - ws.col_count)
                    ws.update([nuevo], "A1", value_input_option="RAW")

    def read(self, tab):
        vals = _reintentar(lambda: self._worksheet(tab).get_all_values())
        if not vals:
            return pd.DataFrame(columns=TABS.get(tab, []))
        header, data = vals[0], vals[1:]
        self._headers[tab] = header
        data = [fila + [""] * (len(header) - len(fila)) for fila in data]
        return _completar(pd.DataFrame(data, columns=header), tab)

    def append(self, tab, rows):
        if not rows:
            return
        header = self._header(tab)
        values = [[_s(r.get(c, "")) for c in header] for r in rows]
        # append_rows agrega al final en una sola operación: dos envíos
        # simultáneos no se pisan.
        _reintentar(lambda: self._worksheet(tab).append_rows(
            values, value_input_option="RAW", insert_data_option="INSERT_ROWS"))

    def update(self, tab, key_col, key, updates):
        self.update_many(tab, key_col, {key: updates})

    def update_many(self, tab, key_col, changes):
        ws = self._worksheet(tab)
        header = self._header(tab)
        keys = ws.col_values(header.index(key_col) + 1)
        cells = []
        for key, upd in changes.items():
            if key not in keys:
                raise KeyError(f"No existe {key_col}={key} en {tab}")
            row = keys.index(key) + 1
            for k, v in upd.items():
                if k in header:
                    cells.append(self._gspread.Cell(row, header.index(k) + 1, _s(v)))
        if cells:
            _reintentar(lambda: ws.update_cells(cells, value_input_option="RAW"))


# ---------------------------------------------------------------------------
def _completar(df: pd.DataFrame, tab: str) -> pd.DataFrame:
    """Agrega como vacías las columnas nuevas que aún no existen en datos guardados antes."""
    for c in TABS.get(tab, []):
        if c not in df.columns:
            df[c] = ""
    return df


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    return str(v)


def _reintentar(fn, intentos=4):
    """Reintenta ante límites de cuota de la API de Google (error 429)."""
    for i in range(intentos):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if "429" in str(e) and i < intentos - 1:
                time.sleep(2 ** i * 3)
                continue
            raise


def diagnosticar_conexion(secrets) -> list[tuple[str, bool, str]]:
    """Prueba la conexión con Google paso a paso y explica en lenguaje simple qué falla."""
    import json

    pasos = []
    try:
        cred_info = json.loads(secrets["gcp_json"]) if "gcp_json" in secrets else dict(secrets["gcp_service_account"])
        correo = cred_info.get("client_email", "")
        pasos.append(("Llave (GCP_JSON)", True,
                      f"Se leyó bien. Proyecto: {cred_info.get('project_id', '?')}. "
                      f"Correo de la cuenta de servicio: {correo}"))
    except Exception as e:  # noqa: BLE001
        return [("Llave (GCP_JSON)", False, f"No se pudo leer el contenido del JSON ({e}). Pégalo de nuevo completo.")]

    sheet_id = limpiar_sheet_id(secrets.get("sheet_id", ""))
    if not sheet_id:
        return pasos + [("ID de la hoja (SHEET_ID)", False, "La variable está vacía o no existe.")]
    pasos.append(("ID de la hoja (SHEET_ID)", True, f"Se usará: {sheet_id}"))

    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2.service_account import Credentials

        cred = Credentials.from_service_account_info(cred_info, scopes=[
            "https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        s = AuthorizedSession(cred)
    except Exception as e:  # noqa: BLE001
        return pasos + [("Autenticación", False, f"Google rechazó la llave ({e}). Crea una llave JSON nueva.")]

    def motivo(resp):
        try:
            return resp.json().get("error", {}).get("message", "")[:300]
        except Exception:  # noqa: BLE001
            return resp.text[:200]

    try:
        r = s.get(f"https://www.googleapis.com/drive/v3/files/{sheet_id}",
                  params={"fields": "id,name,mimeType", "supportsAllDrives": "true"}, timeout=30)
    except Exception as e:  # noqa: BLE001
        return pasos + [("Autenticación", False,
                         f"Google no aceptó la llave ({type(e).__name__}: {str(e)[:200]}). "
                         "Puede que la llave se haya eliminado o desactivado: crea una nueva en la cuenta de servicio.")]
    if r.status_code == 200:
        meta = r.json()
        if meta.get("mimeType") != "application/vnd.google-apps.spreadsheet":
            pasos.append(("Archivo en Drive", False,
                          f"Se encontró «{meta.get('name')}», pero no es una hoja de Google (tipo {meta.get('mimeType')}). "
                          "Ábrelo y usa Archivo → Guardar como Hojas de cálculo de Google, o crea una hoja en blanco."))
            return pasos
        pasos.append(("Archivo en Drive", True, f"Se encontró la hoja «{meta.get('name')}»."))
    elif r.status_code == 404:
        pasos.append(("Archivo en Drive", False,
                      f"La cuenta de servicio no ve la hoja. Compártela como Editor con: {correo} "
                      "(o revisa que el ID sea de esa hoja)."))
        return pasos
    elif r.status_code == 403:
        pasos.append(("Archivo en Drive", False,
                      f"Google Drive API no está habilitada en el proyecto {cred_info.get('project_id')}, "
                      f"o falta permiso. Detalle: {motivo(r)}"))
        return pasos
    else:
        pasos.append(("Archivo en Drive", False, f"Respuesta {r.status_code}: {motivo(r)}"))
        return pasos

    r = s.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
              params={"fields": "properties.title"}, timeout=30)
    if r.status_code == 200:
        pasos.append(("Google Sheets API", True, "Responde bien."))
    elif r.status_code == 403:
        pasos.append(("Google Sheets API", False,
                      f"Google Sheets API no está habilitada en el proyecto {cred_info.get('project_id')} "
                      f"o falta permiso de Editor. Detalle: {motivo(r)}"))
    else:
        pasos.append(("Google Sheets API", False, f"Respuesta {r.status_code}: {motivo(r)}"))
    return pasos


def limpiar_sheet_id(valor: str) -> str:
    """Acepta el ID o la dirección completa de la hoja, con o sin comillas y espacios."""
    import re

    v = re.sub(r"\s+", "", str(valor)).strip("'\"")  # quita espacios y saltos de línea, también internos
    m = re.search(r"/d/([A-Za-z0-9_-]+)", v)
    return m.group(1) if m else v


def crear_store(secrets) -> BaseStore:
    backend = secrets.get("backend", "local")
    if backend == "gsheets":
        if "gcp_json" in secrets:  # el JSON de la llave pegado tal cual
            import json
            credenciales = json.loads(secrets["gcp_json"])
        else:
            credenciales = secrets["gcp_service_account"]
        return GSheetStore(credenciales, limpiar_sheet_id(secrets["sheet_id"]))
    folder = secrets.get("local_folder", "datos_local")
    return LocalStore(folder)
