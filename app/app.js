"use strict";

/* ---------- theme-aware chart tokens (read from CSS custom properties) ---------- */
const css = () => getComputedStyle(document.documentElement);
const tok = (name) => css().getPropertyValue(name).trim();

/* ---------- StripChart: scrolling realtime line chart ---------- */
class StripChart {
  constructor(canvas, series, { windowSec = 10, unit = "" } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.series = series; // [{key, label, colorVar}]
    this.windowSec = windowSec;
    this.unit = unit;
    this.buf = []; // {t, v:[...]}
    this.cursor = null; // pointer x position (CSS px) or null
    this.resize();
    new ResizeObserver(() => this.resize()).observe(canvas);
    canvas.addEventListener("pointerdown", (e) => this.onPointer(e));
    canvas.addEventListener("pointermove", (e) => this.onPointer(e));
    canvas.addEventListener("pointerleave", () => { this.cursor = null; });
    canvas.addEventListener("pointerup", () => { this.cursor = null; });
  }
  onPointer(e) {
    if (e.pointerType === "mouse" && e.buttons === 0 && e.type === "pointermove") {
      this.cursor = e.offsetX; return;
    }
    if (e.type === "pointerdown" || e.buttons > 0) this.cursor = e.offsetX;
  }
  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const r = this.canvas.getBoundingClientRect();
    if (r.width === 0) return;
    this.canvas.width = Math.round(r.width * dpr);
    this.canvas.height = Math.round(r.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = r.width; this.h = r.height;
  }
  push(t, values) {
    this.buf.push({ t, v: values });
    const cutoff = t - this.windowSec * 1000 - 500;
    while (this.buf.length && this.buf[0].t < cutoff) this.buf.shift();
  }
  draw() {
    const { ctx, w, h } = this;
    if (!w) return;
    ctx.clearRect(0, 0, w, h);
    const now = performance.now();
    const t0 = now - this.windowSec * 1000;
    // y-range over visible window
    let min = Infinity, max = -Infinity;
    for (const p of this.buf) for (const v of p.v) {
      if (v == null || !isFinite(v)) continue;
      if (v < min) min = v; if (v > max) max = v;
    }
    if (!isFinite(min)) { min = -1; max = 1; }
    if (max - min < 1e-6) { min -= 1; max += 1; }
    const pad = (max - min) * 0.12;
    min -= pad; max += pad;
    const y = (v) => h - ((v - min) / (max - min)) * h;
    const x = (t) => ((t - t0) / (this.windowSec * 1000)) * w;

    // hairline grid: 3 horizontal lines + labels (muted, tabular)
    ctx.strokeStyle = tok("--grid"); ctx.lineWidth = 1;
    ctx.fillStyle = tok("--muted");
    ctx.font = "10px system-ui, sans-serif";
    ctx.textBaseline = "bottom";
    for (let i = 1; i <= 3; i++) {
      const gy = (h / 4) * i;
      ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke();
      const gv = min + (max - min) * (1 - i / 4);
      ctx.fillText(fmt(gv), 4, gy - 2);
    }
    // series lines, 2px
    this.series.forEach((s, i) => {
      ctx.strokeStyle = tok(s.colorVar);
      ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.lineCap = "round";
      ctx.beginPath();
      let started = false;
      for (const p of this.buf) {
        const v = p.v[i];
        if (v == null || !isFinite(v)) { started = false; continue; }
        const px = x(p.t), py = y(v);
        if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
      }
      ctx.stroke();
    });
    // crosshair + tooltip at cursor
    if (this.cursor != null && this.buf.length) {
      const ct = t0 + (this.cursor / w) * this.windowSec * 1000;
      let best = this.buf[0];
      for (const p of this.buf) if (Math.abs(p.t - ct) < Math.abs(best.t - ct)) best = p;
      const cx = x(best.t);
      ctx.strokeStyle = tok("--axis"); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, h); ctx.stroke();
      this.series.forEach((s, i) => {
        const v = best.v[i];
        if (v == null || !isFinite(v)) return;
        ctx.fillStyle = tok(s.colorVar);
        ctx.beginPath(); ctx.arc(cx, y(v), 4, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = tok("--surface-1"); ctx.lineWidth = 2; ctx.stroke();
      });
      const lines = this.series.map((s, i) => `${s.label} ${fmt(best.v[i])}`);
      ctx.font = "11px system-ui, sans-serif";
      const tw = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 12;
      const th = lines.length * 15 + 8;
      const bx = Math.min(Math.max(cx + 8, 2), w - tw - 2);
      const by = 4;
      ctx.fillStyle = tok("--surface-1");
      ctx.strokeStyle = tok("--axis"); ctx.lineWidth = 1;
      roundRect(ctx, bx, by, tw, th, 6); ctx.fill(); ctx.stroke();
      ctx.textBaseline = "top";
      lines.forEach((l, i) => {
        ctx.fillStyle = tok(this.series[i].colorVar);
        ctx.fillRect(bx + 5, by + 8 + i * 15, 6, 6);
        ctx.fillStyle = tok("--text-primary");
        ctx.fillText(l, bx + 15, by + 5 + i * 15);
      });
    }
  }
}
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function fmt(v) {
  if (v == null || !isFinite(v)) return "–";
  const a = Math.abs(v);
  return v.toFixed(a >= 100 ? 0 : a >= 10 ? 1 : 2);
}

