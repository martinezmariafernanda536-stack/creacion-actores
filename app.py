"""Sistema de solicitudes de creación de actores (terceros) en Hermes y Cíclope.

APC-Colombia · Dirección de Gestión de Demanda de Cooperación Internacional
"""
from __future__ import annotations

import html
import os
from datetime import datetime

import pandas as pd
import streamlit as st
from unidecode import unidecode

st.set_page_config(page_title="Creación de actores | APC-Colombia", page_icon=":material/account_tree:", layout="wide")

from core import catalogos as cat  # noqa: E402
from core.auth import autenticar, cambiar_pin, generar_pin, hash_pin, nuevo_usuario  # noqa: E402
from core.config import (  # noqa: E402
    APP_AMBOS, APP_CICLOPE, APP_HERMES, COLA_CICLOPE, COLA_HERMES, COLOR_ESTADO, DIAS_ALERTA,
    E_ANULADA, E_CREADO, E_DEVUELTA, E_SOLICITADA, ESTADOS,
    ESTADOS_ABIERTOS, NO_APLICA, PAIS_COLOMBIA, ROL_ADMIN, ROL_CICLOPE, ROL_HERMES, ROLES,
    ROLES_ETIQUETA, TAB_ACTORES_CICLOPE, TAB_HISTORIAL, TAB_SOLICITUDES, TAB_USUARIOS, TI_DESIGNADO,
    TI_NIT, TIPOS_ENTIDAD, TIPOS_IDENTIFICACION, TIPOS_ORGANIZACION, TO_COLOMBIANA,
    TO_EXT_DOMICILIADA,
)
from core.correcciones import (  # noqa: E402
    C_PEND_CICLOPE, C_PEND_HERMES, CAMPOS, aplicar_correccion, leer_diff, rechazar_correccion,
    solicitar_correccion,
)
from core.exportar import generar_excel  # noqa: E402
from core.historico import leer_historico  # noqa: E402
from core.flujo import (  # noqa: E402
    aplicar_accion, crear_solicitudes, dias_sin_movimiento, paso_actual, pasos_ruta,
    reenviar_corregida,
)
from core.storage import crear_store, diagnosticar_conexion  # noqa: E402
from core.validaciones import (  # noqa: E402
    buscar_duplicados, clave_identificacion, digito_verificacion, validar_nit, limpiar_texto, normalizar_identificacion,
    normalizar_nombre, regla_tipo_identificacion, solo_digitos, validar_actor,
)
from core.config import PLANTILLA_BASE  # noqa: E402
from core.flujo import _hist, ahora  # noqa: E402

# ---------------------------------------------------------------------------
# Configuración y datos
# ---------------------------------------------------------------------------
try:
    SECRETS = {k: st.secrets[k] for k in st.secrets}
except Exception:  # noqa: BLE001  (sin secrets.toml)
    SECRETS = {}
# En Hugging Face Spaces los secretos llegan como variables de entorno (en MAYÚSCULAS)
for _clave in ("backend", "sheet_id", "pin_salt", "gcp_json", "local_folder"):
    if _clave not in SECRETS and os.environ.get(_clave.upper()):
        SECRETS[_clave] = os.environ[_clave.upper()]
if "gcp_json" in SECRETS and "backend" not in SECRETS:
    SECRETS["backend"] = "gsheets"
SAL = SECRETS.get("pin_salt", "cambiar-esta-sal")


@st.cache_resource(show_spinner=False)
def obtener_store():
    store = crear_store(SECRETS)
    store.ensure_tabs()  # crea las pestañas que falten (solo la primera vez hace cambios)
    return store


try:
    store = obtener_store()
except Exception as e:  # noqa: BLE001
    st.error("No fue posible conectar con la hoja de Google.")
    if SECRETS.get("backend") == "gsheets":
        st.markdown("**Diagnóstico paso a paso.** El primer paso en rojo es el que hay que corregir:")
        try:
            for nombre, ok, detalle in diagnosticar_conexion(SECRETS):
                (st.success if ok else st.error)(f"**{nombre}:** {detalle}")
        except Exception as e2:  # noqa: BLE001
            st.warning(f"No se pudo completar el diagnóstico: {e2}")
        st.caption("Después de corregir algo en Google, recarga esta página. Si cambias una variable en Posit, "
                   "usa Republish para que la app la tome.")
    with st.expander("Detalle técnico del error"):
        st.code(f"{type(e).__name__}: {str(e)[:1500]}")
    st.stop()


@st.cache_data(ttl=30, show_spinner=False)
def leer(tab: str) -> pd.DataFrame:
    return store.read(tab)


def refrescar():
    leer.clear()


st.markdown("""
<style>
[data-testid="stIconMaterial"] {font-family: 'Material Symbols Rounded' !important;}
.block-container {padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1240px;}
h1, h2, h3, h4 {letter-spacing: -0.01em; color: #14284B;}
h1 {font-size: 1.75rem !important; font-weight: 600 !important;}
h3 {font-size: 1.12rem !important; font-weight: 600 !important;}
/* Encabezado de página */
.enc {border-left: 4px solid #1F4E8C; padding: 2px 0 2px 16px; margin-bottom: 1.4rem;}
.enc h1 {margin: 0; padding: 0;}
.enc p {margin: 4px 0 0 0; color: #5A6473; font-size: .95rem; max-width: 72ch;}
/* Pasos del formulario (secuencia real) */
.paso-t {display:flex; align-items:center; gap:10px; margin: 1.6rem 0 .6rem 0;}
.paso-t .n {width:26px; height:26px; border-radius:50%; background:#14284B; color:#fff; font-weight:600;
            font-size:.82rem; display:flex; align-items:center; justify-content:center; flex:none;}
.paso-t .t {font-weight:600; font-size:1.05rem; color:#14284B;}
.paso-t .d {color:#5A6473; font-size:.88rem;}
/* Indicadores */
[data-testid="stMetric"] {background:#FFFFFF; border:1px solid #DCE1E8; border-radius:6px; padding:12px 16px;}
[data-testid="stMetricLabel"] p {color:#5A6473; font-size:.85rem;}
[data-testid="stMetricValue"] {color:#14284B; font-weight:600; font-variant-numeric: tabular-nums;}
/* Estado */
.badge {display:inline-block; padding:2px 10px; border-radius:4px; font-size:.78rem; font-weight:600;
        vertical-align: middle; border:1px solid currentColor;}
/* Línea de tiempo */
.tl {display:flex; gap:0; align-items:center; flex-wrap:wrap; margin:.5rem 0 1rem 0;}
.tl .paso {display:flex; align-items:center; gap:8px; font-size:.86rem; color:#5A6473;}
.tl .punto {width:22px; height:22px; border-radius:50%; border:2px solid #C3CAD4; display:flex;
            align-items:center; justify-content:center; font-size:.72rem; font-weight:600; background:#fff;}
.tl .hecho .punto {background:#1E6B45; border-color:#1E6B45; color:#fff;}
.tl .actual .punto {border-color:#1F4E8C; color:#1F4E8C;}
.tl .hecho {color:#1E6B45;} .tl .actual {color:#1F4E8C; font-weight:600;}
.tl .linea {width:40px; height:2px; background:#C3CAD4; margin:0 8px;}
.tl .linea.hecho {background:#1E6B45;}
/* Ingreso */
.ingreso-inst {color:#5A6473; font-size:.88rem; margin-bottom: 1.6rem; line-height:1.45;}
.ingreso-tit {font-size:1.6rem; font-weight:600; color:#14284B; line-height:1.25; margin:0 0 .5rem 0;}
.ingreso-desc {color:#3A4554; font-size:.95rem; line-height:1.55; margin-bottom:1.2rem;}
/* Barra lateral */
.usuario-bloque {padding: 4px 0 8px 0;}
.usuario-bloque .nom {font-weight:600; font-size:.95rem;}
.usuario-bloque .cor, .usuario-bloque .rol {font-size:.8rem; opacity:.8;}
[data-testid="stSidebarNav"] a span {font-size: .93rem;}
header [data-testid="stToolbar"] {display:none;}
/* Colores institucionales también aquí, por si el archivo .streamlit/config.toml no se carga */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
.stApp button p, [data-testid="stSidebarNav"] span:not([data-testid="stIconMaterial"]) {font-family: 'IBM Plex Sans', sans-serif;}
[data-testid="stIconMaterial"] {font-family: 'Material Symbols Rounded' !important;}
.stApp button[kind="primary"], .stApp button[kind="primaryFormSubmit"],
.stApp [data-testid="stBaseButton-primary"], .stApp [data-testid="stBaseButton-primaryFormSubmit"] {
    background-color: #1F4E8C !important; border-color: #1F4E8C !important; color: #FFFFFF !important;}
.stApp button[kind="primary"]:hover, .stApp button[kind="primaryFormSubmit"]:hover,
.stApp [data-testid="stBaseButton-primary"]:hover, .stApp [data-testid="stBaseButton-primaryFormSubmit"]:hover {
    background-color: #14284B !important; border-color: #14284B !important;}
[data-testid="stSidebar"] {background-color: #14284B !important;}
[data-testid="stSidebar"] * {color: #E8EDF5;}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"],
[data-testid="stSidebar"] a[aria-current="page"] {background-color: #1E3863 !important;}
[data-testid="stSidebar"] button {background-color: transparent !important; border-color: #2C4673 !important;}
[data-testid="stSidebar"] hr {border-color: #2C4673 !important;}
[data-testid="stSidebar"] input {background-color: #1E3863 !important; color: #E8EDF5 !important;}
</style>
""", unsafe_allow_html=True)


