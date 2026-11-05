"""Quita los correos electrónicos que hayan quedado guardados por versiones anteriores del sistema."""
from __future__ import annotations

from .auth import usuario_desde_correo
from .config import TAB_NOTIFICACIONES, TAB_SOLICITUDES, TAB_USUARIOS


def migrar_sin_correos(store) -> None:
    """Reemplaza correos por nombres de usuario y vacía las columnas de correo. Es seguro repetirla."""
    sol = store.read(TAB_SOLICITUDES)
    if "correo_solicitante" in sol and not sol.empty:
        pend = sol[sol["correo_solicitante"].fillna("").str.strip() != ""]
        if not pend.empty:
            store.update_many(TAB_SOLICITUDES, "radicado", {
                r["radicado"]: {"usuario_solicitante": r.get("usuario_solicitante") or usuario_desde_correo(r["correo_solicitante"]),
                                "correo_solicitante": ""}
                for _, r in pend.iterrows()})

    notif = store.read(TAB_NOTIFICACIONES)
    if "correo_destino" in notif and not notif.empty:
        pend = notif[notif["correo_destino"].fillna("").str.strip() != ""]
        if not pend.empty:
            store.update_many(TAB_NOTIFICACIONES, "id", {
                r["id"]: {"usuario_destino": r.get("usuario_destino") or usuario_desde_correo(r["correo_destino"]),
                          "correo_destino": "", "leido": r.get("leido") or "SI"}
                for _, r in pend.iterrows()})

    # Usuarios: se asigna el nombre de usuario; el correo se borra cuando la persona ingresa
    # (o cuando el administrador usa "Borrar correos pendientes"), porque su contraseña cifrada depende de él.
    usu = store.read(TAB_USUARIOS)
    if "correo" in usu and not usu.empty:
        pend = usu[(usu["correo"].fillna("").str.strip() != "") & (usu["usuario"].fillna("").str.strip() == "")]
        if not pend.empty:
            store.update_many(TAB_USUARIOS, "correo", {
                r["correo"]: {"usuario": usuario_desde_correo(r["correo"])} for _, r in pend.iterrows()})