/* ---------- legends with live values (direct labels) ---------- */
function buildLegend(el, series) {
  el.innerHTML = "";
  return series.map((s) => {
    const item = document.createElement("span");
    item.className = "item";
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.style.background = `var(${s.colorVar})`;
    const name = document.createElement("span");
    name.textContent = s.label;
    const val = document.createElement("span");
    val.className = "val";
    val.textContent = "–";
    item.append(chip, name, val);
    el.append(item);
    return val;
  });
}

/* ---------- recorder ---------- */
const recorder = {
  active: false,
  startedAt: 0,
  rows: { accel: [], gyro: [], orientation: [], gps: [], mic: [] },
  count: 0,
  LIMIT: 1_000_000,
  start() {
    this.rows = { accel: [], gyro: [], orientation: [], gps: [], mic: [] };
    this.count = 0;
    this.startedAt = Date.now();
    this.perfStart = performance.now();
    this.active = true;
  },
  stop() { this.active = false; },
  add(sensor, values) {
    if (!this.active) return;
    const elapsed = Math.round(performance.now() - this.perfStart);
    this.rows[sensor].push([elapsed, ...values]);
    if (++this.count >= this.LIMIT) {
      this.active = false;
      stopRecordingUI();
      alert("記録行数が上限(100万行)に達したため記録を停止しました。");
    }
  },
  hasData() { return this.count > 0; },
};

const CSV_HEADERS = {
  accel: "elapsed_ms,ax_ms2,ay_ms2,az_ms2",
  gyro: "elapsed_ms,gx_degs,gy_degs,gz_degs",
  orientation: "elapsed_ms,alpha_deg,beta_deg,gamma_deg,compass_deg",
  gps: "elapsed_ms,lat,lon,alt_m,speed_ms,accuracy_m",
  mic: "elapsed_ms,level_dbfs",
};

async function exportCSV() {
  const stamp = new Date(recorder.startedAt).toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const files = [];
  for (const [sensor, rows] of Object.entries(recorder.rows)) {
    if (!rows.length) continue;
    const csv = CSV_HEADERS[sensor] + "\n" +
      rows.map((r) => r.map((v) => (v == null || !isFinite(v) ? "" : round6(v))).join(",")).join("\n");
    files.push(new File([csv], `sensorlog_${stamp}_${sensor}.csv`, { type: "text/csv" }));
  }
  if (!files.length) return;
  if (navigator.canShare && navigator.canShare({ files })) {
    try { await navigator.share({ files, title: "SensorLog CSV" }); return; }
    catch (e) { if (e.name === "AbortError") return; /* fall through to download */ }
  }
  for (const f of files) {
    const url = URL.createObjectURL(f);
    const a = document.createElement("a");
    a.href = url; a.download = f.name;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }
}
function round6(v) { return Math.round(v * 1e6) / 1e6; }