def encabezado(titulo: str, descripcion: str = ""):
    d = f"<p>{html.escape(descripcion)}</p>" if descripcion else ""
    st.markdown(f"<div class='enc'><h1>{html.escape(titulo)}</h1>{d}</div>", unsafe_allow_html=True)


def paso(n: int, titulo: str, descripcion: str = ""):
    d = f"<span class='d'>{html.escape(descripcion)}</span>" if descripcion else ""
    st.markdown(f"<div class='paso-t'><span class='n'>{n}</span><span class='t'>{html.escape(titulo)}</span>{d}</div>",
                unsafe_allow_html=True)


ETIQUETAS = {
    "radicado": "Radicado", "lote": "Lote", "nombre_organizacion": "Organización",
    "tipo_identificacion": "Tipo de identificación", "identificacion": "Identificación", "pais": "País",
    "municipio": "Municipio / ciudad", "aplicativo": "Crear en", "estado": "Estado", "solicitante": "Solicitante",
    "fecha_solicitud": "Fecha de solicitud", "fecha_actualizacion": "Última actualización",
    "dias": st.column_config.NumberColumn("Días sin movimiento", format="%d"),
    "fuente": "Fuente", "nombre": "Nombre", "coincidencia": "Coincidencia",
    "puntaje": st.column_config.ProgressColumn("Similitud", min_value=0, max_value=100, format="%d"),
    "fecha": "Fecha", "usuario": "Usuario", "accion": "Acción", "estado_nuevo": "Estado resultante",
    "observacion": "Observación", "correo": "Correo", "roles": "Roles", "activo": "Activo",
    "notificaciones": "Avisos por correo",
}


def tabla(df, **kw):
    cfg = {c: ETIQUETAS[c] for c in df.columns if c in ETIQUETAS}
    cfg.update(kw.pop("column_config", {}))
    return st.dataframe(df, hide_index=True, use_container_width=True, column_config=cfg, **kw)


def badge(estado: str) -> str:
    c = COLOR_ESTADO.get(estado, "#5A6473")
    return f"<span class='badge' style='color:{c}; background:{c}14'>{html.escape(estado)}</span>"


def linea_tiempo(row: dict) -> str:
    pasos = pasos_ruta(row.get("aplicativo") or APP_AMBOS)
    est = row.get("estado")
    if est in (E_ANULADA,):
        return f"<div class='tl'>{badge(est)}</div>"
    hecho = paso_actual(row)
    partes = []
    for i, p in enumerate(pasos):
        if est == E_CREADO or i <= hecho:
            cls, simb = "hecho", "✓"
        elif i == hecho + 1 and est != E_DEVUELTA:
            cls, simb = "actual", str(i + 1)
        else:
            cls, simb = "", str(i + 1)
        if i:
            partes.append(f"<div class='linea {'hecho' if cls == 'hecho' else ''}'></div>")
        partes.append(f"<div class='paso {cls}'><div class='punto'>{simb}</div>{p}</div>")
    if est == E_DEVUELTA:
        partes.append(f"<div style='margin-left:12px'>{badge(est)}</div>")
    return f"<div class='tl'>{''.join(partes)}</div>"


def filtrar_texto(df: pd.DataFrame, texto: str, cols=("nombre_organizacion", "identificacion", "lote", "radicado")) -> pd.DataFrame:
    """Búsqueda sin distinguir mayúsculas ni tildes."""
    if not texto:
        return df
    t = unidecode(texto).lower().strip()
    base = df[list(cols)].astype(str).agg(" ".join, axis=1).map(lambda x: unidecode(x).lower())
    return df[base.str.contains(t, regex=False)]


def fila(df: pd.DataFrame, radicado: str) -> dict:
    return df[df["radicado"] == radicado].iloc[0].to_dict()


def ficha_actor(r: dict):
    st.markdown(f"<h3 style='margin:0 0 .2rem 0'>{html.escape(r['nombre_organizacion'])} &nbsp;{badge(r['estado'])}</h3>", unsafe_allow_html=True)
    st.markdown(linea_tiempo(r), unsafe_allow_html=True)
    if r.get("correccion_estado"):
        st.warning(f"Corrección {r['correccion_estado'].lower()}: {r.get('correccion_motivo') or ''}")
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"**Radicado:** {r['radicado']}  \n**Lote:** {r['lote']}  \n**Solicitante:** {r['solicitante']}  \n"
                f"**Fecha:** {r['fecha_solicitud'][:16]}")
    c2.markdown(f"**{r['tipo_identificacion']}:** {r['identificacion'] or '— (por asignar)'}  \n"
                f"**Tipo:** {r['tipo_organizacion']}  \n**Entidad:** {r['tipo_entidad']}  \n"
                f"**Aplicativo:** {r['aplicativo']}  \n**¿Existía en Hermes?:** {r.get('existe_en_hermes') or '—'}"
                + (f" ({r['referencia_hermes_existente']})" if r.get("referencia_hermes_existente") else ""))
    lugar = ", ".join(x for x in (r["municipio"], r["departamento"] if r["departamento"] != NO_APLICA else "",
                                  r["pais"].title() if r["pais"] else "", r["continente"]) if x) or "Sin registrar"
    c3.markdown(f"**Ubicación:** {lugar}  \n"
                f"**Dirección:** {r['direccion']}  \n**Correo:** {r['email']}  \n"
                f"**Teléfonos:** {r['telefono_fijo'] or '—'} / {r['telefono_movil'] or '—'}")
    extras = []
    if r.get("fuente_dato"):
        extras.append(f"**Fuente del dato:** {r['fuente_dato']}")
    if r.get("observaciones_solicitante"):
        extras.append(f"**Observaciones del solicitante:** {r['observaciones_solicitante']}")
    if r.get("numero_itop"):
        extras.append(f"**Itop:** {r['numero_itop']}")
    if r.get("codigo_hermes"):
        extras.append(f"**Código Hermes:** {r['codigo_hermes']}")
    if r.get("codigo_ciclope"):
        extras.append(f"**Código Cíclope:** {r['codigo_ciclope']}")
    if r.get("observaciones_revision"):
        extras.append(f"**Observaciones de revisión:** {r['observaciones_revision']}")
    if extras:
        st.markdown("  \n".join(extras))


