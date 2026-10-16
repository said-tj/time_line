/* Presión uretral (Pura) — lógica del sitio de resultados.
   Los datos vienen de datos.js (window.DATOS), que escribe scripts/generar_web.py. */

(function () {
"use strict";

const D = window.DATOS;
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

/* ---------- formato ---------- */

function mmss(t) {
  const neg = t < 0;
  let s = Math.round(Math.abs(t) * 10) / 10, m = Math.floor(s / 60);
  s = Math.round((s - 60 * m) * 10) / 10;
  if (s >= 60) { s -= 60; m += 1; }                 // acarreo del redondeo
  return (neg ? "−" : "") + m + ":" + (s < 10 ? "0" : "") + (s % 1 ? s.toFixed(1) : String(s));
}
function mmssCorto(t) {
  const neg = t < 0;
  let s = Math.round(Math.abs(t)), m = Math.floor(s / 60);
  s -= 60 * m;
  return (neg ? "−" : "") + m + ":" + (s < 10 ? "0" : "") + s;
}
const n1 = v => (v === null || v === undefined || v === "") ? "—" : (+v).toFixed(1);
const n2 = v => (v === null || v === undefined || v === "") ? "—" : (+v).toFixed(2);
const n3 = v => (v === null || v === undefined || v === "") ? "—" : (+v).toFixed(3);
const n4 = v => (v === null || v === undefined || v === "") ? "—" : (+v).toFixed(4);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const tEn = (ser, i) => ser.t ? ser.t[i] : ser.t0 + i * ser.dt;
const iEn = (ser, t) => Math.round((t - ser.t0) / ser.dt);

function tabla(el, cabeceras, filas) {
  el.innerHTML =
    "<thead><tr>" + cabeceras.map(c =>
      `<th class="${c.izq ? "izq" : ""}" ${c.titulo ? `title="${esc(c.titulo)}"` : ""}>${c.t}</th>`).join("") +
    "</tr></thead><tbody>" + filas.join("") + "</tbody>";
}

/* ---------- tema ---------- */

const temaGuardado = (() => { try { return localStorage.getItem("tema"); } catch (e) { return null; } })();
if (temaGuardado) document.documentElement.dataset.tema = temaGuardado;
$("#btn-tema").addEventListener("click", () => {
  const oscuro = getComputedStyle(document.body).backgroundColor.match(/\d+/g)[0] < 100;
  const nuevo = oscuro ? "claro" : "oscuro";
  document.documentElement.dataset.tema = nuevo;
  try { localStorage.setItem("tema", nuevo); } catch (e) { /* modo privado */ }
  grafica && grafica.dibujar();
  pintarSesiones();
});

/* ---------- pestañas ---------- */

function abrirVista(nombre) {
  $$("nav.pestanas button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.vista === nombre)));
  $$("section.vista").forEach(s => s.classList.toggle("activa", s.id === "vista-" + nombre));
  if (nombre === "curvas" && grafica) grafica.redimensionar();
  try { history.replaceState(null, "", "#" + nombre); } catch (e) { /* file:// */ }
}
$$("nav.pestanas button").forEach(b => b.addEventListener("click", () => abrirVista(b.dataset.vista)));

/* ================= RESUMEN ================= */

$("#titulo").textContent = D.titulo;
$("#subtitulo").textContent = D.subtitulo;
$("#pie").innerHTML = `Base de datos generada el ${esc(D.generado)} a partir de <code>create/</code> · ` +
  `${D.sesiones.length} sesiones · ${D.sesiones.reduce((a, s) => a + s.capturas.length, 0)} capturas`;

const totMuestras = D.sesiones.reduce((a, s) => a + s.resumen.muestras, 0);
const totDur = D.sesiones.reduce((a, s) => a + s.resumen.duracion_s, 0);
const totCapturas = D.sesiones.reduce((a, s) => a + s.capturas.length, 0);
const porRevisar = D.sesiones.reduce((a, s) => a + s.capturas.filter(c => c.estado === "REVISAR").length, 0);
const rmsPeor = Math.max(...D.sesiones.flatMap(s => s.solapamientos.map(o => o.dif_rms || 0)));

$("#kpis").innerHTML = [
  ["Sujetos · sesiones", `${D.sujetos.length} · ${D.sesiones.length}`, D.sujetos.join(", ") + " — " + D.sesiones.map(s => s.condicion).join(" → ")],
  ["Capturas digitalizadas", totCapturas, porRevisar ? `${porRevisar} marcada(s) para revisar` : "todas dentro de tolerancia"],
  ["Muestras de presión", totMuestras.toLocaleString("es-MX"), `paso 0.1 s · ${mmssCorto(totDur)} de registro`],
  ["Concordancia peor caso", n2(rmsPeor) + " cm H₂O", "diferencia RMS entre capturas consecutivas"],
].map(([e, v, p]) => `<div class="kpi"><div class="etiqueta">${e}</div><div class="valor">${v}</div><div class="pie">${esc(p)}</div></div>`).join("");

function miniatura(cv, ses) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth || 240, h = 72;
  cv.width = w * dpr; cv.height = h * dpr;
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);
  const s = ses.serie, cs = getComputedStyle(document.body);
  const ymax = Math.max(10, Math.max.apply(null, s.p)) * 1.05;
  const X = i => (i / (s.n - 1)) * w, Y = v => h - 2 - (v / ymax) * (h - 6);

  for (let x = 0; x < w; x++) {                      // censura
    const i = Math.round((x / w) * (s.n - 1)), c = s.c[i];
    if (c === "0") continue;
    g.fillStyle = cs.getPropertyValue(c === "-" ? "--piso" : "--techo");
    g.fillRect(x, 0, 1.2, h);
  }
  g.beginPath();
  for (let x = 0; x <= w; x++) {                     // trazo (mín–máx por píxel)
    const i0 = Math.floor((x / w) * (s.n - 1)), i1 = Math.max(i0 + 1, Math.floor(((x + 1) / w) * (s.n - 1)));
    let mn = Infinity, mx = -Infinity;
    for (let i = i0; i <= i1 && i < s.n; i++) { if (s.p[i] < mn) mn = s.p[i]; if (s.p[i] > mx) mx = s.p[i]; }
    if (mn === Infinity) continue;
    g.lineTo(x, Y(mn)); g.lineTo(x, Y(mx));
  }
  g.strokeStyle = ses.color; g.lineWidth = 1.2; g.stroke();
}

function pintarSesiones() {
  $("#sesiones").innerHTML = D.sesiones.map(s => {
    const r = s.resumen;
    return `<div class="tarjeta sesion" style="--c:${s.color};margin:0" data-ses="${s.id}">
      <div class="titulo"><h3>${esc(s.condicion)}</h3><span class="orden">${s.orden} de ${D.sesiones.length}</span></div>
      <canvas data-mini="${s.id}"></canvas>
      <dl>
        <dt>Capturas</dt><dd>${s.capturas.length}</dd>
        <dt>Duración</dt><dd>${mmssCorto(r.duracion_s)}</dd>
        <dt>Media</dt><dd>${n1(r.pura_media)} cm H₂O</dd>
        <dt>Máximo</dt><dd>${n1(r.pura_max)} <span style="color:var(--texto-3)">(${mmssCorto(r.t_pura_max)})</span></dd>
        <dt>En el piso</dt><dd>${n1(r.pct_piso)} %</dd>
      </dl></div>`;
  }).join("");
  D.sesiones.forEach(s => miniatura($(`canvas[data-mini="${s.id}"]`), s));
  $$("#sesiones .sesion").forEach(d => d.addEventListener("click", () => {
    const id = d.dataset.ses;
    series.forEach(x => x.visible = x.id === id);
    sincronizarChips(); grafica.reiniciar(); abrirVista("curvas");
  }));
}

const MEDIDAS = {
  pura_media: ["Media", "cm H₂O"], pura_mediana: ["Mediana", "cm H₂O"],
  pura_max: ["Máximo", "cm H₂O"], pura_p95: ["Percentil 95", "cm H₂O"],
  pura_de: ["Desviación estándar", "cm H₂O"], auc: ["Integral", "cm H₂O·s"],
  duracion_s: ["Duración", "s"], pct_piso: ["Piso", "%"],
};

function pintarComparacion() {
  const medida = $("#sel-medida").value;
  const [etq, uni] = MEDIDAS[medida];
  const tope = Math.max.apply(null, D.sesiones.map(s => s.resumen[medida] || 0)) || 1;
  const filas = D.sesiones.map(s => {
    const r = s.resumen, v = r[medida] || 0;
    return `<tr data-ses="${s.id}">
      <td class="izq"><span class="cond-punto" style="background:${s.color}"></span>${esc(s.condicion)}</td>
      <td>${s.capturas.length}</td>
      <td>${mmssCorto(r.duracion_s)}</td>
      <td>${r.muestras.toLocaleString("es-MX")}</td>
      <td>${n1(100 * r.n_validas / r.muestras)} %</td>
      <td>${n1(r.pura_media)}</td>
      <td>${n1(r.pura_mediana)}</td>
      <td>${n1(r.pura_de)}</td>
      <td>${n1(r.pura_max)}</td>
      <td>${mmssCorto(r.t_pura_max)}</td>
      <td>${r.auc.toLocaleString("es-MX")}</td>
      <td><div class="barra" style="--c:${s.color}"><i style="width:${(100 * v / tope).toFixed(1)}%"></i>
          <span>${medida === "duracion_s" ? mmssCorto(v) : v.toLocaleString("es-MX")}</span></div></td></tr>`;
  });
  tabla($("#tabla-comparacion"), [
    { t: "Condición", izq: true }, { t: "Capt." }, { t: "Duración" }, { t: "Muestras" },
    { t: "Válidas", titulo: "Porcentaje de muestras no censuradas" },
    { t: "Media" }, { t: "Mediana" }, { t: "DE" }, { t: "Máx" },
    { t: "t del máx" }, { t: "Integral", titulo: "cm H₂O·s" },
    { t: `${etq} (${uni})` },
  ], filas);
  $$("#tabla-comparacion tbody tr").forEach(tr => tr.addEventListener("click", () => {
    series.forEach(x => x.visible = x.id === tr.dataset.ses);
    sincronizarChips(); grafica.reiniciar(); abrirVista("curvas");
  }));
}
$("#sel-medida").addEventListener("change", pintarComparacion);

/* ================= GRÁFICA ================= */

const series = D.sesiones.map(s => ({
  id: s.id, etiqueta: s.condicion, color: s.color, serie: s.serie, ses: s, visible: true,
}));

class Grafica {
  constructor(cv, globo) {
    this.cv = cv; this.g = cv.getContext("2d"); this.globo = globo;
    this.m = { i: 58, d: 16, a: 14, b: 32 };
    this.reiniciar(true);

    cv.addEventListener("wheel", e => {
      const [a, b] = this.limiteTotal();
      // Si ya se ve todo y se sigue alejando, el gesto le toca a la página.
      if (e.deltaY > 0 && this.vista.t0 <= a && this.vista.t1 >= b) return;
      e.preventDefault();
      const t = this.aTiempo(this.xRaton(e)), k = Math.exp(e.deltaY * 0.0015);
      let { t0, t1 } = this.vista;
      t0 = t - (t - t0) * k; t1 = t + (t1 - t) * k;
      this.fijarVista(t0, t1);
    }, { passive: false });

    cv.addEventListener("pointerdown", e => {
      this.arr = { x: this.xRaton(e), t0: this.vista.t0, t1: this.vista.t1 };
      cv.setPointerCapture(e.pointerId); cv.style.cursor = "grabbing";
    });
    cv.addEventListener("pointermove", e => {
      if (this.arr) {
        const dt = (this.xRaton(e) - this.arr.x) / this.anchoUtil() * (this.arr.t1 - this.arr.t0);
        this.fijarVista(this.arr.t0 - dt, this.arr.t1 - dt);
      } else this.mostrarGlobo(e);
    });
    const soltar = e => { this.arr = null; cv.style.cursor = "crosshair"; };
    cv.addEventListener("pointerup", soltar);
    cv.addEventListener("pointercancel", soltar);
    cv.addEventListener("pointerleave", () => { this.arr = null; this.globo.style.display = "none"; this.cruz = null; this.dibujar(); });
    cv.addEventListener("dblclick", () => this.reiniciar());
    window.addEventListener("resize", () => this.redimensionar());
  }

  visibles() { return series.filter(s => s.visible); }
  anchoUtil() { return this.cv.clientWidth - this.m.i - this.m.d; }
  xRaton(e) { return e.clientX - this.cv.getBoundingClientRect().left; }
  aTiempo(x) { const v = this.vista; return v.t0 + (x - this.m.i) / this.anchoUtil() * (v.t1 - v.t0); }
  aX(t) { const v = this.vista; return this.m.i + (t - v.t0) / (v.t1 - v.t0) * this.anchoUtil(); }
  aY(p) { const a = this.cv.clientHeight - this.m.a - this.m.b; return this.m.a + (1 - (p - this.y0) / (this.y1 - this.y0)) * a; }

  limiteTotal() {
    const vs = this.visibles().length ? this.visibles() : series;
    return [Math.min.apply(null, vs.map(s => s.serie.t0)),
            Math.max.apply(null, vs.map(s => tEn(s.serie, s.serie.n - 1)))];
  }
  reiniciar(silencio) {
    const [a, b] = this.limiteTotal();
    this.vista = { t0: a, t1: b };
    if (!silencio) this.dibujar();
  }
  fijarVista(t0, t1) {
    const [a, b] = this.limiteTotal(), minSpan = 0.5;
    if (t1 - t0 < minSpan) { const c = (t0 + t1) / 2; t0 = c - minSpan / 2; t1 = c + minSpan / 2; }
    if (t1 - t0 > b - a) { t0 = a; t1 = b; }
    if (t0 < a) { t1 += a - t0; t0 = a; }
    if (t1 > b) { t0 -= t1 - b; t1 = b; }
    this.vista = { t0, t1 }; this.dibujar();
  }
  redimensionar() { this.dibujar(); }

  /* mín/máx por columna de píxel, para dibujar rápido series largas */
  agregados(s, campo) {
    const v = this.vista, w = Math.max(1, Math.round(this.anchoUtil()));
    const a = s.serie[campo], out = new Array(w);
    for (let x = 0; x < w; x++) {
      const ta = v.t0 + (x / w) * (v.t1 - v.t0), tb = v.t0 + ((x + 1) / w) * (v.t1 - v.t0);
      let i0 = Math.max(0, Math.ceil(iEn(s.serie, ta))), i1 = Math.min(s.serie.n - 1, Math.floor(iEn(s.serie, tb)));
      if (i1 < i0) { const i = Math.round(iEn(s.serie, (ta + tb) / 2)); i0 = i1 = i; }
      if (i0 < 0 || i1 >= s.serie.n || i1 < i0) { out[x] = null; continue; }
      let mn = Infinity, mx = -Infinity;
      for (let i = i0; i <= i1; i++) { const y = a[i]; if (y < mn) mn = y; if (y > mx) mx = y; }
      out[x] = [mn, mx];
    }
    return out;
  }

  dibujar() {
    const cv = this.cv, g = this.g, cs = getComputedStyle(document.body);
    const dpr = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr; g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);

    const vis = this.visibles(), v = this.vista;
    const col = k => cs.getPropertyValue(k).trim();
    const izq = this.m.i, der = w - this.m.d, arr = this.m.a, aba = h - this.m.b;

    if (!vis.length) {
      g.fillStyle = col("--texto-3"); g.font = "13px system-ui"; g.textAlign = "center";
      g.fillText("Ninguna sesión seleccionada", w / 2, h / 2); return;
    }

    /* escala vertical sobre lo visible */
    let y0 = Infinity, y1 = -Infinity;
    const conEnv = $("#chk-envolvente").checked;
    vis.forEach(s => {
      const ag = this.agregados(s, "p"), agl = conEnv ? this.agregados(s, "lo") : null,
            agh = conEnv ? this.agregados(s, "hi") : null;
      ag.forEach((p, x) => { if (!p) return; if (p[0] < y0) y0 = p[0]; if (p[1] > y1) y1 = p[1]; });
      if (conEnv) {
        agl.forEach(p => { if (p && p[0] < y0) y0 = p[0]; });
        agh.forEach(p => { if (p && p[1] > y1) y1 = p[1]; });
      }
    });
    if (!isFinite(y0)) { y0 = 0; y1 = 100; }
    const pad = Math.max(2, (y1 - y0) * 0.06);
    y0 = y0 < 10 ? Math.min(0, y0 - pad) : y0 - pad; y1 = y1 + pad;
    this.y0 = y0; this.y1 = y1;

    /* rejilla y ejes */
    g.save(); g.beginPath(); g.rect(izq, arr, der - izq, aba - arr); g.clip();

    /* censura: a toda altura con una sola sesión, en carriles cuando hay varias */
    if ($("#chk-censura").checked) {
      const unica = vis.length === 1, alto = 5, w2 = Math.max(1, Math.round(der - izq));
      vis.forEach((s, k) => {
        const yTop = unica ? arr : aba - alto * (vis.length - k) - 1;
        const alt = unica ? aba - arr : alto - 1;
        if (!unica) { g.globalAlpha = .5; g.fillStyle = col("--panel-2"); g.fillRect(izq, yTop, der - izq, alt); g.globalAlpha = 1; }
        for (let x = 0; x < w2; x++) {
          const t = v.t0 + (x / w2) * (v.t1 - v.t0), i = Math.round(iEn(s.serie, t));
          if (i < 0 || i >= s.serie.n) continue;
          const c = s.serie.c[i];
          if (c === "0") continue;
          if (unica) g.fillStyle = col(c === "-" ? "--piso" : "--techo");
          else { g.fillStyle = c === "-" ? s.color : col("--alerta"); g.globalAlpha = c === "-" ? .45 : .9; }
          g.fillRect(izq + x, yTop, 1.05, alt);
          g.globalAlpha = 1;
        }
      });
    }

    /* límites de captura y cursores del equipo */
    if ($("#chk-limites").checked || $("#chk-cursores").checked) {
      vis.forEach(s => {
        g.strokeStyle = s.color; g.globalAlpha = .45; g.lineWidth = 1;
        if ($("#chk-limites").checked) {
          g.setLineDash([5, 4]);
          s.ses.capturas.forEach(c => {
            const x = this.aX(c.t_inicio_s);
            if (x < izq || x > der) return;
            g.beginPath(); g.moveTo(x, arr); g.lineTo(x, aba); g.stroke();
            g.globalAlpha = .9; g.fillStyle = s.color; g.font = "10px system-ui"; g.textAlign = "left";
            g.fillText(c.captura, x + 3, arr + 10); g.globalAlpha = .45;
          });
        }
        if ($("#chk-cursores").checked) {
          g.setLineDash([2, 3]);
          s.ses.capturas.forEach(c => (c.calib.cursores_s || []).forEach(t => {
            const x = this.aX(t); if (x < izq || x > der) return;
            g.beginPath(); g.moveTo(x, arr); g.lineTo(x, aba); g.stroke();
          }));
        }
        g.setLineDash([]); g.globalAlpha = 1;
      });
    }

    /* envolvente */
    if (conEnv) vis.forEach(s => {
      const lo = this.agregados(s, "lo"), hi = this.agregados(s, "hi");
      g.beginPath(); let abierto = false;
      for (let x = 0; x < hi.length; x++) { if (!hi[x]) continue; const X = izq + x; if (!abierto) { g.moveTo(X, this.aY(hi[x][1])); abierto = true; } else g.lineTo(X, this.aY(hi[x][1])); }
      for (let x = lo.length - 1; x >= 0; x--) { if (!lo[x]) continue; g.lineTo(izq + x, this.aY(lo[x][0])); }
      g.closePath(); g.fillStyle = s.color; g.globalAlpha = .17; g.fill(); g.globalAlpha = 1;
    });

    /* trazo */
    vis.forEach(s => {
      const ag = this.agregados(s, "p");
      g.beginPath(); let abierto = false;
      for (let x = 0; x < ag.length; x++) {
        const p = ag[x]; if (!p) { abierto = false; continue; }
        const X = izq + x;
        if (!abierto) { g.moveTo(X, this.aY(p[0])); abierto = true; }
        g.lineTo(X, this.aY(p[0])); g.lineTo(X, this.aY(p[1]));
      }
      g.strokeStyle = s.color; g.lineWidth = 1.4; g.lineJoin = "round"; g.stroke();
    });

    /* cruz */
    if (this.cruz !== null && this.cruz !== undefined) {
      const x = this.aX(this.cruz);
      if (x >= izq && x <= der) {
        g.strokeStyle = col("--texto-3"); g.globalAlpha = .7; g.setLineDash([3, 3]); g.lineWidth = 1;
        g.beginPath(); g.moveTo(x, arr); g.lineTo(x, aba); g.stroke();
        g.setLineDash([]); g.globalAlpha = 1;
        vis.forEach(s => {
          const i = Math.round(iEn(s.serie, this.cruz));
          if (i < 0 || i >= s.serie.n) return;
          g.fillStyle = s.color; g.beginPath(); g.arc(x, this.aY(s.serie.p[i]), 3, 0, 7); g.fill();
        });
      }
    }
    g.restore();

    /* ejes */
    g.strokeStyle = col("--borde"); g.lineWidth = 1;
    g.fillStyle = col("--texto-3"); g.font = "11px system-ui";

    const pasoY = pasoLindo((y1 - y0) / 6);
    g.textAlign = "right"; g.textBaseline = "middle";
    for (let p = Math.ceil(y0 / pasoY) * pasoY; p <= y1; p += pasoY) {
      const Y = this.aY(p);
      g.globalAlpha = .55; g.beginPath(); g.moveTo(izq, Y); g.lineTo(der, Y); g.stroke(); g.globalAlpha = 1;
      g.fillText(Math.round(p), izq - 8, Y);
    }
    const pasoT = pasoTiempo((v.t1 - v.t0) / 7);
    g.textAlign = "center"; g.textBaseline = "top";
    for (let t = Math.ceil(v.t0 / pasoT) * pasoT; t <= v.t1; t += pasoT) {
      const X = this.aX(t);
      g.globalAlpha = .4; g.beginPath(); g.moveTo(X, arr); g.lineTo(X, aba); g.stroke(); g.globalAlpha = 1;
      g.fillText(pasoT < 1 ? mmss(t) : mmssCorto(t), X, aba + 7);
    }
    g.strokeStyle = col("--borde");
    g.beginPath(); g.moveTo(izq, arr); g.lineTo(izq, aba); g.lineTo(der, aba); g.stroke();

    g.save(); g.translate(14, (arr + aba) / 2); g.rotate(-Math.PI / 2);
    g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = col("--texto-2");
    g.fillText("Pura (cm H₂O)", 0, 0); g.restore();
    g.textAlign = "right"; g.textBaseline = "bottom"; g.fillStyle = col("--texto-2");
    g.fillText("tiempo (m:ss)", der, h - 2);

    $("#info-rango").textContent =
      `Rango visible ${mmss(v.t0)} – ${mmss(v.t1)}  (${(v.t1 - v.t0).toFixed(1)} s)`;
  }

  mostrarGlobo(e) {
    const x = this.xRaton(e), y = e.clientY - this.cv.getBoundingClientRect().top;
    if (x < this.m.i || x > this.cv.clientWidth - this.m.d) { this.globo.style.display = "none"; this.cruz = null; this.dibujar(); return; }
    const t = this.aTiempo(x);
    this.cruz = t; this.dibujar();
    const filas = this.visibles().map(s => {
      const i = Math.round(iEn(s.serie, t));
      if (i < 0 || i >= s.serie.n) return "";
      const c = s.serie.c[i], marca = c === "-" ? " ↓piso" : c === "+" ? " ↑techo" : "";
      return `<div class="fila"><span class="n"><i class="punto" style="background:${s.color}"></i>${esc(s.etiqueta)}</span>` +
        `<span class="v">${n1(s.serie.p[i])}${marca}</span></div>`;
    }).join("");
    if (!filas) { this.globo.style.display = "none"; return; }
    this.globo.innerHTML = `<div class="t">${mmss(t)}  ·  ${t.toFixed(1)} s</div>${filas}`;
    this.globo.style.display = "block";
    const gw = this.globo.offsetWidth, gh = this.globo.offsetHeight;
    this.globo.style.left = Math.min(x + 14, this.cv.clientWidth - gw - 4) + "px";
    this.globo.style.top = Math.max(4, Math.min(y - gh / 2, this.cv.clientHeight - gh - 4)) + "px";
  }
}