/* ---------- server sender ---------- */
const sender = {
  queue: [],
  MAX_QUEUE: 20000,
  deviceId: localStorage.getItem("deviceId") ||
    (() => { const id = crypto.randomUUID(); localStorage.setItem("deviceId", id); return id; })(),
  sessionId: crypto.randomUUID(),
  enabled: localStorage.getItem("sendEnabled") === "1",
  endpoint: localStorage.getItem("endpoint") || "",
  timer: null,
  lastStatus: "",
  add(sensor, values) {
    if (!this.enabled || !this.endpoint) return;
    this.queue.push({ t: Date.now(), sensor, v: values });
    if (this.queue.length > this.MAX_QUEUE) this.queue.splice(0, this.queue.length - this.MAX_QUEUE);
  },
  startLoop() {
    if (this.timer) return;
    this.timer = setInterval(() => this.flush(), 2000);
  },
  async flush() {
    if (!this.enabled || !this.endpoint || !this.queue.length) return;
    const batch = this.queue.splice(0, 5000);
    try {
      const res = await fetch(this.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: this.deviceId, session_id: this.sessionId, samples: batch }),
      });
      this.lastStatus = res.ok
        ? `送信OK: ${batch.length}件 (${new Date().toLocaleTimeString()})`
        : `送信エラー: HTTP ${res.status}`;
      if (!res.ok) this.requeue(batch);
    } catch (e) {
      this.lastStatus = `送信失敗: ${e.message}`;
      this.requeue(batch);
    }
    els.sendStat.textContent = this.lastStatus;
  },
  requeue(batch) {
    this.queue.unshift(...batch.slice(-2000));
  },
};

/* ---------- DOM refs ---------- */
const $ = (id) => document.getElementById(id);
const els = {
  tglMotion: $("tglMotion"), tglOrient: $("tglOrient"), tglGps: $("tglGps"), tglMic: $("tglMic"),
  errMotion: $("errMotion"), errOrient: $("errOrient"), errGps: $("errGps"), errMic: $("errMic"),
  vHeading: $("vHeading"), vBeta: $("vBeta"), vGamma: $("vGamma"),
  vLat: $("vLat"), vLon: $("vLon"), vSpeed: $("vSpeed"), vAlt: $("vAlt"), vAcc: $("vAcc"),
  btnRec: $("btnRec"), btnExport: $("btnExport"), btnSettings: $("btnSettings"),
  recBadge: $("recBadge"), recTime: $("recTime"), sendStat: $("sendStat"),
  dlg: $("dlgSettings"), inpEndpoint: $("inpEndpoint"), tglSend: $("tglSend"),
};
function showErr(el, msg) { el.textContent = msg; el.classList.add("show"); }
function clearErr(el) { el.classList.remove("show"); }

/* ---------- charts ---------- */
const SER3 = (labels) => [
  { label: labels[0], colorVar: "--series-1" },
  { label: labels[1], colorVar: "--series-2" },
  { label: labels[2], colorVar: "--series-3" },
];
const chAccel = new StripChart($("chAccel"), SER3(["X", "Y", "Z"]));
const chGyro = new StripChart($("chGyro"), SER3(["X", "Y", "Z"]));
const chMic = new StripChart($("chMic"), [{ label: "音量", colorVar: "--series-1" }], { windowSec: 15 });
const legAccel = buildLegend($("legAccel"), chAccel.series);
const legGyro = buildLegend($("legGyro"), chGyro.series);
const legMic = buildLegend($("legMic"), chMic.series);