def historial_de(radicado: str):
    h = leer(TAB_HISTORIAL)
    h = h[h["radicado"] == radicado].sort_values("fecha", ascending=False)
    if h.empty:
        st.caption("Sin movimientos registrados en el sistema.")
    else:
        tabla(h[["fecha", "usuario", "accion", "estado_nuevo", "observacion"]])


def mostrar_duplicados(nombre, tipo_id, ident, excluir=""):
    dup = buscar_duplicados(nombre, tipo_id, ident, leer(TAB_SOLICITUDES), leer(TAB_ACTORES_CICLOPE),
                            excluir_radicado=excluir)
    if dup.empty:
        return dup
    exactos = dup[dup["coincidencia"] == "Misma identificación"]
    if not exactos.empty:
        st.error("Ya existe un actor con esta misma identificación.")
    else:
        st.warning("Hay organizaciones con nombre parecido. Revisa que no sea la misma.")
    tabla(dup)
    return dup


# ---------------------------------------------------------------------------
# Acceso
# ---------------------------------------------------------------------------
def pantalla_login():
    _, centro, _ = st.columns([1, 1.5, 1])
    with centro:
        st.markdown("<div style='height:6vh'></div>", unsafe_allow_html=True)
        st.markdown("<div class='ingreso-inst'>Agencia Presidencial de Cooperación Internacional de Colombia<br>"
                    "Dirección de Gestión de Demanda de Cooperación Internacional</div>"
                    "<div class='ingreso-tit'>Solicitudes de creación de actores</div>"
                    "<div class='ingreso-desc'>Registra organizaciones para su creación en Hermes y Cíclope "
                    "y consulta en qué fase va cada solicitud.</div>", unsafe_allow_html=True)
        with st.form("login"):
            correo = st.text_input("Correo institucional")
            pin = st.text_input("PIN", type="password", max_chars=6)
            ok = st.form_submit_button("Ingresar", type="primary", use_container_width=True)
        if ok:
            intentos = st.session_state.get("intentos", 0)
            if intentos >= 5:
                st.error("Superaste los 5 intentos. Recarga la página e inténtalo de nuevo.")
                return
            u = autenticar(leer(TAB_USUARIOS), correo, pin, SAL)
            if u:
                st.session_state.usuario = u
                st.rerun()
            st.session_state.intentos = intentos + 1
            st.error("El correo o el PIN no coinciden, o el usuario está inactivo.")
        st.caption("Si no tienes acceso o olvidaste tu PIN, pídelo al administrador del sistema.")


def pantalla_configuracion_inicial():
    """Solo aparece mientras no exista ningún usuario: crea el administrador y carga el histórico."""
    _, centro, _ = st.columns([1, 1.8, 1])
    with centro:
        st.markdown("<div style='height:4vh'></div>", unsafe_allow_html=True)
        encabezado("Configuración inicial",
                   "Esta pantalla aparece una sola vez. Crea tu usuario de administrador y, si quieres, "
                   "carga los actores de la plantilla de Excel actual.")
        with st.form("instalacion"):
            frase = st.text_input("Frase secreta", type="password",
                                  help="La misma que escribiste en pin_salt dentro de los Secrets. "
                                       "Así se comprueba que quien configura es quien instaló la app.")
            c1, c2 = st.columns(2)
            nombre = c1.text_input("Tu nombre", help="Escríbelo igual que en la plantilla, por ejemplo Natalia Gomez.")
            correo = c2.text_input("Tu correo institucional")
            c1, c2 = st.columns(2)
            pin1 = c1.text_input("Elige un PIN de 6 dígitos", type="password", max_chars=6)
            pin2 = c2.text_input("Repite el PIN", type="password", max_chars=6)
            archivo = st.file_uploader("Plantilla de Excel con los actores actuales (opcional)", type=["xlsx"])
            enviar = st.form_submit_button("Terminar configuración", type="primary")
        if enviar:
            errores = []
            if frase != SAL:
                errores.append("La frase secreta no coincide con la de los Secrets (pin_salt).")
            if not limpiar_texto(nombre) or "@" not in correo:
                errores.append("Escribe tu nombre y un correo válido.")
            if len(solo_digitos(pin1)) != 6 or pin1 != pin2:
                errores.append("El PIN debe tener 6 dígitos y coincidir en ambos campos.")
            if errores:
                st.error("\n".join(f"- {e}" for e in errores))
                return
            with st.spinner("Configurando… puede tardar un minuto si cargas la plantilla."):
                n = 0
                if archivo is not None and leer(TAB_SOLICITUDES).empty:
                    filas = leer_historico(archivo)
                    store.append(TAB_SOLICITUDES, filas)
                    n = len(filas)
                nuevo_usuario(store, correo, limpiar_texto(nombre), [ROL_ADMIN, ROL_HERMES, ROL_CICLOPE],
                              SAL, "resumen", pin=pin1)
            refrescar()
            st.success("Listo. Se creó tu usuario" + (f" y se cargaron {n} actores históricos" if n else "")
                       + ". Ya puedes ingresar con tu correo y tu PIN.")
            st.button("Ir al ingreso", type="primary")


if leer(TAB_USUARIOS).empty:
    pantalla_configuracion_inicial()
    st.stop()

if "usuario" not in st.session_state:
    pantalla_login()
    st.stop()

USUARIO = st.session_state.usuario
ROLES_U = USUARIO["roles"]