function pasoLindo(bruto) {
  const e = Math.pow(10, Math.floor(Math.log10(Math.max(bruto, 1e-6))));
  return [1, 2, 2.5, 5, 10].find(m => bruto <= m * e) * e;
}
function pasoTiempo(bruto) {
  return [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600].find(p => bruto <= p) || 600;
}

const grafica = new Grafica($("#grafica"), $("#globo"));

function sincronizarChips() {
  $("#chips-series").innerHTML = series.map(s =>
    `<span class="serie-chip ${s.visible ? "" : "apagada"}" data-id="${s.id}">
       <i class="muestra" style="background:${s.color}"></i>${esc(s.etiqueta)}</span>`).join("") +
    `<span class="sep"></span><button class="boton" id="btn-todas">Todas</button>`;
  $$("#chips-series .serie-chip").forEach(ch => ch.addEventListener("click", () => {
    const s = series.find(x => x.id === ch.dataset.id);
    s.visible = !s.visible;
    sincronizarChips(); grafica.dibujar();
  }));
  $("#btn-todas").addEventListener("click", () => {
    series.forEach(s => s.visible = true);
    sincronizarChips(); grafica.reiniciar();
  });
}
["#chk-envolvente", "#chk-censura", "#chk-limites", "#chk-cursores"].forEach(id =>
  $(id).addEventListener("change", () => grafica.dibujar()));