/* ---------- motion (accel + gyro) ---------- */
let motionOn = false;
let lastAccel = [null, null, null], lastGyro = [null, null, null];
function onMotion(e) {
  const t = performance.now();
  const a = e.acceleration && e.acceleration.x != null ? e.acceleration : e.accelerationIncludingGravity;
  if (a) {
    lastAccel = [a.x, a.y, a.z];
    chAccel.push(t, lastAccel);
    recorder.add("accel", lastAccel);
    sender.add("accel", lastAccel);
  }
  const r = e.rotationRate;
  if (r && r.alpha != null) {
    // spec: alpha=z-axis, beta=x-axis, gamma=y-axis — expose as X/Y/Z
    lastGyro = [r.beta, r.gamma, r.alpha];
    chGyro.push(t, lastGyro);
    recorder.add("gyro", lastGyro);
    sender.add("gyro", lastGyro);
  }
}
async function setMotion(on) {
  clearErr(els.errMotion);
  if (on) {
    try {
      if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
        const p = await DeviceMotionEvent.requestPermission();
        if (p !== "granted") throw new Error("許可されませんでした");
      }
      if (typeof DeviceMotionEvent === "undefined") throw new Error("この端末では利用できません");
      window.addEventListener("devicemotion", onMotion);
      motionOn = true;
    } catch (e) {
      showErr(els.errMotion, "加速度センサーを開始できません: " + e.message);
      els.tglMotion.checked = false;
    }
  } else {
    window.removeEventListener("devicemotion", onMotion);
    motionOn = false;
  }
}

/* ---------- orientation / compass ---------- */
let lastOrient = [null, null, null, null];
function onOrient(e) {
  const compass = e.webkitCompassHeading != null
    ? e.webkitCompassHeading
    : (e.absolute && e.alpha != null ? (360 - e.alpha) % 360 : null);
  lastOrient = [e.alpha, e.beta, e.gamma, compass];
  recorder.add("orientation", lastOrient);
  sender.add("orientation", lastOrient);
  els.vHeading.innerHTML = (compass != null ? Math.round(compass) : "–") + "<small> °</small>";
  els.vBeta.innerHTML = (e.beta != null ? Math.round(e.beta) : "–") + "<small> °</small>";
  els.vGamma.innerHTML = (e.gamma != null ? Math.round(e.gamma) : "–") + "<small> °</small>";
}
async function setOrient(on) {
  clearErr(els.errOrient);
  if (on) {
    try {
      if (typeof DeviceOrientationEvent !== "undefined" && typeof DeviceOrientationEvent.requestPermission === "function") {
        const p = await DeviceOrientationEvent.requestPermission();
        if (p !== "granted") throw new Error("許可されませんでした");
      }
      if (typeof DeviceOrientationEvent === "undefined") throw new Error("この端末では利用できません");
      window.addEventListener("deviceorientation", onOrient);
    } catch (e) {
      showErr(els.errOrient, "方位センサーを開始できません: " + e.message);
      els.tglOrient.checked = false;
    }
  } else {
    window.removeEventListener("deviceorientation", onOrient);
  }
}

/* ---------- GPS ---------- */
let gpsWatch = null;
function setGps(on) {
  clearErr(els.errGps);
  if (on) {
    if (!navigator.geolocation) {
      showErr(els.errGps, "この端末では位置情報を利用できません");
      els.tglGps.checked = false;
      return;
    }
    gpsWatch = navigator.geolocation.watchPosition(
      (pos) => {
        const c = pos.coords;
        const row = [c.latitude, c.longitude, c.altitude, c.speed, c.accuracy];
        recorder.add("gps", row);
        sender.add("gps", row);
        els.vLat.textContent = c.latitude.toFixed(6);
        els.vLon.textContent = c.longitude.toFixed(6);
        els.vSpeed.innerHTML = (c.speed != null ? (c.speed * 3.6).toFixed(1) : "–") + "<small> km/h</small>";
        els.vAlt.innerHTML = (c.altitude != null ? c.altitude.toFixed(0) : "–") + "<small> m</small>";
        els.vAcc.innerHTML = "±" + c.accuracy.toFixed(0) + "<small> m</small>";
      },
      (err) => {
        showErr(els.errGps, "位置情報エラー: " + err.message);
        els.tglGps.checked = false;
      },
      { enableHighAccuracy: true, maximumAge: 1000, timeout: 15000 }
    );
  } else if (gpsWatch != null) {
    navigator.geolocation.clearWatch(gpsWatch);
    gpsWatch = null;
  }
}