# ---------------------------------------------------------------------------
# 1. Nueva solicitud
# ---------------------------------------------------------------------------
def pagina_nueva():
    encabezado("Nueva solicitud", "Agrega uno o varios actores y envíalos juntos: el equipo los recibe como un solo lote.")
    ss = st.session_state
    ss.setdefault("carrito", [])
    ss.setdefault("fv", 0)
    k = lambda n: f"{n}_{ss.fv}"  # noqa: E731  (claves que se reinician al agregar un actor)

    # --- Paso 1: identificación y búsqueda de duplicados
    paso(1, "Identifica la organización", "Revisamos si ya existe antes de continuar")
    c1, c2, c3 = st.columns([2.2, 1.2, 1.3])
    nombre = c1.text_input("Nombre de la organización *", key=k("nombre"),
                           help="Nombre completo, sin abreviar. La sigla puede ir entre paréntesis.")
    tipo_id = c2.selectbox("Tipo de identificación *", TIPOS_IDENTIFICACION, key=k("tipo_id"),
                           help="NIT: organizaciones colombianas o extranjeras domiciliadas en Colombia (10 dígitos "
                                "con dígito de verificación). NIE o NIF: organizaciones extranjeras no domiciliadas, "
                                "con el número de su país. Designado APC: cuando no tiene número y lo asigna TI.")
    ident = c3.text_input("Identificación (sin puntos ni guiones)", key=k("ident"),
                          disabled=tipo_id == TI_DESIGNADO,
                          help="NIT: 10 dígitos incluido el dígito de verificación.")
    if tipo_id == TI_DESIGNADO:
        st.info("El número lo asigna el GIT de TI mediante Itop. Quien crea en Hermes lo registrará.")
    elif tipo_id == TI_NIT and limpiar_texto(ident):
        d = solo_digitos(ident)
        if len(d) == 9:
            st.warning(f"Falta el dígito de verificación. Para {d} es **{digito_verificacion(d)}**: "
                       f"escribe {d}{digito_verificacion(d)}.")
        elif validar_nit(d):
            st.error(f"{validar_nit(d)} Ahora tiene {len(d)} dígito(s).")
        else:
            st.success("NIT válido: 10 dígitos y dígito de verificación correcto.")

    dup = pd.DataFrame()
    if len(limpiar_texto(nombre)) >= 3 or len(solo_digitos(ident)) >= 6:
        dup = mostrar_duplicados(nombre, tipo_id, ident)
        if dup.empty:
            st.success("No se encontraron coincidencias en las solicitudes registradas.")

    # --- Paso 2: validación previa en Hermes
    paso(2, "Validación en Hermes")
    ya_creado_sugerido = not dup.empty and (dup["estado"] == E_CREADO).any()
    if ya_creado_sugerido:
        st.info("Según las coincidencias, este actor podría estar ya creado. Verifícalo en Hermes antes de responder.")
    existe = st.radio("¿El actor ya está creado en Hermes? *", ["No", "Sí"], index=None,
                      horizontal=True, key=k("existe"))
    referencia, aplicativo = "", None
    if existe == "Sí":
        referencia = st.text_input("¿Con qué nombre o código aparece en Hermes?", key=k("ref"))
        aplicativo = APP_CICLOPE
        st.info("Como ya existe en Hermes, la solicitud irá directamente a creación en **Cíclope**.")
    elif existe == "No":
        aplicativo = st.radio("¿Dónde se debe crear? *", [APP_AMBOS, APP_HERMES], horizontal=True,
                              key=k("app"))

    # --- Paso 3: datos de la plantilla
    paso(3, "Datos de la organización", "Campos de la plantilla de creación de terceros")
    c1, c2 = st.columns(2)
    tipo_org = c1.selectbox("Tipo de organización *", TIPOS_ORGANIZACION, index=None,
                            placeholder="Selecciona…", key=k("tipo_org"))
    tipo_ent = c2.selectbox("Tipo de entidad *", TIPOS_ENTIDAD, index=None,
                            placeholder="Selecciona…", key=k("tipo_ent"))
    aviso_tipo = regla_tipo_identificacion(tipo_org, tipo_id)
    if aviso_tipo:
        st.warning(aviso_tipo + " Corrige el tipo de identificación en el paso 1 o el tipo de organización aquí.")
    en_colombia = tipo_org in (TO_COLOMBIANA, TO_EXT_DOMICILIADA)
    c1, c2, c3, c4 = st.columns(4)
    if en_colombia:
        continente, pais = "Sudamérica", PAIS_COLOMBIA
        c1.text_input("Continente", value=continente, disabled=True, key=k("cont_fijo"))
        c2.text_input("País", value=pais, disabled=True, key=k("pais_fijo"))
    else:
        conts = cat.continentes()
        continente = c1.selectbox("Continente *", conts, index=None, placeholder="Selecciona…", key=k("cont"))
        pais = c2.selectbox("País *", cat.paises_de(continente) if continente else [], index=None,
                            placeholder="Selecciona…", key=k("pais"),
                            help="Holanda y Reino Unido están en Unión Europea.")
    if pais == PAIS_COLOMBIA:
        depto = c3.selectbox("Departamento *", cat.departamentos(), index=None, placeholder="Selecciona…", key=k("dep"))
        muni = c4.selectbox("Municipio *", cat.municipios_de(depto) if depto else [], index=None,
                            placeholder="Selecciona…", key=k("mun"))
    else:
        depto = c3.text_input("Estado / provincia", value=NO_APLICA, key=k("dep_txt"))
        muni = c4.text_input("Ciudad *", key=k("ciudad"))
    direccion = st.text_input("Dirección *", key=k("dir"))
    c1, c2, c3 = st.columns([2, 1, 1])
    email = c1.text_input("Correo electrónico de la organización *", key=k("email"),
                          help="Preferiblemente institucional genérico (info@, contacto@…).")
    fijo = c2.text_input("Teléfono fijo (solo números)", key=k("fijo"))
    movil = c3.text_input("Teléfono móvil (solo números)", key=k("movil"))
    c1, c2 = st.columns(2)
    fuente = c1.text_input("Fuente del dato (URL o documento)", key=k("fuente"),
                           help="Ej.: página web de la organización, RUES, RUT.")
    obs = c2.text_input("Observaciones (opcional)", key=k("obs"))

    if st.button("Agregar a la solicitud", type="secondary"):
        actor = {
            "nombre_organizacion": limpiar_texto(nombre).upper(), "tipo_identificacion": tipo_id,
            "identificacion": normalizar_identificacion(tipo_id, ident),
            "existe_en_hermes": existe or "", "referencia_hermes_existente": limpiar_texto(referencia),
            "aplicativo": aplicativo or "", "tipo_organizacion": tipo_org or "", "tipo_entidad": tipo_ent or "",
            "continente": continente or "", "pais": pais or "", "departamento": limpiar_texto(depto),
            "municipio": limpiar_texto(muni), "direccion": limpiar_texto(direccion),
            "email": limpiar_texto(email).lower(), "telefono_fijo": solo_digitos(fijo),
            "telefono_movil": solo_digitos(movil), "fuente_dato": limpiar_texto(fuente),
            "observaciones_solicitante": limpiar_texto(obs),
        }
        errores = validar_actor(actor)
        if not existe:
            errores.insert(0, "Responde si el actor ya está creado en Hermes.")
        if not dup.empty and (dup["coincidencia"] == "Misma identificación").any():
            errores.append("Ya existe un actor con esta identificación: no se puede solicitar de nuevo.")
        if actor["identificacion"] and any(a["identificacion"] == actor["identificacion"] for a in ss.carrito):
            errores.append("Este actor ya está en la lista que vas a enviar.")
        if errores:
            st.error("Corrige lo siguiente:\n\n" + "\n".join(f"- {e}" for e in errores))
        else:
            ss.carrito.append(actor)
            ss.fv += 1
            st.toast(f"Agregado a la lista: {actor['nombre_organizacion']}")
            st.rerun()

    # --- Lista por enviar
    st.divider()
    st.subheader(f"Lista por enviar ({len(ss.carrito)})")
    if not ss.carrito:
        st.caption("Cuando agregues un actor aparecerá aquí. Puedes enviar varios en la misma solicitud.")
        return
    vista = pd.DataFrame(ss.carrito)[["nombre_organizacion", "tipo_identificacion", "identificacion",
                                       "pais", "municipio", "aplicativo"]]
    tabla(vista)
    c1, c2, _ = st.columns([1.3, 1.3, 2])
    quitar = c1.selectbox("Quitar de la lista", [""] + [a["nombre_organizacion"] for a in ss.carrito],
                          label_visibility="collapsed", format_func=lambda x: x or "Quitar un actor…")
    if quitar:
        ss.carrito = [a for a in ss.carrito if a["nombre_organizacion"] != quitar]
        st.rerun()
    if c2.button(f"Enviar solicitud ({len(ss.carrito)} actores)", type="primary", use_container_width=True):
        with st.spinner("Enviando…"):
            lote = crear_solicitudes(store, ss.carrito, USUARIO)
        ss.carrito = []
        refrescar()
        st.success(f"Solicitud enviada. Lote **{lote}**. Puedes seguirla en *Mis solicitudes*.")


