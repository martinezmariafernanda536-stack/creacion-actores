---
title: Creacion de actores
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Solicitudes de creación de actores en Hermes y Cíclope
---

# Creación de actores · Hermes y Cíclope

Sistema para solicitar, validar y hacer seguimiento a la creación de actores (terceros) en **Hermes** y **Cíclope**. Reemplaza el diligenciamiento manual de la *Plantilla Solicitud Creación de Terceros HERMES*.

APC-Colombia · Dirección de Gestión de Demanda de Cooperación Internacional.

## Qué hace

| Rol | Puede |
|---|---|
| Solicitante | Llenar el formulario (uno o varios actores por lote), ver en qué fase va cada actor y corregir lo que le devuelvan |
| Creación en Hermes | Ver su bandeja, tomar en revisión, registrar Itop, marcar como creado en Hermes, devolver, anular y descargar el Excel en formato plantilla |
| Creación en Cíclope | Ver su bandeja, marcar como creado en Cíclope, devolver y anular |
| Administrador | Todo lo anterior, más la gestión de usuarios, PIN y permisos |

**Validaciones del formulario**
- NIT de 10 dígitos con dígito de verificación según el algoritmo de la DIAN.
- Alerta de duplicados por identificación exacta y por nombre parecido (coincidencia difusa), contra todas las solicitudes y la base de CICLOPE.
- Pregunta obligatoria **"¿El actor ya está creado en Hermes?"** antes de elegir dónde crearlo. Si la respuesta es *Sí*, la solicitud va directo a Cíclope.
- Listas encadenadas: continente → país, y para Colombia, departamento → municipio.
- **Holanda y Reino Unido quedan dentro de Unión Europea**, según la regla institucional definida en `core/config.py`.
- Correo con formato válido y teléfonos solo numéricos.

**Flujo de estados**

```
Solicitud realizada → En revisión → (Itop en trámite) → Pendiente en Cíclope → Creado
            ↘ Devuelta para corrección (vuelve a la cola al corregir)
            ↘ Anulada
```

- La ruta "Hermes" termina al crear en Hermes.
- La ruta "Cíclope" (actor que ya existe en Hermes) empieza en *Pendiente en Cíclope*.

## Arquitectura

```
Streamlit Community Cloud (app.py)
        │  gspread + cuenta de servicio
        ▼
Hoja de Google privada ── Apps Script (Notificaciones.gs) ── correos
  Solicitudes · Historial · Usuarios · Notificaciones · Actores_CICLOPE
```

- **GitHub** guarda solo código, sin datos ni contraseñas.
- **Correos**: la app deja los avisos en la pestaña *Notificaciones*. Apps Script los envía cada 15 minutos, agrupados en un correo por persona, y a las 8 a. m. de cada día hábil envía un resumen de la cola a Hermes y a Cíclope.

## Estructura

```
app.py                    Interfaz (formulario, bandejas, seguimiento, usuarios)
core/config.py            Columnas, estados, listas y reglas
core/validaciones.py      NIT/DV, correo, teléfonos, duplicados
core/flujo.py             Cambios de estado, historial y cola de avisos
core/exportar.py          Excel en formato de la plantilla oficial
core/storage.py           Google Sheets (producción) / CSV local (pruebas)
core/auth.py              Acceso con correo + PIN (cifrado PBKDF2)
core/historico.py         Migración de la plantilla Excel actual
core/catalogos.py         Países por continente y DIVIPOLA
data/catalogos/           paises.csv, divipola.csv
plantilla/                Plantilla base vacía para exportar
scripts/inicializar.py    Crea pestañas, carga el histórico y crea el administrador
apps_script/              Script de correos para pegar en la hoja de Google
```

## Probar en el computador (sin Google)

```bash
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# en secrets.toml deja: backend = "local"
python scripts/inicializar.py --admin-correo tu@correo --admin-nombre "Tu Nombre" \
    --plantilla "Plantilla Solicitud Creación de Terceros HERMES.xlsx"
streamlit run app.py
```

La guía paso a paso completa de despliegue está en el documento que acompaña este repositorio.