/* ---------- mic level ---------- */
let audioCtx = null, analyser = null, micStream = null, micBuf = null, lastMicPush = 0;
async function setMic(on) {
  clearErr(els.errMic);
  if (on) {
    try {
      micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const src = audioCtx.createMediaStreamSource(micStream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      src.connect(analyser);
      micBuf = new Float32Array(analyser.fftSize);
    } catch (e) {
      showErr(els.errMic, "マイクを開始できません: " + e.message);
      els.tglMic.checked = false;
    }
  } else {
    if (micStream) micStream.getTracks().forEach((tr) => tr.stop());
    if (audioCtx) audioCtx.close();
    audioCtx = analyser = micStream = null;
  }
}
function sampleMic(t) {
  if (!analyser) return;
  analyser.getFloatTimeDomainData(micBuf);
  let sum = 0;
  for (let i = 0; i < micBuf.length; i++) sum += micBuf[i] * micBuf[i];
  const rms = Math.sqrt(sum / micBuf.length);
  const db = Math.max(-90, 20 * Math.log10(rms || 1e-9));
  chMic.push(t, [db]);
  if (t - lastMicPush > 50) { // record/send at ~20 Hz
    lastMicPush = t;
    recorder.add("mic", [db]);
    sender.add("mic", [db]);
  }
}

/* ---------- render loop ---------- */
let frame = 0;
function loop(t) {
  sampleMic(t);
  chAccel.draw(); chGyro.draw(); chMic.draw();
  if (++frame % 6 === 0) { // legend values at ~10 Hz
    legAccel.forEach((el, i) => (el.textContent = fmt(lastAccel[i])));
    legGyro.forEach((el, i) => (el.textContent = fmt(lastGyro[i])));
    legMic[0].textContent = chMic.buf.length ? fmt(chMic.buf[chMic.buf.length - 1].v[0]) : "–";
    if (recorder.active) {
      const s = Math.floor((performance.now() - recorder.perfStart) / 1000);
      els.recTime.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }
  }
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

/* ---------- recording UI ---------- */
let wakeLock = null;
async function requestWakeLock() {
  try { wakeLock = await navigator.wakeLock?.request("screen"); } catch { /* not critical */ }
}
function startRecordingUI() {
  recorder.start();
  els.btnRec.textContent = "記録停止";
  els.btnRec.classList.remove("primary");
  els.btnRec.classList.add("danger");
  els.recBadge.classList.add("on");
  els.btnExport.disabled = true;
  requestWakeLock();
}
function stopRecordingUI() {
  recorder.stop();
  els.btnRec.textContent = "記録開始";
  els.btnRec.classList.add("primary");
  els.btnRec.classList.remove("danger");
  els.recBadge.classList.remove("on");
  els.btnExport.disabled = !recorder.hasData();
  wakeLock?.release(); wakeLock = null;
}
els.btnRec.addEventListener("click", () => {
  if (recorder.active) stopRecordingUI();
  else {
    if (!motionOn && !gpsWatch && !analyser && !els.tglOrient.checked) {
      alert("先に計測したいセンサーをONにしてください。");
      return;
    }
    startRecordingUI();
  }
});
els.btnExport.addEventListener("click", exportCSV);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && recorder.active) requestWakeLock();
});

/* ---------- settings ---------- */
els.btnSettings.addEventListener("click", () => {
  els.inpEndpoint.value = sender.endpoint;
  els.tglSend.checked = sender.enabled;
  els.dlg.showModal();
});
$("btnCloseSettings").addEventListener("click", () => els.dlg.close());
$("btnSaveSettings").addEventListener("click", () => {
  sender.endpoint = els.inpEndpoint.value.trim();
  sender.enabled = els.tglSend.checked && !!sender.endpoint;
  localStorage.setItem("endpoint", sender.endpoint);
  localStorage.setItem("sendEnabled", sender.enabled ? "1" : "0");
  els.sendStat.textContent = sender.enabled ? "サーバー送信: 有効" : "";
  els.dlg.close();
});
if (sender.enabled) els.sendStat.textContent = "サーバー送信: 有効";
sender.startLoop();

/* ---------- sensor toggles ---------- */
els.tglMotion.addEventListener("change", (e) => setMotion(e.target.checked));
els.tglOrient.addEventListener("change", (e) => setOrient(e.target.checked));
els.tglGps.addEventListener("change", (e) => setGps(e.target.checked));
els.tglMic.addEventListener("change", (e) => setMic(e.target.checked));

/* ---------- service worker ---------- */
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}
