/**
 * Avisos por correo del sistema de creación de actores (Hermes y Cíclope).
 *
 * Se pega en la hoja de Google: Extensiones → Apps Script.
 * Envía los correos desde la cuenta dueña de la hoja (sin contraseñas en la app).
 *
 * - procesarNotificaciones(): cada 15 minutos. Toma los avisos pendientes
 *   (devoluciones, actores creados, anulaciones) y envía UN correo por persona
 *   con todo lo que tenga acumulado.
 * - resumenDiario(): cada día hábil a las 8 a. m. Envía a quienes crean en Hermes
 *   y en Cíclope un único correo con su cola pendiente y lo atrasado.
 *
 * Primera vez: ejecuta instalarActivadores() una sola vez y acepta los permisos.
 */

const CONFIG = {
  APP_URL: 'https://TU-APP.streamlit.app',   // ← cambia por la URL real de la app
  NOMBRE: 'Creación de actores · Hermes y Cíclope',
  DIAS_ALERTA: 5,
  SOLO_DIAS_HABILES: true,
};

const COLA_HERMES = ['Solicitud realizada', 'En revisión', 'Itop en trámite'];
const COLA_CICLOPE = ['Pendiente en Cíclope'];

// ---------------------------------------------------------------------------
function procesarNotificaciones() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) return;
  try {
    enviarPendientes_(['inmediato', '']);
  } finally {
    lock.releaseLock();
  }
}

function resumenDiario() {
  if (CONFIG.SOLO_DIAS_HABILES) {
    const d = new Date().getDay();
    if (d === 0 || d === 6) return;
  }
  // 1) Avisos acumulados de quienes eligieron "resumen"
  enviarPendientes_(['resumen']);

  // 2) Cola de trabajo para Hermes y Cíclope
  const sol = leer_('Solicitudes');
  const usuarios = leer_('Usuarios').filter(u => String(u.activo).toUpperCase() === 'SI'
                                              && u.notificaciones !== 'ninguno');
  const hoy = new Date();
  const dias = r => {
    const f = new Date(String(r.fecha_actualizacion || r.fecha_solicitud).replace(' ', 'T'));
    return isNaN(f) ? 0 : Math.floor((hoy - f) / 86400000);
  };

  usuarios.forEach(u => {
    const roles = String(u.roles).toLowerCase().split(/[;,]/).map(s => s.trim());
    const bloques = [];
    if (roles.includes('hermes')) bloques.push(bloqueCola_('Hermes', sol.filter(r => COLA_HERMES.includes(r.estado)), dias,
      sol.filter(r => r.correccion_estado === 'Pendiente en Hermes')));
    if (roles.includes('ciclope')) bloques.push(bloqueCola_('Cíclope', sol.filter(r => COLA_CICLOPE.includes(r.estado)), dias,
      sol.filter(r => r.correccion_estado === 'Pendiente en Cíclope')));
    const conTrabajo = bloques.filter(b => b.total > 0);
    if (!conTrabajo.length) return;
    const total = conTrabajo.reduce((a, b) => a + b.total, 0);
    MailApp.sendEmail({
      to: u.correo,
      subject: `[Actores] Tienes ${total} solicitud(es) pendiente(s)`,
      htmlBody: plantilla_(`Hola ${u.nombre},`,
        conTrabajo.map(b => b.html).join('') +
        `<p><a href="${CONFIG.APP_URL}" style="${btn_()}">Abrir mi bandeja</a></p>`),
    });
  });
}