# ---------------------------------------------------------------------------
# 2. Mis solicitudes (seguimiento)
# ---------------------------------------------------------------------------
def pagina_mis():
    encabezado("Mis solicitudes", "Estado de cada actor que has solicitado y lo que debes corregir.")
    df = leer(TAB_SOLICITUDES)
    mias = df[(df["correo_solicitante"].str.lower() == USUARIO["correo"]) |
              ((df["correo_solicitante"] == "") & (df["solicitante"].str.lower() == USUARIO["nombre"].lower()))]
    if mias.empty:
        st.info("No tienes solicitudes registradas.")
        return
    c = st.columns(4)
    c[0].metric("En trámite", int(mias["estado"].isin(COLA_HERMES + COLA_CICLOPE).sum()))
    c[1].metric("Devueltas", int((mias["estado"] == E_DEVUELTA).sum()))
    c[2].metric("Creadas", int((mias["estado"] == E_CREADO).sum()))
    c[3].metric("Total", len(mias))

    devueltas = mias[mias["estado"] == E_DEVUELTA]
    if not devueltas.empty:
        st.subheader("Devueltas para corrección")
        for _, r in devueltas.iterrows():
            with st.expander(f"{r['nombre_organizacion']} (radicado {r['radicado']})", expanded=True):
                st.error(f"Motivo: {r['observaciones_revision']}")
                form_correccion(r.to_dict())

    st.subheader("Seguimiento")
    c1, c2 = st.columns([1, 2])
    filtro = c1.multiselect("Estado", ESTADOS, placeholder="Todos")
    texto = c2.text_input("Buscar por nombre, identificación o lote")
    v = mias if not filtro else mias[mias["estado"].isin(filtro)]
    v = filtrar_texto(v, texto).sort_values("fecha_solicitud", ascending=False)
    if v.empty:
        st.info("Sin resultados con esos filtros.")
        return
    ev = tabla(v[["radicado", "nombre_organizacion", "aplicativo", "estado", "fecha_solicitud",
                  "fecha_actualizacion"]], on_select="rerun", selection_mode="single-row", key="tabla_mis")
    st.caption("Selecciona una fila para ver el detalle y el historial.")
    if ev.selection.rows:
        r = v.iloc[ev.selection.rows[0]].to_dict()
        with st.container(border=True):
            ficha_actor(r)
            form_solicitar_correccion(r)
            st.markdown("**Historial**")
            historial_de(r["radicado"])


def campos_editables(r: dict) -> dict:
    """Campos del actor que se pueden corregir (va dentro de un st.form)."""
    c1, c2 = st.columns(2)
    nombre = c1.text_input("Nombre", r["nombre_organizacion"])
    ident = c2.text_input("Identificación", r["identificacion"],
                          disabled=r["tipo_identificacion"] == TI_DESIGNADO and not r["identificacion"])
    c1, c2, c3 = st.columns(3)
    direccion = c1.text_input("Dirección", r["direccion"])
    email = c2.text_input("Correo", r["email"])
    tipo_ent = c3.selectbox("Tipo de entidad", TIPOS_ENTIDAD,
                            index=TIPOS_ENTIDAD.index(r["tipo_entidad"]) if r["tipo_entidad"] in TIPOS_ENTIDAD else 0)
    c1, c2, c3, c4 = st.columns(4)
    depto = c1.text_input("Departamento / estado", r["departamento"])
    muni = c2.text_input("Municipio / ciudad", r["municipio"])
    fijo = c3.text_input("Teléfono fijo", r["telefono_fijo"])
    movil = c4.text_input("Teléfono móvil", r["telefono_movil"])
    return {"nombre_organizacion": limpiar_texto(nombre).upper(),
            "identificacion": normalizar_identificacion(r["tipo_identificacion"], ident) or r["identificacion"],
            "tipo_entidad": tipo_ent, "direccion": limpiar_texto(direccion), "email": limpiar_texto(email).lower(),
            "departamento": limpiar_texto(depto), "municipio": limpiar_texto(muni),
            "telefono_fijo": solo_digitos(fijo), "telefono_movil": solo_digitos(movil)}


def errores_correccion(r: dict, nuevos: dict) -> list[str]:
    previos = set(validar_actor(r))  # problemas que el registro ya traía (p. ej. histórico incompleto)
    errores = [e for e in validar_actor({**r, **nuevos}) if e not in previos]
    if nuevos["identificacion"] and nuevos["identificacion"] != r["identificacion"]:
        d = buscar_duplicados("", r["tipo_identificacion"], nuevos["identificacion"], leer(TAB_SOLICITUDES),
                              leer(TAB_ACTORES_CICLOPE), excluir_radicado=r["radicado"])
        if not d.empty:
            errores.append("La nueva identificación ya pertenece a otro actor registrado.")
    return errores


def form_correccion(r: dict):
    """Solicitud devuelta: el solicitante corrige y la reenvía."""
    with st.form(f"corr_{r['radicado']}"):
        nuevos = campos_editables(r)
        comentario = st.text_input("Comentario sobre la corrección")
        if st.form_submit_button("Reenviar corregida", type="primary"):
            errores = errores_correccion(r, nuevos)
            if errores:
                st.error("\n".join(f"- {e}" for e in errores))
            else:
                reenviar_corregida(store, r, nuevos, USUARIO, limpiar_texto(comentario))
                refrescar()
                st.success("Reenviada.")
                st.rerun()


def tabla_cambios(r: dict):
    diff = leer_diff(r)
    if diff:
        tabla(pd.DataFrame([{"Campo": CAMPOS.get(k, k), "Dato actual": a or "—", "Corrección": b or "—"}
                            for k, (a, b) in diff.items()]))


def form_solicitar_correccion(r: dict):
    """Corrección de un actor en trámite o ya creado: se avisa a Hermes y/o Cíclope."""
    if r.get("correccion_estado"):
        st.warning(f"Hay una corrección {r['correccion_estado'].lower()}. Motivo: {r.get('correccion_motivo') or '—'}")
        tabla_cambios(r)
        return
    if r["estado"] in (E_ANULADA, E_DEVUELTA):
        return
    with st.expander("Corregir datos de este actor"):
        st.caption("Si el actor aún no está creado, la corrección se aplica de inmediato. Si ya está creado, "
                   "llega a quien crea en Hermes o en Cíclope para que la aplique, y te avisamos cuando quede lista.")
        with st.form(f"solcorr_{r['radicado']}"):
            nuevos = campos_editables(r)
            motivo = st.text_input("¿Qué se corrige y por qué? *", placeholder="Ej.: el NIT tenía un dígito errado")
            if st.form_submit_button("Enviar corrección", type="primary"):
                errores = errores_correccion(r, nuevos)
                if not motivo.strip():
                    errores.insert(0, "Escribe el motivo de la corrección.")
                if errores:
                    st.error("\n".join(f"- {e}" for e in errores))
                else:
                    try:
                        msg = solicitar_correccion(store, r, nuevos, limpiar_texto(motivo), USUARIO, leer(TAB_USUARIOS))
                    except ValueError as e:
                        st.warning(str(e))
                    else:
                        refrescar()
                        st.success(f"Corrección enviada. {msg}")


