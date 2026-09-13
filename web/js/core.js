"use strict";

// ---- данные страницы и подстановка надписей ----------------------------------------------
const DATA = JSON.parse(document.getElementById("mb-data").textContent);
// Надписи страницы приходят готовыми из словаря языка: в скрипте их нет, как и в ядре.
const T = DATA.texts;
// Подстановка ИМЕНАМИ, а не по месту: в другом языке порядок слов другой.
function say(text, values) {
  return String(text).replace(/%\((\w+)\)s/g, (whole, name) =>
    name in values ? String(values[name]) : whole);
}

// ---- вспомогательное --------------------------------------------------------------------
const mod360 = (x) => ((x % 360) + 360) % 360;
const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
// Округление как у round() в Python - к ближайшему чётному на ровной половине, - чтобы
// as_dict страницы и ядра давали одни и те же числа.
const rnd = (x, digits) => {
  const k = Math.pow(10, digits), s = x * k;
  if (Number.isInteger(s * 2) && !Number.isInteger(s)) {
    // Точная двоичная половина (0.125, 22.25): к чётному, как round() в Python.
    const f = Math.floor(s);
    return (f % 2 === 0 ? f : f + 1) / k;
  }
  // Остальное - к ближайшему по десятичной записи: toFixed округляет верно там, где
  // произведение x·k уже наврало бы в последнем знаке.
  return Number(x.toFixed(digits));
};
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const norm = (a) => Math.sqrt(dot(a, a));
const fmt = (x) => String(rnd(x, 3));

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) for (const k in attrs) {
    if (k === "text") node.textContent = attrs[k];
    else if (k === "on") for (const ev in attrs.on) node.addEventListener(ev, attrs.on[ev]);
    else if (k === "class") node.className = attrs[k];
    else node.setAttribute(k, attrs[k]);
  }
  if (children) for (const c of children) if (c) node.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  return node;
}

// ---- распаковка вложенных массивов ------------------------------------------------------
// Каждый массив приходит строкой base64; раскладывается в свежий буфер, поэтому смещение
// нулевое и типизированное представление ложится на него без выравнивания.
const Codec = {
  bytes(b64) {
    const bin = atob(b64), n = bin.length, out = new Uint8Array(n);
    for (let i = 0; i < n; i++) out[i] = bin.charCodeAt(i);
    return out;
  },
  f32(b64) { const u = this.bytes(b64); return new Float32Array(u.buffer, 0, u.length >> 2); },
  i16(b64) { const u = this.bytes(b64); return new Int16Array(u.buffer, 0, u.length >> 1); },
  u8(b64) { return this.bytes(b64); },
  index(b64, kind) {
    const u = this.bytes(b64);
    return kind === "u32" ? new Uint32Array(u.buffer, 0, u.length >> 2)
                          : new Uint16Array(u.buffer, 0, u.length >> 1);
  },
};

// ---- палитры: перенос из presenters/raster.py один в один --------------------------------
const Palette = {
  NO_BONE: [0.30, 0.30, 0.33],
  SHADE: 0.72,

  // colorsys.hsv_to_rgb из стандартной библиотеки Python, чтобы цвета сошлись до бита.
  hsvToRgb(h, s, v) {
    if (s === 0.0) return [v, v, v];
    let i = Math.trunc(h * 6.0);
    const f = (h * 6.0) - i;
    const p = v * (1.0 - s), q = v * (1.0 - s * f), t = v * (1.0 - s * (1.0 - f));
    i = i % 6;
    if (i === 0) return [v, t, p];
    if (i === 1) return [q, v, p];
    if (i === 2) return [p, v, t];
    if (i === 3) return [p, q, v];
    if (i === 4) return [t, p, v];
    return [v, p, q];
  },

  // Разные кости - заметно разные цвета: золотой угол по кругу оттенков.
  bones(count) {
    const n = Math.max(count, 1), out = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const h = (i * 0.61803398875) % 1.0;
      const s = 0.55 + 0.25 * ((i * 7) % 3) / 2.0;
      const v = 0.70 + 0.25 * ((i * 5) % 2);
      const rgb = this.hsvToRgb(h, s, v);
      out[i * 3] = rgb[0]; out[i * 3 + 1] = rgb[1]; out[i * 3 + 2] = rgb[2];
    }
    return out;
  },

  // Серое - ноль, дальше жёлтое и красное; нормировка на максимум переданного признака -
  // как в растеризаторе, где признак берётся по одной части меша.
  heat(values) {
    const n = values.length, out = new Float32Array(n * 3);
    let top = 0.0;
    for (let i = 0; i < n; i++) if (values[i] > top) top = values[i];
    for (let i = 0; i < n; i++) {
      const t = top <= 1e-6 ? 0.0 : clamp(values[i] / top, 0.0, 1.0);
      out[i * 3] = 0.35 + 0.65 * t;
      out[i * 3 + 1] = 0.35 + 0.55 * clamp(1.6 * t, 0, 1) * (1.0 - 0.85 * t);
      out[i * 3 + 2] = 0.35 * (1.0 - t);
    }
    return out;
  },
};

// ---- зеркало morphbench/model.py: vertex_normals ------------------------------------------
// Нормаль в каждой вершине: сумма нормалей прилегающих треугольников, взвешенных их площадью
// (длина векторного произведения - удвоенная площадь, вес выходит сам собой), приведённая
// к единичной длине. Вершина без треугольников смотрит вверх, (0, 0, 1).
function vertexNormals(pos, tris, out) {
  out.fill(0);
  for (let t = 0, n = tris.length; t < n; t += 3) {
    const a = tris[t] * 3, b = tris[t + 1] * 3, c = tris[t + 2] * 3;
    const abx = pos[b] - pos[a], aby = pos[b + 1] - pos[a + 1], abz = pos[b + 2] - pos[a + 2];
    const acx = pos[c] - pos[a], acy = pos[c + 1] - pos[a + 1], acz = pos[c + 2] - pos[a + 2];
    const nx = aby * acz - abz * acy, ny = abz * acx - abx * acz, nz = abx * acy - aby * acx;
    out[a] += nx; out[a + 1] += ny; out[a + 2] += nz;
    out[b] += nx; out[b + 1] += ny; out[b + 2] += nz;
    out[c] += nx; out[c + 1] += ny; out[c + 2] += nz;
  }
  for (let i = 0, n = out.length; i < n; i += 3) {
    const l = Math.sqrt(out[i] * out[i] + out[i + 1] * out[i + 1] + out[i + 2] * out[i + 2]);
    if (l < 1e-12) { out[i] = 0; out[i + 1] = 0; out[i + 2] = 1; }
    else { out[i] /= l; out[i + 1] /= l; out[i + 2] /= l; }
  }
  return out;
}
