"""Prepara la base de datos (hoja de Google o carpeta local) por primera vez.

Uso (desde la carpeta del proyecto):

    python scripts/inicializar.py --admin-correo tu.correo@apccolombia.gov.co --admin-nombre "Tu Nombre" \
        --plantilla "Plantilla Solicitud Creación de Terceros HERMES.xlsx"

Qué hace:
  1. Crea las pestañas Solicitudes, Historial, Usuarios, Notificaciones y Actores_CICLOPE.
  2. Si se indica --plantilla y la pestaña Solicitudes está vacía, carga los actores
     históricos de la plantilla Excel (para que la alerta de duplicados funcione desde el inicio).
  3. Crea el primer usuario administrador y muestra su PIN (solo una vez).
  4. Opcional: --actores-ciclope archivo.csv (columnas nombre, identificacion) carga la base
     de actores de CICLOPE para comparar duplicados.

Lee la configuración de .streamlit/secrets.toml (backend local o gsheets).
"""
import argparse
import sys
import tomllib
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from core.auth import nuevo_usuario  # noqa: E402
from core.config import ROL_ADMIN, ROL_CICLOPE, ROL_HERMES, TAB_ACTORES_CICLOPE, TAB_SOLICITUDES, TAB_USUARIOS  # noqa: E402
from core.historico import leer_historico  # noqa: E402
from core.storage import crear_store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secrets", default=str(RAIZ / ".streamlit" / "secrets.toml"))
    ap.add_argument("--plantilla", help="Excel actual de solicitudes para cargar el histórico")
    ap.add_argument("--admin-correo")
    ap.add_argument("--admin-nombre")
    ap.add_argument("--actores-ciclope", help="CSV con columnas nombre, identificacion")
    args = ap.parse_args()

    with open(args.secrets, "rb") as f:
        secrets = tomllib.load(f)
    if secrets.get("backend", "local") == "local":
        secrets["local_folder"] = str(RAIZ / secrets.get("local_folder", "datos_local"))
    store = crear_store(secrets)

    print("1) Creando pestañas…")
    store.ensure_tabs()

    if args.plantilla:
        if store.read(TAB_SOLICITUDES).empty:
            filas = leer_historico(args.plantilla)
            store.append(TAB_SOLICITUDES, filas)
            print(f"2) Histórico cargado: {len(filas)} actores.")
        else:
            print("2) La pestaña Solicitudes ya tiene datos: no se cargó el histórico.")

    if args.actores_ciclope:
        df = pd.read_csv(args.actores_ciclope, dtype=str).fillna("")
        store.append(TAB_ACTORES_CICLOPE, df[["nombre", "identificacion"]].to_dict("records"))
        print(f"   Base CICLOPE cargada: {len(df)} actores.")

    if args.admin_correo and args.admin_nombre:
        usuarios = store.read(TAB_USUARIOS)
        if args.admin_correo.lower() in set(usuarios["correo"].str.lower()):
            print("3) El administrador ya existe.")
        else:
            pin = nuevo_usuario(store, args.admin_correo, args.admin_nombre,
                                [ROL_ADMIN, ROL_HERMES, ROL_CICLOPE], secrets["pin_salt"], "resumen")
            print(f"3) Administrador creado: {args.admin_correo}  PIN: {pin}  (guárdalo; no se vuelve a mostrar)")
    print("Listo.")


if __name__ == "__main__":
    main()