// ---------------------------------------------------------------------------
function enviarPendientes_(preferencias) {
  const hoja = SpreadsheetApp.getActive().getSheetByName('Notificaciones');
  const datos = hoja.getDataRange().getValues();
  if (datos.length < 2) return;
  const h = datos[0];
  const col = n => h.indexOf(n);
  const pref = {};
  leer_('Usuarios').forEach(u => pref[String(u.correo).toLowerCase()] = u.notificaciones || 'inmediato');

  const porDestino = {};
  for (let i = 1; i < datos.length; i++) {
    const fila = datos[i];
    if (fila[col('estado_envio')] !== 'pendiente') continue;
    const correo = String(fila[col('correo_destino')]).toLowerCase();
    const p = pref[correo] === undefined ? 'inmediato' : pref[correo];
    if (p === 'ninguno') {
      hoja.getRange(i + 1, col('estado_envio') + 1).setValue('omitido');
      continue;
    }
    if (!preferencias.includes(p)) continue;
    (porDestino[correo] = porDestino[correo] || { nombre: fila[col('nombre_destino')], filas: [] })
      .filas.push({ i: i + 1, tipo: fila[col('tipo')], org: fila[col('nombre_organizacion')],
                    rad: fila[col('radicado')], msg: fila[col('mensaje')] });
  }

  const ahora = Utilities.formatDate(new Date(), 'America/Bogota', 'yyyy-MM-dd HH:mm:ss');
  Object.keys(porDestino).forEach(correo => {
    const d = porDestino[correo];
    const devueltas = d.filas.filter(f => f.tipo === 'Devuelta para corrección');
    const porAplicar = d.filas.filter(f => f.tipo === 'Corrección por aplicar' || f.tipo === 'Datos corregidos');
    const asunto = porAplicar.length
      ? `[Actores] ${porAplicar.length} corrección(es) de datos de actores`
      : devueltas.length
        ? `[Actores] ${devueltas.length} solicitud(es) devuelta(s) para corrección`
        : `[Actores] Actualización de ${d.filas.length} solicitud(es)`;
    const filasHtml = d.filas.map(f =>
      `<tr><td style="${td_()}">${esc_(f.org)}<br><small style="color:#6b7280">${esc_(f.rad)}</small></td>` +
      `<td style="${td_()}"><b>${esc_(f.tipo)}</b><br>${esc_(f.msg)}</td></tr>`).join('');
    MailApp.sendEmail({
      to: correo,
      subject: asunto,
      htmlBody: plantilla_(`Hola ${d.nombre},`,
        `<p>Estas son las novedades de las solicitudes de creación de actores:</p>` +
        `<table style="border-collapse:collapse;width:100%">${filasHtml}</table>` +
        `<p><a href="${CONFIG.APP_URL}" style="${btn_()}">Ver mis solicitudes</a></p>`),
    });
    d.filas.forEach(f => {
      hoja.getRange(f.i, col('estado_envio') + 1).setValue('enviado');
      hoja.getRange(f.i, col('fecha_envio') + 1).setValue(ahora);
    });
  });
}

function bloqueCola_(sistema, filas, dias, correcciones) {
  const atrasadas = filas.filter(r => dias(r) > CONFIG.DIAS_ALERTA);
  const porEstado = {};
  filas.forEach(r => porEstado[r.estado] = (porEstado[r.estado] || 0) + 1);
  const lista = Object.keys(porEstado).map(e => `<li>${esc_(e)}: <b>${porEstado[e]}</b></li>`).join('');
  const top = atrasadas.slice(0, 10).map(r =>
    `<li>${esc_(r.nombre_organizacion)} <small>(${dias(r)} días · ${esc_(r.solicitante)})</small></li>`).join('');
  const corr = (correcciones || []).map(r =>
    `<li>${esc_(r.nombre_organizacion)} <small>(pedida por ${esc_(r.solicitante)})</small></li>`).join('');
  return {
    total: filas.length + (correcciones || []).length,
    html: `<h3 style="margin:16px 0 6px">${sistema}: ${filas.length} pendiente(s)</h3><ul>${lista}</ul>` +
      (corr ? `<p><b>${correcciones.length}</b> corrección(es) de actores ya creados por aplicar:</p><ul>${corr}</ul>` : '') +
      (atrasadas.length ? `<p style="color:#b3261e"><b>${atrasadas.length}</b> con más de ${CONFIG.DIAS_ALERTA} días sin movimiento:</p><ul>${top}</ul>` : ''),
  };
}

// ---------------------------------------------------------------------------
function leer_(nombre) {
  const v = SpreadsheetApp.getActive().getSheetByName(nombre).getDataRange().getValues();
  const h = v.shift();
  return v.map(f => Object.fromEntries(h.map((k, i) => [k, f[i]])));
}

function plantilla_(saludo, cuerpo) {
  return `<div style="font-family:Arial,sans-serif;font-size:14px;color:#1f2937;max-width:640px">
    <p>${esc_(saludo)}</p>${cuerpo}
    <hr style="border:none;border-top:1px solid #e5e7eb;margin-top:24px">
    <p style="color:#6b7280;font-size:12px">${CONFIG.NOMBRE} · Mensaje automático. Puedes ajustar
    la frecuencia de estos avisos con el administrador del sistema.</p></div>`;
}
const td_ = () => 'border-bottom:1px solid #e5e7eb;padding:8px;vertical-align:top';
const btn_ = () => 'background:#1f3b73;color:#fff;padding:9px 16px;border-radius:6px;text-decoration:none;display:inline-block';
const esc_ = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

// ---------------------------------------------------------------------------
function instalarActivadores() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('procesarNotificaciones').timeBased().everyMinutes(15).create();
  ScriptApp.newTrigger('resumenDiario').timeBased().everyDays(1).atHour(8).inTimezone('America/Bogota').create();
  Logger.log('Activadores instalados: avisos cada 15 min y resumen diario 8 a. m.');
}

function probarCorreo() {
  const yo = Session.getActiveUser().getEmail();
  MailApp.sendEmail({ to: yo, subject: '[Actores] Prueba de correo',
    htmlBody: plantilla_('Hola,', '<p>Si recibes este mensaje, los avisos están bien configurados.</p>') });
  Logger.log('Correo de prueba enviado a ' + yo + '. Cupo restante hoy: ' + MailApp.getRemainingDailyQuota());
}