def seccion_correcciones(rol: str, df: pd.DataFrame):
    pendiente = C_PEND_HERMES if rol == ROL_HERMES else C_PEND_CICLOPE
    sistema = "Hermes" if rol == ROL_HERMES else "Cíclope"
    corr = df[df["correccion_estado"] == pendiente].sort_values("correccion_fecha")
    if corr.empty:
        return
    st.subheader(f"Correcciones por aplicar ({len(corr)})")
    st.caption(f"Actores ya creados cuyos datos cambiaron. Aplica el cambio en {sistema} y confírmalo aquí.")
    for _, fila_c in corr.iterrows():
        r = fila_c.to_dict()
        with st.expander(f"{r['nombre_organizacion']} (radicado {r['radicado']}), pedida por {r['solicitante']}"):
            st.markdown(f"**Motivo:** {r.get('correccion_motivo') or '—'}  \n"
                        f"**{r['tipo_identificacion']}:** {r['identificacion'] or '—'}"
                        + (f"  \n**Código {sistema}:** {r.get('codigo_hermes' if rol == ROL_HERMES else 'codigo_ciclope')}"
                           if r.get('codigo_hermes' if rol == ROL_HERMES else 'codigo_ciclope') else ""))
            tabla_cambios(r)
            c1, c2 = st.columns([1, 2])
            if c1.button(f"Corrección aplicada en {sistema}", key=f"ap_{rol}_{r['radicado']}", type="primary"):
                msg = aplicar_correccion(store, r, rol, USUARIO, leer(TAB_USUARIOS))
                refrescar()
                st.toast(msg)
                st.rerun()
            with c2.popover("Rechazar corrección"):
                motivo = st.text_input("Motivo del rechazo", key=f"rmot_{rol}_{r['radicado']}")
                if st.button("Rechazar", key=f"rech_{rol}_{r['radicado']}"):
                    if not motivo.strip():
                        st.error("Escribe el motivo: el solicitante lo recibirá.")
                    else:
                        rechazar_correccion(store, r, rol, USUARIO, motivo.strip())
                        refrescar()
                        st.rerun()
    st.divider()


# ---------------------------------------------------------------------------
# 3. Bandejas de trabajo (Hermes / Cíclope)
# ---------------------------------------------------------------------------
def pagina_bandeja(rol: str):
    es_hermes = rol == ROL_HERMES
    if es_hermes:
        encabezado("Bandeja de Hermes", "Solicitudes por validar y crear en Hermes, de la más antigua a la más reciente.")
    else:
        encabezado("Bandeja de Cíclope", "Actores listos para crear en Cíclope.")
    df = leer(TAB_SOLICITUDES)
    seccion_correcciones(rol, df)
    cola = df[df["estado"].isin(COLA_HERMES if es_hermes else COLA_CICLOPE)].copy()
    if cola.empty:
        st.success("No hay solicitudes pendientes en esta bandeja.")
        return
    cola["dias"] = dias_sin_movimiento(cola)

    estados_cola = COLA_HERMES if es_hermes else COLA_CICLOPE
    cols = st.columns(len(estados_cola) + 1)
    for c, e in zip(cols, estados_cola):
        c.metric(e, int((cola["estado"] == e).sum()))
    cols[-1].metric(f"Más de {DIAS_ALERTA} días", int((cola["dias"] > DIAS_ALERTA).sum()))

    c1, c2, c3 = st.columns([1.4, 1.4, 2])
    f_estado = c1.multiselect("Estado", estados_cola, placeholder="Todos")
    f_sol = c2.multiselect("Solicitante", sorted(cola["solicitante"].unique()), placeholder="Todos")
    texto = c3.text_input("Buscar (nombre, identificación, lote)")
    v = cola
    if f_estado:
        v = v[v["estado"].isin(f_estado)]
    if f_sol:
        v = v[v["solicitante"].isin(f_sol)]
    v = filtrar_texto(v, texto).sort_values(["dias", "fecha_solicitud"], ascending=[False, True]).reset_index(drop=True)
    if v.empty:
        st.info("Sin resultados con esos filtros.")
        return

    ev = tabla(
        v[["radicado", "nombre_organizacion", "tipo_identificacion", "identificacion", "pais", "aplicativo",
           "estado", "solicitante", "dias"]],
        on_select="rerun", selection_mode="multi-row", key=f"tabla_{rol}",
    )
    sel = v.iloc[ev.selection.rows] if ev.selection.rows else v.iloc[0:0]

    c1, c2 = st.columns(2)
    c1.download_button("Descargar cola en Excel (formato plantilla)", generar_excel(v),
                       file_name=f"cola_{rol}_{datetime.now():%Y%m%d}.xlsx", use_container_width=True)
    if sel.empty:
        st.caption("Selecciona una o varias filas para gestionarlas.")
        return
    c2.download_button(f"Descargar selección en Excel ({len(sel)})", generar_excel(sel),
                       file_name=f"seleccion_{rol}_{datetime.now():%Y%m%d_%H%M}.xlsx",
                       use_container_width=True, type="primary")

    filas = sel.to_dict("records")
    if len(filas) > 1:
        st.subheader(f"Acciones para {len(filas)} solicitudes")
        b = st.columns(3)
        if es_hermes:
            if b[0].button("Tomar en revisión", use_container_width=True):
                ejecutar(filas, "tomar")
            if b[1].button("Marcar creadas en Hermes", use_container_width=True):
                if any(f["tipo_identificacion"] == TI_DESIGNADO and not f["identificacion"] for f in filas):
                    st.error("Hay actores 'Designado' sin identificación asignada: gestiónalos uno a uno.")
                else:
                    ejecutar(filas, "creado_hermes")
        else:
            if b[0].button("Marcar creadas en Cíclope", use_container_width=True):
                ejecutar(filas, "creado_ciclope")
        st.caption("Para registrar códigos, devolver o anular, selecciona una sola fila.")
        return

    r = filas[0]
    with st.container(border=True):
        ficha_actor(r)
        st.markdown("**Posibles duplicados**")
        d = buscar_duplicados(r["nombre_organizacion"], r["tipo_identificacion"], r["identificacion"],
                              df, leer(TAB_ACTORES_CICLOPE), excluir_radicado=r["radicado"])
        if d.empty:
            st.caption("Sin coincidencias.")
        else:
            tabla(d)
        with st.expander("Historial"):
            historial_de(r["radicado"])

    st.subheader("Gestionar")
    if es_hermes:
        t1, t2, t3, t4 = st.tabs(["Registrar creación", "Revisión e Itop", "Devolver", "Anular"])
        with t1:
            with st.form("f_creado_h"):
                codigo = st.text_input("Código o ID asignado en Hermes (opcional)")
                ident = ""
                if r["tipo_identificacion"] == TI_DESIGNADO and not r["identificacion"]:
                    ident = st.text_input("Identificación asignada por TI *")
                destino = "Pendiente en Cíclope" if r["aplicativo"] == APP_AMBOS else "Creado"
                st.caption(f"Pasará a: **{destino}**")
                if st.form_submit_button("Registrar creación en Hermes", type="primary"):
                    if r["tipo_identificacion"] == TI_DESIGNADO and not r["identificacion"] and not ident.strip():
                        st.error("Registra la identificación asignada por TI.")
                    else:
                        ejecutar([r], "creado_hermes", datos={"codigo_hermes": codigo.strip(),
                                                               "identificacion": ident.strip()})
        with t2:
            if r["estado"] == E_SOLICITADA and st.button("Tomar en revisión"):
                ejecutar([r], "tomar")
            with st.form("f_itop"):
                itop = st.text_input("Número de Itop", r.get("numero_itop", ""))
                if st.form_submit_button("Marcar 'Itop en trámite'"):
                    ejecutar([r], "itop", datos={"numero_itop": itop.strip()})
        with t3:
            form_motivo(r, "devolver", "Devolver al solicitante")
        with t4:
            form_motivo(r, "anular", "Anular solicitud (p. ej. duplicada)")
    else:
        t1, t2, t3 = st.tabs(["Registrar creación", "Devolver", "Anular"])
        with t1:
            with st.form("f_creado_c"):
                codigo = st.text_input("Código o ID asignado en Cíclope (opcional)")
                if st.form_submit_button("Registrar creación en Cíclope", type="primary"):
                    ejecutar([r], "creado_ciclope", datos={"codigo_ciclope": codigo.strip()})
        with t2:
            form_motivo(r, "devolver", "Devolver al solicitante")
        with t3:
            form_motivo(r, "anular", "Anular solicitud")


