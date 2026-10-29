"""Constantes del sistema: columnas, estados, listas y reglas del flujo."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CATALOGOS_DIR = BASE_DIR / "data" / "catalogos"
PLANTILLA_BASE = BASE_DIR / "plantilla" / "plantilla_hermes_base.xlsx"

# ---------------------------------------------------------------------------
# Pestañas de la hoja de Google (o archivos CSV en modo local)
# ---------------------------------------------------------------------------
TAB_SOLICITUDES = "Solicitudes"
TAB_HISTORIAL = "Historial"
TAB_USUARIOS = "Usuarios"
TAB_NOTIFICACIONES = "Notificaciones"
TAB_ACTORES_CICLOPE = "Actores_CICLOPE"  # opcional: base de actores ya existentes

COLS_SOLICITUDES = [
    "radicado", "lote", "fecha_solicitud", "solicitante", "correo_solicitante",
    # Validación previa: ¿ya existe en Hermes?
    "existe_en_hermes", "referencia_hermes_existente",
    "aplicativo", "estado",
    # Datos de la plantilla HERMES
    "tipo_organizacion", "tipo_entidad", "tipo_identificacion", "identificacion",
    "nombre_organizacion", "direccion", "continente", "pais", "departamento",
    "municipio", "email", "telefono_fijo", "telefono_movil",
    "fuente_dato", "observaciones_solicitante",
    # Gestión Hermes
    "responsable_hermes", "numero_itop", "codigo_hermes", "fecha_creado_hermes",
    # Gestión Cíclope
    "responsable_ciclope", "codigo_ciclope", "fecha_creado_ciclope",
    # Control
    "observaciones_revision", "fecha_actualizacion", "origen",
    # Correcciones posteriores al envío
    "correccion_estado", "correccion_detalle", "correccion_motivo", "correccion_fecha",
]
COLS_HISTORIAL = ["fecha", "radicado", "lote", "usuario", "accion",
                  "estado_anterior", "estado_nuevo", "observacion"]
COLS_USUARIOS = ["correo", "nombre", "roles", "pin_hash", "activo", "notificaciones"]
COLS_NOTIFICACIONES = ["id", "fecha", "correo_destino", "nombre_destino", "tipo",
                       "radicado", "lote", "nombre_organizacion", "mensaje",
                       "estado_envio", "fecha_envio"]
COLS_ACTORES_CICLOPE = ["nombre", "identificacion"]

TABS = {
    TAB_SOLICITUDES: COLS_SOLICITUDES,
    TAB_HISTORIAL: COLS_HISTORIAL,
    TAB_USUARIOS: COLS_USUARIOS,
    TAB_NOTIFICACIONES: COLS_NOTIFICACIONES,
    TAB_ACTORES_CICLOPE: COLS_ACTORES_CICLOPE,
}

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
ROL_SOLICITANTE = "solicitante"
ROL_HERMES = "hermes"
ROL_CICLOPE = "ciclope"
ROL_ADMIN = "admin"
ROLES = [ROL_SOLICITANTE, ROL_HERMES, ROL_CICLOPE, ROL_ADMIN]
ROLES_ETIQUETA = {
    ROL_SOLICITANTE: "Solicitante",
    ROL_HERMES: "Creación en Hermes",
    ROL_CICLOPE: "Creación en Cíclope",
    ROL_ADMIN: "Administrador",
}

# ---------------------------------------------------------------------------
# Estados del flujo
# ---------------------------------------------------------------------------
E_SOLICITADA = "Solicitud realizada"
E_REVISION = "En revisión"
E_ITOP = "Itop en trámite"
E_DEVUELTA = "Devuelta para corrección"
E_PEND_CICLOPE = "Pendiente en Cíclope"
E_CREADO = "Creado"
E_ANULADA = "Anulada"

ESTADOS = [E_SOLICITADA, E_REVISION, E_ITOP, E_DEVUELTA, E_PEND_CICLOPE, E_CREADO, E_ANULADA]
COLA_HERMES = [E_SOLICITADA, E_REVISION, E_ITOP]
COLA_CICLOPE = [E_PEND_CICLOPE]
ESTADOS_ABIERTOS = COLA_HERMES + COLA_CICLOPE + [E_DEVUELTA]

COLOR_ESTADO = {
    E_SOLICITADA: "#8a6d00",
    E_REVISION: "#1f5fa8",
    E_ITOP: "#7a3fa0",
    E_DEVUELTA: "#b3261e",
    E_PEND_CICLOPE: "#0d7a6f",
    E_CREADO: "#2e7d32",
    E_ANULADA: "#5f6368",
}

# ---------------------------------------------------------------------------
# Listas de la plantilla
# ---------------------------------------------------------------------------
APP_HERMES = "Hermes"
APP_CICLOPE = "Cíclope"
APP_AMBOS = "Hermes y Cíclope"
APLICATIVOS = [APP_HERMES, APP_CICLOPE, APP_AMBOS]

TO_COLOMBIANA = "Organización Colombiana"
TO_EXT_DOMICILIADA = "Extranjera domiciliada en Colombia"
TO_EXT_NO_DOMICILIADA = "Organización extranjera No domiciliada en Colombia"
TIPOS_ORGANIZACION = [TO_COLOMBIANA, TO_EXT_DOMICILIADA, TO_EXT_NO_DOMICILIADA]

TIPOS_ENTIDAD = ["Organización Pública/Gubernamental", "Organización Privada", "Organización Mixta"]

TI_NIT = "NIT"
TI_NIE = "NIE"
TI_NIF = "NIF"
TI_DESIGNADO = "Designado APC Colombia - GIT de TI"
TIPOS_IDENTIFICACION = [TI_NIT, TI_NIE, TI_NIF, TI_DESIGNADO]

PAIS_COLOMBIA = "COLOMBIA"
NO_APLICA = "No aplica"

# Regla institucional: Holanda y Reino Unido se reportan dentro de Unión Europea
CONTINENTE_FORZADO = {"HOLANDA": "Unión Europea", "REINO UNIDO": "Unión Europea"}

DIAS_ALERTA = 5  # días sin movimiento para marcar una solicitud como atrasada