$("#btn-reset").addEventListener("click", () => grafica.reiniciar());

$("#btn-exportar").addEventListener("click", () => {
  const v = grafica.vista, vis = series.filter(s => s.visible);
  const lin = ["sujeto,condicion,t_s,pura_cmH2O,pura_min_cmH2O,pura_max_cmH2O,censura"];
  vis.forEach(s => {
    const i0 = Math.max(0, Math.ceil(iEn(s.serie, v.t0))), i1 = Math.min(s.serie.n - 1, Math.floor(iEn(s.serie, v.t1)));
    for (let i = i0; i <= i1; i++) {
      const c = s.serie.c[i];
      lin.push(`${s.ses.sujeto},${s.ses.condicion},${tEn(s.serie, i).toFixed(1)},` +
        `${s.serie.p[i]},${s.serie.lo[i]},${s.serie.hi[i]},${c === "-" ? -1 : c === "+" ? 1 : 0}`);
    }
  });
  const url = URL.createObjectURL(new Blob([lin.join("\n") + "\n"], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `pura_${Math.round(v.t0)}-${Math.round(v.t1)}s.csv`;
  a.click(); URL.revokeObjectURL(url);
});

/* ================= CAPTURAS ================= */

const CAPTURAS = D.sesiones.flatMap(s => s.capturas.map(c => Object.assign({ ses: s }, c)));
let ordenCap = { campo: "captura", asc: true };
let condsActivas = new Set(D.sesiones.map(s => s.condicion));

const COLS_CAP = [
  { k: "captura", t: "Captura", izq: true, v: c => `<span class="cond-punto" style="background:${c.ses.color}"></span>${esc(c.captura)}` },
  { k: "condicion", t: "Condición", izq: true, v: c => esc(c.ses.condicion) },
  { k: "t_inicio_s", t: "Inicio", v: c => mmssCorto(c.t_inicio_s), titulo: "Instante del registro en que empieza la captura" },
  { k: "t_fin_s", t: "Fin", v: c => mmssCorto(c.t_fin_s) },
  { k: "muestras", t: "Muestras", v: c => c.muestras },
  { k: "piso", t: "Piso", v: c => c.piso, titulo: "Muestras en el piso del panel" },
  { k: "techo", t: "Techo", v: c => c.techo, titulo: "Muestras saturadas en 300 cm H₂O" },
  { k: "pura_max_valida", t: "Máx válido", v: c => n1(c.pura_max_valida) },
  { k: "pura_final", t: "Final", v: c => n1(c.pura_final), titulo: "Último valor reconstruido" },
  { k: "pura_pantalla", t: "Pantalla", v: c => n1(c.pura_pantalla), titulo: "Valor que muestra el equipo" },
  { k: "dif_final_vs_pantalla", t: "Δ", v: c => n1(c.dif_final_vs_pantalla), titulo: "Reconstruido − pantalla (cm H₂O)" },
  { k: "estado", t: "Estado", izq: true, v: c => marcaEstado(c.estado) },
  { k: "notas", t: "Notas", izq: true, clase: "obs", v: c => esc(c.notas || "") },
];

function marcaEstado(e) {
  const cl = e === "OK" ? "ok" : e === "OK_PISO" ? "piso" : "revisar";
  return `<span class="marca ${cl}">${esc(e)}</span>`;
}

function pintarCapturas() {
  const q = $("#busca-captura").value.trim().toLowerCase();
  let filas = CAPTURAS.filter(c => condsActivas.has(c.ses.condicion))
    .filter(c => !q || [c.captura, c.ses.condicion, c.estado, c.notas].join(" ").toLowerCase().includes(q));

  const { campo, asc } = ordenCap;
  filas.sort((a, b) => {
    const va = campo === "condicion" ? a.ses.orden : a[campo], vb = campo === "condicion" ? b.ses.orden : b[campo];
    const c = (typeof va === "number" && typeof vb === "number") ? va - vb : String(va).localeCompare(String(vb), "es");
    return asc ? c : -c;
  });

  tabla($("#tabla-capturas"),
    COLS_CAP.map(c => ({ t: c.t, izq: c.izq, titulo: c.titulo })),
    filas.map(c => `<tr data-cap="${c.captura}">` +
      COLS_CAP.map(col => `<td class="${col.izq ? "izq" : ""} ${col.clase || ""}">${col.v(c)}</td>`).join("") + "</tr>"));

  $$("#tabla-capturas thead th").forEach((th, i) => {
    const k = COLS_CAP[i].k;
    th.classList.toggle("orden", k === campo);
    th.classList.toggle("asc", k === campo && asc);
    th.addEventListener("click", () => {
      ordenCap = { campo: k, asc: k === campo ? !asc : true };
      pintarCapturas();
    });
  });
  $$("#tabla-capturas tbody tr").forEach(tr => tr.addEventListener("click", () => mostrarCaptura(tr.dataset.cap)));
  $("#conteo-capturas").textContent = `${filas.length} de ${CAPTURAS.length} capturas`;
  if (capturaActual) $$(`#tabla-capturas tr[data-cap="${capturaActual}"]`).forEach(tr => tr.classList.add("sel"));
}

let capturaActual = null;
function mostrarCaptura(nombre) {
  const c = CAPTURAS.find(x => x.captura === nombre);
  capturaActual = nombre;
  $$("#tabla-capturas tbody tr").forEach(tr => tr.classList.toggle("sel", tr.dataset.cap === nombre));

  const d = (t, v) => `<dt>${t}</dt><dd>${v}</dd>`;
  $("#detalle-captura").innerHTML = `
    <h2><span class="cond-punto" style="background:${c.ses.color}"></span>${esc(c.captura)} · ${esc(c.ses.condicion)}
        ${marcaEstado(c.estado)}</h2>
    <p class="nota">${esc(c.notas || "Sin observaciones.")}</p>
    <div class="detalle">
      <div>
        <img src="${c.img.verificacion}" alt="Verificación de ${esc(c.captura)}" loading="lazy">
        <p class="pie-img">Verificación: curva reconstruida sobre el recorte, y el tiempo calculado para
           cada marca mayor de la regla (en azul) frente al rótulo impreso por el equipo.</p>
        <img src="${c.img.recorte}" alt="Recorte de ${esc(c.captura)}" loading="lazy">
        <p class="pie-img">Recorte de trabajo (regla, Vol. infundido y panel Pura).</p>
        <img src="${c.img.pantalla}" alt="Pantalla completa de ${esc(c.captura)}" loading="lazy">
        <p class="pie-img">Captura completa de la pantalla del equipo.</p>
      </div>
      <div>
        <h4>Tiempo</h4>
        <dl>
          ${d("Rótulo de referencia", esc(c.rotulo_ref))}
          ${d("t de referencia", c.t_ref_s + " s")}
          ${d("Intervalo", `${mmssCorto(c.t_inicio_s)} – ${mmssCorto(c.t_fin_s)}`)}
          ${d("Duración", n1(c.t_fin_s - c.t_inicio_s) + " s")}
          ${d("px por segundo", n4(c.px_por_seg))}
          ${d("Marcas de la regla", `${c.calib.regla_marcas} (${c.calib.regla_marcas_mayores} mayores)`)}
          ${d("RMS del ajuste", n3(c.regla_rms_px) + " px")}
          ${d("Residuo máximo", n3(c.calib.regla_residuo_max_px) + " px")}
          ${d("Coherencia de mayores", n3(c.regla_coherencia_mayores))}
        </dl>
        <hr>
        <h4>Panel de presión</h4>
        <dl>
          ${d("Bordes (y px)", `${c.panel_y_top} – ${c.panel_y_bot}`)}
          ${d("Escala", n4(c.cmH2O_por_px) + " cm H₂O/px")}
          ${d("Columnas útiles", `${c.x_inicio} – ${c.x_fin}`)}
          ${d("Tamaño del recorte", (c.calib.tamano_px || []).join(" × ") + " px")}
        </dl>
        <hr>
        <h4>Serie</h4>
        <dl>
          ${d("Muestras", c.muestras)}
          ${d("En el piso", `${c.piso} (${n1(100 * c.piso / c.muestras)} %)`)}
          ${d("En el techo", `${c.techo} (${n1(100 * c.techo / c.muestras)} %)`)}
          ${d("Máximo válido", n1(c.pura_max_valida) + " cm H₂O")}
          ${d("Valor final", n1(c.pura_final) + " cm H₂O")}
          ${d("Pantalla", n1(c.pura_pantalla) + " cm H₂O")}
          ${d("Diferencia", n1(c.dif_final_vs_pantalla) + " cm H₂O")}
          ${d("Cursores del equipo", (c.calib.cursores_s || []).length)}
          ${d("Bandas sombreadas", c.calib.n_bandas)}
        </dl>
        <hr>
        <button class="boton" data-ver="${c.ses.id}" data-t0="${c.t_inicio_s}" data-t1="${c.t_fin_s}">
          Ver este tramo en la gráfica</button>
      </div>
    </div>`;

  $$("#detalle-captura img").forEach(im => im.addEventListener("click", () => {
    $("#visor img").src = im.src; $("#visor").classList.add("abierto");
  }));
  const btn = $("#detalle-captura [data-ver]");
  btn.addEventListener("click", () => {
    series.forEach(s => s.visible = s.id === btn.dataset.ver);
    sincronizarChips();
    abrirVista("curvas");
    grafica.redimensionar();
    grafica.fijarVista(+btn.dataset.t0, +btn.dataset.t1);
  });
  $("#detalle-captura").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

$("#visor").addEventListener("click", () => $("#visor").classList.remove("abierto"));
document.addEventListener("keydown", e => { if (e.key === "Escape") $("#visor").classList.remove("abierto"); });
$("#busca-captura").addEventListener("input", pintarCapturas);

$("#filtros-cond").innerHTML = D.sesiones.map(s =>
  `<span class="serie-chip" data-cond="${esc(s.condicion)}"><i class="muestra" style="background:${s.color}"></i>${esc(s.condicion)}</span>`).join("");
$$("#filtros-cond .serie-chip").forEach(ch => ch.addEventListener("click", () => {
  const c = ch.dataset.cond;
  if (condsActivas.has(c)) condsActivas.delete(c); else condsActivas.add(c);
  if (!condsActivas.size) D.sesiones.forEach(s => condsActivas.add(s.condicion));
  $$("#filtros-cond .serie-chip").forEach(x => x.classList.toggle("apagada", !condsActivas.has(x.dataset.cond)));
  pintarCapturas();
}));

/* ================= VALIDACIÓN ================= */

function pintarValidacion() {
  const tope = Math.max.apply(null, CAPTURAS.map(c => Math.abs(c.dif_final_vs_pantalla))) || 1;
  tabla($("#tabla-pantalla"), [
    { t: "Captura", izq: true }, { t: "Condición", izq: true }, { t: "Reconstruido" },
    { t: "Pantalla" }, { t: "Δ (cm H₂O)" }, { t: "Estado", izq: true }, { t: "", izq: true },
  ], CAPTURAS.map(c => `<tr>
      <td class="izq"><span class="cond-punto" style="background:${c.ses.color}"></span>${esc(c.captura)}</td>
      <td class="izq">${esc(c.ses.condicion)}</td>
      <td>${n1(c.pura_final)}</td>
      <td>${n1(c.pura_pantalla)}</td>
      <td>${n1(c.dif_final_vs_pantalla)}</td>
      <td class="izq">${marcaEstado(c.estado)}</td>
      <td class="izq"><div class="barra" style="--c:${c.ses.color}">
        <i style="width:${(100 * Math.abs(c.dif_final_vs_pantalla) / tope).toFixed(1)}%"></i></div></td>
    </tr>`));

  const solapes = D.sesiones.flatMap(s => s.solapamientos.map(o => Object.assign({ ses: s }, o)));
  tabla($("#tabla-solapes"), [
    { t: "Condición", izq: true }, { t: "Par", izq: true },
    { t: "Solape", titulo: "Duración del intervalo común (s)" },
    { t: "Comparable", titulo: "Parte del solape con muestras válidas en ambas (s)" },
    { t: "Dif. media" }, { t: "Dif. RMS" }, { t: "Desfase" }, { t: "Correlación" },
  ], solapes.map(o => `<tr>
      <td class="izq"><span class="cond-punto" style="background:${o.ses.color}"></span>${esc(o.condicion)}</td>
      <td class="izq">${esc(o.captura_a)} → ${esc(o.captura_b)}</td>
      <td>${n1(o.solape_s)} s</td>
      <td>${n1(o.solape_valido_s)} s</td>
      <td>${o.dif_media === null ? "—" : n3(o.dif_media)}</td>
      <td>${o.dif_rms === null ? "—" : n3(o.dif_rms)}</td>
      <td>${o.desfase_s === null ? "—" : n1(o.desfase_s) + " s"}</td>
      <td>${o.correlacion === null ? "—" : n3(o.correlacion)}</td>
    </tr>`));

  tabla($("#tabla-calib"), [
    { t: "Captura", izq: true }, { t: "Condición", izq: true },
    { t: "Panel (y px)" }, { t: "cm H₂O/px" }, { t: "px/s" },
    { t: "RMS regla (px)" }, { t: "Residuo máx (px)" }, { t: "Coherencia" }, { t: "Marcas" },
  ], CAPTURAS.map(c => `<tr>
      <td class="izq"><span class="cond-punto" style="background:${c.ses.color}"></span>${esc(c.captura)}</td>
      <td class="izq">${esc(c.ses.condicion)}</td>
      <td>${c.panel_y_top} – ${c.panel_y_bot}</td>
      <td>${n4(c.cmH2O_por_px)}</td>
      <td>${n4(c.px_por_seg)}</td>
      <td>${n3(c.regla_rms_px)}</td>
      <td>${n3(c.calib.regla_residuo_max_px)}</td>
      <td>${n3(c.regla_coherencia_mayores)}</td>
      <td>${c.calib.regla_marcas} / ${c.calib.regla_marcas_mayores}</td>
    </tr>`));
}

/* ================= GUÍA ================= */

tabla($("#tabla-diccionario"), [{ t: "Columna", izq: true }, { t: "Descripción", izq: true }],
  D.diccionario.map(r => `<tr><td class="izq"><code>${esc(r.columna)}</code></td><td class="izq obs">${esc(r.descripcion)}</td></tr>`));
tabla($("#tabla-estados"), [{ t: "Estado", izq: true }, { t: "Significado", izq: true }],
  D.estados.map(r => `<tr><td class="izq">${marcaEstado(r.estado)}</td><td class="izq obs">${esc(r.descripcion)}</td></tr>`));

/* ================= arranque ================= */

pintarSesiones();
pintarComparacion();
sincronizarChips();
pintarCapturas();
pintarValidacion();
grafica.dibujar();

const inicial = (location.hash || "").replace("#", "");
if (["resumen", "curvas", "capturas", "validacion", "guia"].includes(inicial)) abrirVista(inicial);

})();