def form_motivo(r, accion, etiqueta):
    with st.form(f"f_{accion}"):
        motivo = st.text_area("Motivo *", height=80)
        if st.form_submit_button(etiqueta):
            if not motivo.strip():
                st.error("Escribe el motivo: el solicitante lo recibirá.")
            else:
                ejecutar([r], accion, observacion=motivo.strip())


def ejecutar(filas, accion, observacion="", datos=None):
    with st.spinner("Guardando…"):
        n = aplicar_accion(store, filas, accion, USUARIO, observacion, datos)
    refrescar()
    st.toast(f"{n} solicitud(es) actualizada(s).")
    st.rerun()


# ---------------------------------------------------------------------------
# 4. Consulta general e indicadores
# ---------------------------------------------------------------------------
def pagina_consulta():
    encabezado("Consulta general", "Todas las solicitudes, incluido el histórico de la plantilla.")
    df = leer(TAB_SOLICITUDES).copy()
    df["dias"] = dias_sin_movimiento(df)
    abiertas = df[df["estado"].isin(ESTADOS_ABIERTOS)]
    c = st.columns(5)
    c[0].metric("Total registros", len(df))
    c[1].metric("Abiertas", len(abiertas))
    c[2].metric("Pendientes Hermes", int(df["estado"].isin(COLA_HERMES).sum()))
    c[3].metric("Pendientes Cíclope", int(df["estado"].isin(COLA_CICLOPE).sum()))
    c[4].metric(f"Abiertas > {DIAS_ALERTA} días", int((abiertas["dias"] > DIAS_ALERTA).sum()))

    c1, c2, c3, c4 = st.columns(4)
    f_est = c1.multiselect("Estado", ESTADOS, placeholder="Todos")
    f_app = c2.multiselect("Aplicativo", [APP_HERMES, APP_CICLOPE, APP_AMBOS], placeholder="Todos")
    f_sol = c3.multiselect("Solicitante", sorted(df["solicitante"].unique()), placeholder="Todos")
    texto = c4.text_input("Buscar")
    v = df
    if f_est:
        v = v[v["estado"].isin(f_est)]
    if f_app:
        v = v[v["aplicativo"].isin(f_app)]
    if f_sol:
        v = v[v["solicitante"].isin(f_sol)]
    v = filtrar_texto(v, texto).sort_values("fecha_solicitud", ascending=False)
    ev = tabla(v[["radicado", "nombre_organizacion", "identificacion", "pais", "aplicativo", "estado",
                  "solicitante", "fecha_solicitud", "dias"]],
               on_select="rerun", selection_mode="single-row", key="tabla_consulta")
    c1, c2 = st.columns(2)
    c1.download_button(f"Descargar Excel formato plantilla ({len(v)} filas)", generar_excel(v),
                       file_name=f"actores_{datetime.now():%Y%m%d}.xlsx", use_container_width=True)
    c2.download_button("Descargar CSV con todos los campos", v.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"actores_completo_{datetime.now():%Y%m%d}.csv", use_container_width=True)
    if ev.selection.rows:
        r = v.iloc[ev.selection.rows[0]].to_dict()
        with st.container(border=True):
            ficha_actor(r)
            historial_de(r["radicado"])

    with st.expander("Indicadores por solicitante"):
        res = df.pivot_table(index="solicitante", columns="estado", values="radicado", aggfunc="count", fill_value=0)
        st.dataframe(res, use_container_width=True)


# ---------------------------------------------------------------------------
# 5. Usuarios (administración)
# ---------------------------------------------------------------------------
def pagina_carga_masiva():
    encabezado("Carga masiva", "Sube un Excel con el formato de la plantilla de creación de terceros para "
                               "agregar varios actores de una vez.")
    st.markdown(
        "- Los datos se leen de la hoja **Organización**, desde la fila 8, con las mismas columnas de la plantilla.\n"
        "- Si la columna *Estado* dice **Creado**, el actor se registra como ya creado (histórico). "
        "Si está vacía, entra a la bandeja de Hermes como **Solicitud realizada**.\n"
        "- Los actores que ya existen en el sistema (por identificación, o por nombre si no tienen identificación) "
        "**no se cargan**, para evitar duplicados.")
    with open(PLANTILLA_BASE, "rb") as f:
        st.download_button("Descargar plantilla vacía", f.read(), file_name="plantilla_carga_masiva.xlsx")

    archivo = st.file_uploader("Excel con los actores", type=["xlsx"], key="carga_masiva")
    if archivo is None:
        return
    marca = datetime.now().strftime("%y%m%d%H%M")
    try:
        filas = leer_historico(archivo, prefijo=f"CM{marca}", lote=f"CARGA-{marca}", origen="Carga masiva")
    except KeyError:
        st.error("El archivo no tiene una hoja llamada «Organización». Usa la plantilla vacía de arriba.")
        return
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo leer el archivo: {e}")
        return
    if not filas:
        st.warning("No se encontraron actores. Revisa que los datos empiecen en la fila 8 de la hoja «Organización» "
                   "y que la columna *Nombre Organización* esté llena.")
        return

    existentes = leer(TAB_SOLICITUDES)
    existentes = existentes[existentes["estado"] != E_ANULADA]
    claves = {clave_identificacion(t, i) for t, i in zip(existentes["tipo_identificacion"], existentes["identificacion"]) if i}
    nombres = {normalizar_nombre(n) for n in existentes["nombre_organizacion"] if n}
    nuevas, duplicadas, vistas = [], [], set()
    for f_ in filas:
        if not f_["fecha_solicitud"]:
            f_["fecha_solicitud"] = f_["fecha_actualizacion"] = ahora()
        # Con identificación se compara el número; sin ella (p. ej. Designado APC), el nombre
        c = (clave_identificacion(f_["tipo_identificacion"], f_["identificacion"]) if f_["identificacion"]
             else "N:" + normalizar_nombre(f_["nombre_organizacion"]))
        repetido = c in vistas or (c in claves if not c.startswith("N:") else c[2:] in nombres)
        if repetido:
            duplicadas.append(f_)
        else:
            nuevas.append(f_)
            vistas.add(c)

    c1, c2, c3 = st.columns(3)
    c1.metric("Actores en el archivo", len(filas))
    c2.metric("Nuevos para cargar", len(nuevas))
    c3.metric("Ya existen (se omiten)", len(duplicadas))
    cols = ["nombre_organizacion", "tipo_identificacion", "identificacion", "pais", "estado", "solicitante"]
    if nuevas:
        st.subheader("Se cargarán")
        tabla(pd.DataFrame(nuevas)[cols])
    if duplicadas:
        with st.expander(f"Omitidos porque ya existen ({len(duplicadas)})"):
            tabla(pd.DataFrame(duplicadas)[cols])
    if nuevas and st.button(f"Cargar {len(nuevas)} actores", type="primary"):
        with st.spinner("Cargando…"):
            store.append(TAB_SOLICITUDES, nuevas)
            store.append(TAB_HISTORIAL, [_hist(f_["radicado"], f_["lote"], USUARIO["nombre"], "Carga masiva",
                                               "", f_["estado"], archivo.name) for f_ in nuevas])
        refrescar()
        st.success(f"Se cargaron {len(nuevas)} actores en el lote {nuevas[0]['lote']}.")


def pagina_usuarios():
    encabezado("Usuarios y permisos", "Quién puede entrar al sistema y qué puede hacer cada persona.")
    u = leer(TAB_USUARIOS)
    tabla(u.drop(columns=["pin_hash"]))

    t1, t2 = st.tabs(["Nuevo usuario", "Editar o restablecer PIN"])
    with t1:
        with st.form("nuevo_u", clear_on_submit=True):
            c1, c2 = st.columns(2)
            correo = c1.text_input("Correo institucional *")
            nombre = c2.text_input("Nombre *")
            roles = st.multiselect("Roles", ROLES, default=["solicitante"], format_func=ROLES_ETIQUETA.get)
            notif = st.selectbox("Avisos por correo", ["inmediato", "resumen", "ninguno"],
                                 help="inmediato: cada 15 min agrupados · resumen: un correo diario")
            if st.form_submit_button("Crear usuario", type="primary"):
                if not correo.strip() or not nombre.strip():
                    st.error("Correo y nombre son obligatorios.")
                elif correo.lower().strip() in set(u["correo"].str.lower()):
                    st.error("Ese correo ya existe.")
                else:
                    pin = nuevo_usuario(store, correo, nombre, roles, SAL, notif)
                    refrescar()
                    st.success(f"Usuario creado. PIN inicial: **{pin}** — compártelo de forma privada; "
                               "no se volverá a mostrar.")
    with t2:
        if u.empty:
            return
        correo = st.selectbox("Usuario", u["correo"].tolist(),
                              format_func=lambda c: f"{u.loc[u['correo'] == c, 'nombre'].iloc[0]} · {c}")
        actual = u[u["correo"] == correo].iloc[0]
        roles_act = [r for r in str(actual["roles"]).split(";") if r in ROLES]
        with st.form("edit_u"):
            roles = st.multiselect("Roles", ROLES, default=roles_act, format_func=ROLES_ETIQUETA.get)
            c1, c2 = st.columns(2)
            activo = c1.selectbox("Activo", ["SI", "NO"], index=0 if actual["activo"] == "SI" else 1)
            opciones = ["inmediato", "resumen", "ninguno"]
            notif = c2.selectbox("Avisos", opciones,
                                 index=opciones.index(actual["notificaciones"]) if actual["notificaciones"] in opciones else 0)
            if st.form_submit_button("Guardar cambios"):
                store.update(TAB_USUARIOS, "correo", correo,
                             {"roles": ";".join(roles), "activo": activo, "notificaciones": notif})
                refrescar()
                st.success("Guardado.")
                st.rerun()
        if st.button("Generar PIN nuevo para este usuario"):
            pin = generar_pin()
            store.update(TAB_USUARIOS, "correo", correo, {"pin_hash": hash_pin(pin, correo, SAL)})
            refrescar()
            st.success(f"PIN nuevo: **{pin}** — compártelo de forma privada.")


# ---------------------------------------------------------------------------
# Navegación
# ---------------------------------------------------------------------------
def bandeja_hermes():
    pagina_bandeja(ROL_HERMES)


def bandeja_ciclope():
    pagina_bandeja(ROL_CICLOPE)


secciones = {"Solicitudes": [
    st.Page(pagina_nueva, title="Nueva solicitud", icon=":material/add_circle:", url_path="nueva", default=True),
    st.Page(pagina_mis, title="Mis solicitudes", icon=":material/assignment:", url_path="mis-solicitudes"),
]}
gestion = []
if ROL_HERMES in ROLES_U:
    gestion.append(st.Page(bandeja_hermes, title="Bandeja de Hermes", icon=":material/inbox:", url_path="hermes"))
if ROL_CICLOPE in ROLES_U:
    gestion.append(st.Page(bandeja_ciclope, title="Bandeja de Cíclope", icon=":material/inbox:", url_path="ciclope"))
if ROLES_U & {ROL_HERMES, ROL_CICLOPE, ROL_ADMIN}:
    gestion.append(st.Page(pagina_consulta, title="Consulta general", icon=":material/table_view:", url_path="consulta"))
if gestion:
    secciones["Gestión"] = gestion
if ROL_ADMIN in ROLES_U:
    secciones["Administración"] = [
        st.Page(pagina_usuarios, title="Usuarios", icon=":material/group:", url_path="usuarios"),
        st.Page(pagina_carga_masiva, title="Carga masiva", icon=":material/upload_file:", url_path="carga-masiva"),
    ]

nav = st.navigation(secciones, position="sidebar")

with st.sidebar:
    st.markdown(f"<div class='usuario-bloque'><div class='nom'>{html.escape(USUARIO['nombre'])}</div>"
                f"<div class='cor'>{html.escape(USUARIO['correo'])}</div>"
                f"<div class='rol'>{html.escape(', '.join(ROLES_ETIQUETA[r] for r in ROLES if r in ROLES_U))}</div></div>",
                unsafe_allow_html=True)
    if st.button("Actualizar datos", use_container_width=True, icon=":material/refresh:"):
        refrescar()
        st.rerun()
    with st.expander("Cambiar mi PIN"):
        with st.form("pin"):
            p1 = st.text_input("Nuevo PIN (6 dígitos)", type="password", max_chars=6)
            p2 = st.text_input("Repite el PIN", type="password", max_chars=6)
            if st.form_submit_button("Cambiar PIN"):
                if len(solo_digitos(p1)) != 6 or p1 != p2:
                    st.error("El PIN debe tener 6 dígitos y coincidir en ambos campos.")
                else:
                    cambiar_pin(store, USUARIO["correo"], p1, SAL)
                    refrescar()
                    st.success("PIN cambiado.")
    if st.button("Cerrar sesión", use_container_width=True, icon=":material/logout:"):
        st.session_state.clear()
        st.rerun()

nav.run()
