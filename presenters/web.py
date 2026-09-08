"""Слой показа: самодостаточная страница со смотрелкой в браузере.

Один HTML-файл и ничего снаружи: ни библиотек, ни шрифтов, ни картинок, ни запросов. Всё, что
нужно, чтобы покрутить тело и потянуть ползунки, вложено внутрь - геометрия, морфы, признаки
раскраски, цели наведения, ракурсы и настройки. Открывается с диска, по file://, и живёт
столько, сколько живёт файл: страницу можно положить рядом с отчётом о прогоне.

Ничего не вычисляет сам - в том же смысле, что и растеризатор. Вершины, треугольники, номера
костей, смещения морфов и растяжение берутся у фасада и упаковываются в один блок JSON;
двоичные массивы - типизированные массивы в base64. Смещения морфов сжаты в двухбайтные числа
с одним множителем на пару «часть - морф», как в формате TRIP, растяжение - разреженно, только
ненулевые вершины. Скрипт страницы повторяет объекты ядра зеркально: у каждой кнопки есть
метод `MorphBench` с тем же именем, а внизу панели видно текущее состояние в том виде, в каком
его отдаёт `view_state()`, и командную строку `mb.py render`, которая даст тот же кадр без окна.

Палитры перенесены из растеризатора один в один, камера повторяет `ViewState.basis()`
и `framing()`, свет - `light_vector()` и силы из того же состояния, нормали вершин считаются
по `vertex_normals` из model.py - поэтому кадр страницы совпадает с PNG.

Капсулы столкновений - если к мешу открыт скелет - вкладываются готовыми треугольниками,
как их отдаёт `collider_mesh()` и `bumper_mesh()`; страница кладёт их поверх тела так же,
как растеризатор: полупрозрачно, цветом и прозрачностью из настроек, со своей глубиной
и не заслоняя тело. Включение слоя - `show_colliders`, тот же метод, что у фасада.

Та же страница умеет приходить и с локального сервера (`mb.py serve`): тогда в блок JSON
вкладываются ещё список мешей под корнем обзора и окружение, и на панели появляется выбор
модели. Геометрия в обоих случаях упаковывается одинаково, а страница с сервера обращается
только к своему серверу - переходом на другой запрос, без единого запроса наружу.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np


class WebPage:
    """Страница поверх фасада: числа ядра, упакованные в один файл.

    Без сервера страница самодостаточна и открывается с диска. С сервера (`server=True`)
    она получает ещё список мешей `catalog` (как его отдаёт `bench.catalog`), окружение
    `environment`, корень обзора `root`, признак «и без морфов» и текст ошибки последнего
    запроса: этого хватает панели, чтобы предложить выбор модели ссылкой на тот же сервер.
    Меш при этом может быть и не открыт - тогда страница показывает пустой холст и список.
    """

    def __init__(self, bench, server: bool = False, catalog=None, environment=None,
                 root=None, with_morphs: bool = True, error: str | None = None):
        self.bench = bench
        self.cfg = bench.cfg
        self.server = bool(server)
        self.catalog = list(catalog or [])
        self.environment = dict(environment or {})
        self.root = None if root is None else str(root)
        self.with_morphs = bool(with_morphs)
        self.error = None if error is None else str(error)

    # ---- упаковка массивов ------------------------------------------------------------
    @staticmethod
    def _b64(arr, dtype) -> str:
        """Байты массива в base64; порядок байтов - little-endian, как читает JS."""
        return base64.b64encode(np.ascontiguousarray(arr, dtype=dtype).tobytes()).decode("ascii")

    @staticmethod
    def _index_type(vertex_count: int) -> str:
        """Номера вершин: два байта, пока вершин меньше 65536, иначе четыре."""
        return "u16" if vertex_count < 65536 else "u32"

    @classmethod
    def _indices(cls, idx, vertex_count: int) -> str:
        return cls._b64(idx, "<u2" if cls._index_type(vertex_count) == "u16" else "<u4")

    # ---- части меша -------------------------------------------------------------------
    def _shape(self, name: str) -> dict:
        """Одна часть: вершины, треугольники, признак главной кости и имена костей."""
        shape = self.bench.model.shape(name)
        count = shape.vertex_count
        return {
            "name": name,
            "vertexCount": count,
            "vertices": self._b64(shape.verts, "<f4"),
            "indexType": self._index_type(count),
            "triangles": self._indices(shape.tris, count),
            "boneKey": self._b64(self.bench.bone_key(name), "<i2"),
            "boneNames": self.bench.shape_bone_names(name),
        }

    # ---- капсулы столкновений ---------------------------------------------------------
    @classmethod
    def _chunk(cls, verts, tris) -> dict | None:
        """Кусок геометрии без костей и морфов - в том же виде, что часть меша: вершины
        `<f4`, тип номера и треугольники. Пустой кусок - None: рисовать нечего."""
        tris = np.asarray(tris)
        if tris.shape[0] == 0:
            return None
        verts = np.asarray(verts, dtype=np.float32).reshape(-1, 3)
        count = int(verts.shape[0])
        return {"vertexCount": count,
                "vertices": cls._b64(verts, "<f4"),
                "indexType": cls._index_type(count),
                "triangles": cls._indices(tris, count)}

    def _colliders(self) -> dict | None:
        """Капсулы тел одним куском и бампер отдельно - как их отдаёт фасад, в мировых
        координатах. Без скелета - None: раздел на панели не строится."""
        bench = self.bench
        if not bench.has_skeleton():
            return None
        bodies = self._chunk(*bench.collider_mesh())
        if bodies is None:
            bodies = {"vertexCount": 0, "vertices": "", "indexType": "u16", "triangles": ""}
        bodies["bumper"] = self._chunk(*bench.bumper_mesh())
        return bodies

    # ---- морфы ------------------------------------------------------------------------
    def _deltas(self, shape_name: str, morph: str, vertex_count: int) -> dict | None:
        """Смещения морфа на части, сжатые в int16 с одним множителем: max|сдвиг|/32767."""
        raw = self.bench.morph_deltas(shape_name, morph)
        if raw is None:
            return None
        keep = raw["indices"] < vertex_count
        idx = raw["indices"][keep]
        off = np.asarray(raw["offsets"][keep], dtype=np.float32).reshape(-1, 3)
        if idx.size == 0:
            return None
        top = float(np.abs(off).max())
        if top <= 0.0:
            return None
        scale = top / 32767.0
        q = np.clip(np.rint(off / scale), -32767, 32767).astype(np.int16)
        return {"count": int(idx.size), "scale": scale,
                "indexType": self._index_type(vertex_count),
                "indices": self._indices(idx, vertex_count),
                "offsets": self._b64(q, "<i2")}

    def _strain(self, shape_name: str, morph: str, vertex_count: int) -> dict | None:
        """Растяжение у вершин - разреженно: ненулевые вершины, uint8 от максимума и сам максимум."""
        key = np.asarray(self.bench.strain_key(shape_name, morph), dtype=np.float32)
        top = float(key.max()) if key.size else 0.0
        if top <= 1e-6:
            return None
        idx = np.nonzero(key > 0.0)[0]
        values = np.clip(np.rint(255.0 * key[idx] / top), 0, 255).astype(np.uint8)
        return {"count": int(idx.size), "max": top,
                "indexType": self._index_type(vertex_count),
                "indices": self._indices(idx, vertex_count),
                "values": self._b64(values, "u1")}

    # ---- настройки, которые нужны показу ----------------------------------------------
    def _settings(self) -> dict:
        """Единственный источник чисел для страницы: ни одно из них в скрипте не зашито."""
        cfg = self.cfg
        return {
            "background": [float(x) for x in cfg["background"]],
            "lightFollowCamera": bool(cfg["lightFollowCamera"]),
            "lightCameraDirection": [float(x) for x in cfg["lightCameraDirection"]],
            "lightDirection": [float(x) for x in cfg["lightDirection"]],
            "ambient": float(cfg["ambient"]),
            "diffuse": float(cfg["diffuse"]),
            "fill": float(cfg["fill"]),
            "shading": str(cfg["shading"]),
            "imageWidth": int(cfg["imageWidth"]),
            "imageHeight": int(cfg["imageHeight"]),
            "frameFill": float(cfg["frameFill"]),
            "focusPadding": float(cfg["focusPadding"]),
            "baseShape": str(cfg["baseShape"]),
            "sliderRange": [float(x) for x in cfg["sliderRange"]],
            "sliderStep": float(cfg["sliderStep"]),
            "orbitSensitivity": float(cfg["orbitSensitivity"]),
            "wheelZoomRate": float(cfg["wheelZoomRate"]),
            # Слой капсул: цвет 0..255 и прозрачность 0..1 - те же ключи, что у растеризатора.
            "colliderColour": [float(x) for x in cfg["colliderColour"]],
            "colliderOpacity": float(cfg["colliderOpacity"]),
        }

    # ---- сервер: то, что страница знает о нём -----------------------------------------
    def _server(self) -> dict | None:
        """Список мешей, окружение и корень - только когда страницу отдаёт сервер.
        В файле с диска здесь None, и панель не предлагает того, чего сделать не может."""
        if not self.server:
            return None
        return {"root": self.root, "withMorphs": self.with_morphs,
                "catalog": self.catalog, "environment": self.environment,
                "error": self.error}

    # ---- тело: геометрия, морфы, цели -------------------------------------------------
    def _body(self) -> dict:
        """Всё про открытый меш. Здесь нет ни одного вычисления - только вопросы
        к фасаду и упаковка ответов."""
        bench = self.bench
        summary = bench.summary()
        names = bench.model.shape_names()
        shapes = [self._shape(n) for n in names]
        counts = {s["name"]: s["vertexCount"] for s in shapes}
        morphs = bench.morphs() if summary["tri"] else []

        deltas: dict[str, dict] = {}
        strain: dict[str, dict] = {}
        for morph in morphs:
            for n in names:
                d = self._deltas(n, morph, counts[n])
                if d is not None:
                    deltas.setdefault(morph, {})[n] = d
                s = self._strain(n, morph, counts[n])
                if s is not None:
                    strain.setdefault(morph, {})[n] = s

        # Цели наведения - без округления, чтобы кадр страницы сошёлся с PNG. Наведение,
        # заданное из командной строки подстрокой («Finger»), среди целей отсутствует -
        # ядро уже сосчитало его сферу, и она добавляется к целям под своим именем.
        targets = bench.focus_targets(precise=True)
        view = bench.view
        if view.has_focus and view.focus_name and ":" in view.focus_name:
            kind, _, name = view.focus_name.partition(":")
            group = targets.get(kind + "s")
            if group is not None and not any(t["name"] == name for t in group):
                group.append({"name": name, "centre": [float(x) for x in view.focus_centre],
                              "radius": float(view.focus_radius)})

        return {
            "summary": summary,
            "names": {"nif": Path(summary["nif"]).name,
                      "tri": Path(summary["tri"]).name if summary["tri"] else None,
                      "skeleton": Path(summary["skeleton"]).name if summary["skeleton"] else None},
            "shapes": shapes,
            "morphs": morphs,
            "deltas": deltas,
            "strain": strain,
            "targets": targets,
            "colliders": self._colliders(),
        }

    @staticmethod
    def _no_body() -> dict:
        """Меш не открыт: пустой холст, но та же форма данных, чтобы скрипт не ветвился."""
        return {"summary": None, "names": {"nif": None, "tri": None, "skeleton": None},
                "shapes": [], "morphs": [], "deltas": {}, "strain": {},
                "targets": {"bones": [], "morphs": [], "shapes": []},
                "colliders": None}

    # ---- всё вместе -------------------------------------------------------------------
    def payload(self) -> dict:
        """Всё, что страница знает о меше, настройках и - если есть - сервере, одним словарём."""
        bench = self.bench
        data = self._body() if bench.is_open() else self._no_body()
        data.update({
            "settings": self._settings(),
            "presets": bench.presets(),
            "view": bench.view_state(precise=True),
            "sliders": bench.sliders(),
            "server": self._server(),
        })
        return data

    def html(self) -> str:
        """Готовая страница строкой. Данные лежат в блоке <script type="application/json">;
        последовательность `</` внутри строк экранируется, чтобы имя части не закрыло блок."""
        data = json.dumps(self.payload(), ensure_ascii=False, separators=(",", ":"))
        data = data.replace("</", "<\\/")
        name = Path(self.bench.summary()["nif"]).name if self.bench.is_open() else "меш не открыт"
        title = "morphbench — %s" % name
        return _PAGE.replace("__MB_TITLE__", _escape(title)).replace("__MB_DATA__", data)

    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.html(), encoding="utf-8")
        return path


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# Сама страница. Ниже - разметка, стили и скрипт; данные подставляются на место __MB_DATA__.
# Скрипт написан теми же объектами, что ядро: ViewMirror повторяет ViewState, BenchMirror -
# MorphBench, vertexNormals - одноимённую функцию model.py, и у каждого действия на панели
# есть метод с тем же именем.
_PAGE = r"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>__MB_TITLE__</title>
<style>
  :root { --bg: #1a1c20; --panel: #23262b; --panel2: #2b2f36; --text: #e4e6ea; --muted: #9aa0a8;
          --line: #3a3f47; --accent: #d9a441; }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--text);
               font: 13px/1.4 system-ui, "Segoe UI", sans-serif; }
  body { display: grid; grid-template-rows: auto 1fr; grid-template-columns: 1fr 380px; height: 100vh; }
  header { grid-column: 1 / -1; padding: 8px 14px; background: var(--panel); border-bottom: 1px solid var(--line);
           display: flex; gap: 16px; align-items: baseline; flex-wrap: wrap; }
  header h1 { margin: 0; font-size: 15px; font-weight: 600; }
  header .sub { color: var(--muted); }
  main { position: relative; overflow: hidden; }
  canvas { display: block; width: 100%; height: 100%; touch-action: none; }
  #hint { position: absolute; left: 10px; bottom: 8px; color: var(--muted); font-size: 12px;
          background: rgba(26,28,32,.7); padding: 3px 8px; border-radius: 4px; pointer-events: none; }
  #nogl { position: absolute; inset: 0; display: none; align-items: center; justify-content: center;
          padding: 30px; text-align: center; color: var(--muted); }
  aside { background: var(--panel); border-left: 1px solid var(--line); overflow-y: auto; padding: 10px 12px 20px; }
  section { border-bottom: 1px solid var(--line); padding: 8px 0 10px; }
  section h2 { margin: 0 0 6px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
  .row { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  button { background: var(--panel2); color: var(--text); border: 1px solid var(--line); border-radius: 4px;
           padding: 3px 9px; cursor: pointer; font: inherit; }
  button:hover { border-color: var(--accent); }
  button.on { background: var(--accent); color: #1a1c20; border-color: var(--accent); }
  select, input[type=number], input[type=text] { background: var(--panel2); color: var(--text); border: 1px solid var(--line);
           border-radius: 4px; padding: 2px 4px; font: inherit; }
  select { max-width: 100%; }
  input.short { width: 68px; }
  input.wide { flex: 1; min-width: 120px; }
  label { cursor: pointer; }
  .current { word-break: break-all; }
  .parts .part { display: flex; align-items: center; gap: 6px; padding: 1px 0; }
  .parts label { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
  .parts .only { color: var(--muted); font-size: 11px; cursor: pointer; }
  .parts .only:hover { color: var(--accent); }
  .slider { display: grid; grid-template-columns: 1fr 120px 62px; gap: 6px; align-items: center; padding: 2px 0; }
  .slider .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .slider input[type=range] { width: 100%; margin: 0; }
  .slider input[type=number] { width: 62px; }
  .slider.active .name { color: var(--accent); }
  .legend { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 10px; margin-top: 6px; }
  .legend div { display: flex; align-items: center; gap: 6px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .swatch { width: 14px; height: 14px; border-radius: 3px; flex: none; border: 1px solid rgba(0,0,0,.4); }
  pre { background: var(--bg); border: 1px solid var(--line); border-radius: 4px; padding: 6px 8px; margin: 4px 0;
        white-space: pre-wrap; word-break: break-all; font: 11.5px/1.35 Consolas, "Cascadia Mono", monospace; }
  .muted { color: var(--muted); font-size: 12px; }
  .err { color: #e07070; }
</style>
</head>
<body>
<header>
  <h1 id="title"></h1>
  <span class="sub" id="subtitle"></span>
</header>
<main>
  <canvas id="canvas"></canvas>
  <div id="hint">левая кнопка — орбита · колесо — масштаб к курсору · правая кнопка — панорама · двойной щелчок — сброс</div>
  <div id="nogl">В этом браузере нет WebGL2 — нарисовать тело нечем.</div>
</main>
<aside id="panel"></aside>
<script id="mb-data" type="application/json">__MB_DATA__</script>
<script>
(function () {
"use strict";

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

// ---- данные ядра, как они вложены в страницу ----------------------------------------------
class Shape {
  constructor(raw) {
    this.name = raw.name;
    this.base = Codec.f32(raw.vertices);          // исходные вершины, не трогаются
    this.pos = new Float32Array(this.base);        // вершины с применёнными ползунками
    this.nrm = new Float32Array(this.base.length); // нормали вершин по деформированным позициям
    this.count = raw.vertexCount;
    this.tris = Codec.index(raw.triangles, raw.indexType);
    this.triCount = this.tris.length / 3;
    this.boneKey = Codec.i16(raw.boneKey);
    this.boneNames = raw.boneNames;
  }
}

class Deltas {
  // Смещения одного морфа на одной части: номера вершин и int16-векторы с общим множителем.
  constructor(raw) {
    this.indices = Codec.index(raw.indices, raw.indexType);
    this.q = Codec.i16(raw.offsets);
    this.scale = raw.scale;
    this.count = raw.count;
  }
  applyTo(pos, amount) {
    const k = amount * this.scale, idx = this.indices, q = this.q;
    for (let i = 0, n = idx.length; i < n; i++) {
      const v = idx[i] * 3, j = i * 3;
      pos[v] += k * q[j]; pos[v + 1] += k * q[j + 1]; pos[v + 2] += k * q[j + 2];
    }
  }
  lengthsInto(out) {
    const idx = this.indices, q = this.q, k = this.scale;
    for (let i = 0, n = idx.length; i < n; i++) {
      const j = i * 3;
      out[idx[i]] = k * Math.sqrt(q[j] * q[j] + q[j + 1] * q[j + 1] + q[j + 2] * q[j + 2]);
    }
  }
}

class Strain {
  constructor(raw) {
    this.indices = Codec.index(raw.indices, raw.indexType);
    this.values = Codec.u8(raw.values);
    this.max = raw.max;
  }
  valuesInto(out) {
    const idx = this.indices, v = this.values, k = this.max / 255.0;
    for (let i = 0, n = idx.length; i < n; i++) out[idx[i]] = v[i] * k;
  }
}

// Кусок капсул - тела одним куском либо бампер, - как его отдаёт collider_mesh() и
// bumper_mesh() фасада: уже в мировых координатах, без костей и морфов, поэтому ползунки
// его не трогают и нормали считаются один раз. Поля те же, что у Shape, - рисующему всё равно.
class ColliderMesh {
  constructor(name, raw) {
    this.name = name;
    this.pos = Codec.f32(raw.vertices);
    this.count = raw.vertexCount;
    this.tris = Codec.index(raw.triangles, raw.indexType);
    this.triCount = this.tris.length / 3;
    this.nrm = vertexNormals(this.pos, this.tris, new Float32Array(this.pos.length));
  }
}

// ---- зеркало morphbench/view.py: ViewState -----------------------------------------------
class ViewMirror {
  constructor(settings, presets, init) {
    this.settings = settings;
    this.presets = presets;
    this.yaw = init.yaw; this.pitch = init.pitch; this.zoom = init.zoom;
    this.pan = init.pan ? init.pan.slice() : [0, 0];
    this.visible = init.visible === null ? null : new Set(init.visible);
    this.colouring = init.colouring;
    // Слой капсул поверх тела и бампер отдельно - числами, как в ядре; старое состояние
    // без этих ключей означает «выключено».
    this.colliders = !!init.colliders;
    this.bumper = !!init.bumper;
    this.highlightMorph = init.highlightMorph;
    this.width = init.width; this.height = init.height;
    this.focus = init.focus ? { name: init.focus.name, centre: init.focus.centre.slice(),
                                radius: init.focus.radius } : null;
    // Свет: за камерой (направление в осях камеры - вправо, вверх, к зрителю) либо отдельно
    // (мировое направление). Ядро отдаёт оба направления; настройки - лишь запас
    // на случай старого состояния без них.
    const light = init.light;
    this.lightFollow = !!light.follow;
    this.lightCameraDir = (light.cameraDirection
      || (light.follow ? light.direction : settings.lightCameraDirection)).slice();
    this.lightWorldDir = (light.worldDirection
      || (light.follow ? settings.lightDirection : light.direction)).slice();
    this.ambient = light.ambient; this.diffuse = light.diffuse; this.fill = light.fill;
    // Полуразмах последнего кадра: по нему масштаб к точке переводит доли кадра в единицы.
    this.frameHalf = null;
  }
  // камера
  orbit(dYaw, dPitch) { this.yaw = mod360(this.yaw + dYaw); this.pitch = clamp(this.pitch + dPitch, -89, 89); return this; }
  look(yaw, pitch) { this.yaw = mod360(yaw); this.pitch = clamp(pitch, -89, 89); return this; }
  preset(name) {
    if (!(name in this.presets)) throw new Error("нет ракурса " + name);
    return this.look(this.presets[name][0], this.presets[name][1]);
  }
  preset_names() { return Object.keys(this.presets).sort(); }
  preset_name() {
    const y = rnd(this.yaw, 1), p = rnd(this.pitch, 1);
    for (const name in this.presets) {
      const v = this.presets[name];
      if (rnd(mod360(v[0]), 1) === y && rnd(v[1], 1) === p) return name;
    }
    return null;
  }
  set_zoom(factor) { this.zoom = Math.max(0.05, Number(factor)); return this; }
  // Масштаб к точке: точка сцены под курсором остаётся на месте. fx, fy - положение курсора
  // от центра кадра в долях половины меньшей стороны холста, вправо и вверх. Без полуразмаха
  // последнего кадра точка неизвестна, и масштаб идёт от центра - как в ядре.
  zoom_at(factor, fx, fy) {
    const old = this.zoom, next = Math.max(0.05, Number(factor));
    if (this.frameHalf !== null && old > 0.0 && next !== old) {
      const fill = this.settings.frameFill;
      const u = Number(fx) * this.frameHalf / (fill * old);
      const v = Number(fy) * this.frameHalf / (fill * old);
      const k = 1.0 - old / next;
      this.pan = [this.pan[0] - u * k, this.pan[1] - v * k];
    }
    this.zoom = next;
    return this;
  }
  resize(width, height) { this.width = Math.trunc(width); this.height = Math.trunc(height); return this; }
  // панорама: сдвиг кадра вдоль осей экрана - вправо и вверх - в единицах модели
  set_pan(dx, dy) { this.pan = [Number(dx), Number(dy)]; return this; }
  pan_by(dx, dy) { return this.set_pan(this.pan[0] + dx, this.pan[1] + dy); }
  // наведение
  focus_on(centre, radius, name) { this.focus = { name: name, centre: centre.slice(), radius: Math.max(radius, 1e-3) }; return this; }
  focus_all() { this.focus = null; return this; }
  // Кадр: сфера наведения с запасом либо переданный охват; панорама сдвигает центр - то же
  // правило, что у ViewState.framing() в ядре. Полуразмах запоминается для zoom_at.
  framing(centre, halfSpan) {
    let c = centre, half = halfSpan;
    if (this.focus !== null) { c = this.focus.centre; half = this.focus.radius * this.settings.focusPadding; }
    if (this.pan[0] !== 0 || this.pan[1] !== 0) {
      const b = this.basis();
      c = [0, 1, 2].map((i) => c[i] - b.right[i] * this.pan[0] - b.up[i] * this.pan[1]);
    }
    this.frameHalf = half;
    return [c, half];
  }
  // свет
  light_follow_camera(on) { this.lightFollow = !!on; return this; }
  light_direction(x, y, z) {
    const v = [Number(x), Number(y), Number(z)];
    if (norm(v) < 1e-6) throw new Error("направление света не может быть нулевым");
    if (this.lightFollow) this.lightCameraDir = v; else this.lightWorldDir = v;
    return this;
  }
  light_power(ambient, diffuse, fill) {
    if (ambient !== undefined && ambient !== null) this.ambient = Math.max(0.0, Number(ambient));
    if (diffuse !== undefined && diffuse !== null) this.diffuse = Math.max(0.0, Number(diffuse));
    if (fill !== undefined && fill !== null) this.fill = Math.max(0.0, Number(fill));
    return this;
  }
  // Свет как в настройках: режим, оба направления и силы - зеркало ViewState.light_reset.
  light_reset() {
    const st = this.settings;
    this.lightFollow = !!st.lightFollowCamera;
    this.lightCameraDir = st.lightCameraDirection.slice();
    this.lightWorldDir = st.lightDirection.slice();
    this.ambient = Number(st.ambient); this.diffuse = Number(st.diffuse); this.fill = Number(st.fill);
    return this;
  }
  // Единичный вектор на источник в мировых координатах - то, что нужно рисующему. За камерой
  // он собирается из осей камеры: right·x + up·y - forward·z, поэтому едет вместе с ракурсом.
  light_vector() {
    let v;
    if (this.lightFollow) {
      const b = this.basis(), d = this.lightCameraDir;
      v = [0, 1, 2].map((i) => b.right[i] * d[0] + b.up[i] * d[1] - b.forward[i] * d[2]);
    } else {
      v = this.lightWorldDir.slice();
    }
    const n = norm(v);
    return n > 1e-6 ? v.map((x) => x / n) : [0, 0, 1];
  }
  light_state() {
    const d = this.lightFollow ? this.lightCameraDir : this.lightWorldDir;
    return { follow: this.lightFollow, direction: d.map((x) => rnd(x, 3)),
             cameraDirection: this.lightCameraDir.map((x) => rnd(x, 3)),
             worldDirection: this.lightWorldDir.map((x) => rnd(x, 3)),
             ambient: rnd(this.ambient, 3), diffuse: rnd(this.diffuse, 3), fill: rnd(this.fill, 3) };
  }
  // слой капсул: бампер отдельно и по умолчанию выключен; null или undefined - не менять,
  // как None у ViewState.show_colliders
  show_colliders(on, bumper) {
    this.colliders = on === undefined ? true : !!on;
    if (bumper !== undefined && bumper !== null) this.bumper = !!bumper;
    return { colliders: this.colliders, bumper: this.bumper };
  }
  // слои
  show_all() { this.visible = null; return this; }
  only(names) { this.visible = new Set(names); return this; }
  show(name) { if (this.visible !== null) this.visible.add(name); return this; }
  hide(name) { if (this.visible === null) this.visible = new Set(); this.visible.delete(name); return this; }
  is_visible(name) { return this.visible === null || this.visible.has(name); }
  // раскраска
  colour_by(mode, morph) {
    if (!["shade", "bone", "morph", "strain"].includes(mode)) throw new Error("раскраска бывает shade, bone, morph, strain");
    this.colouring = mode; this.highlightMorph = morph === undefined ? null : morph; return this;
  }
  // три оси камеры: вправо, вверх, от зрителя к модели. Персонаж смотрит вдоль +Y,
  // поэтому нулевой поворот ставит камеру перед ним, взгляд идёт в сторону -Y.
  basis() {
    const ry = this.yaw * Math.PI / 180, rp = this.pitch * Math.PI / 180;
    const forward = [-Math.sin(ry) * Math.cos(rp), -Math.cos(ry) * Math.cos(rp), -Math.sin(rp)];
    let right = cross(forward, [0, 0, 1]);
    const n = norm(right);
    right = n < 1e-5 ? [1, 0, 0] : right.map((x) => x / n);
    return { right: right, up: cross(right, forward), forward: forward };
  }
  as_dict() {
    return {
      yaw: rnd(this.yaw, 1), pitch: rnd(this.pitch, 1), preset: this.preset_name(),
      zoom: rnd(this.zoom, 3),
      pan: [rnd(this.pan[0], 2), rnd(this.pan[1], 2)],
      colouring: this.colouring, highlightMorph: this.highlightMorph,
      visible: this.visible === null ? null : Array.from(this.visible).sort(),
      colliders: this.colliders, bumper: this.bumper,
      width: this.width, height: this.height,
      light: this.light_state(),
      focus: this.focus === null ? null : { name: this.focus.name,
        centre: this.focus.centre.map((x) => rnd(x, 2)), radius: rnd(this.focus.radius, 2) },
    };
  }
}

// ---- зеркало morphbench/api.py: MorphBench ------------------------------------------------
// Имена методов нарочно те же, что у фасада, вплоть до подчёркиваний: каждая кнопка страницы
// зовёт метод отсюда, а он один в один соответствует вызову ядра.
class BenchMirror {
  constructor(data) {
    this.summary = data.summary;               // null - меш не открыт (страница с сервера)
    this.names = data.names;
    this.settings = data.settings;
    this.server = data.server || null;         // список мешей и окружение - только с сервера
    this.shapes = new Map(data.shapes.map((raw) => [raw.name, new Shape(raw)]));
    this.morphList = data.morphs;
    this.deltas = {};
    for (const morph in data.deltas) {
      this.deltas[morph] = {};
      for (const shape in data.deltas[morph]) this.deltas[morph][shape] = new Deltas(data.deltas[morph][shape]);
    }
    this.strainData = {};
    for (const morph in data.strain) {
      this.strainData[morph] = {};
      for (const shape in data.strain[morph]) this.strainData[morph][shape] = new Strain(data.strain[morph][shape]);
    }
    this.targets = data.targets;
    // Капсулы - только при открытом скелете: тела одним куском и бампер отдельно.
    // Распаковываются и получают нормали один раз - ползунки капсул не касаются.
    const raw = data.colliders || null;
    this._colliderMesh = raw ? new ColliderMesh("colliders:bodies", raw) : null;
    this._bumperMesh = raw && raw.bumper ? new ColliderMesh("colliders:bumper", raw.bumper) : null;
    this.view = new ViewMirror(data.settings, data.presets, data.view);
    this._sliders = new Map(Object.entries(data.sliders));
  }

  is_open() { return this.summary !== null; }
  // скелет и капсулы: геометрия уже сосчитана ядром и лежит в странице
  has_skeleton() { return this._colliderMesh !== null; }
  collider_mesh() { return this._colliderMesh; }
  bumper_mesh() { return this._bumperMesh; }
  show_colliders(on, bumper) { return this.view.show_colliders(on, bumper); }
  shape_names() { return Array.from(this.shapes.keys()).sort(); }
  shape(name) { const s = this.shapes.get(name); if (!s) throw new Error("в меше нет части " + name); return s; }
  morphs() { return this.morphList.slice(); }
  presets() { return this.view.presets; }
  visible_shapes() { return this.shape_names().filter((n) => this.view.is_visible(n)); }

  // ползунки
  set_slider(name, value) {
    if (!this.morphList.includes(name)) throw new Error("нет ползунка " + name);
    value = Number(value);
    if (value === 0.0) this._sliders.delete(name); else this._sliders.set(name, value);
    return this.sliders();
  }
  set_sliders(values) { for (const k in values) this.set_slider(k, values[k]); return this.sliders(); }
  sliders() { return Object.fromEntries(this._sliders); }
  reset_sliders() { this._sliders.clear(); return {}; }

  // геометрия: base + сумма amount × scale × int16 - тот же счёт, что делает Morph.apply в ядре
  deformed(name) {
    const s = this.shape(name);
    s.pos.set(s.base);
    for (const [morph, amount] of this._sliders) {
      const d = this.deltas[morph] && this.deltas[morph][name];
      if (d) d.applyTo(s.pos, amount);
    }
    return s.pos;
  }
  // нормали вершин части с применёнными ползунками - для мягкого затенения
  vertex_normals(name) {
    const s = this.shape(name);
    return vertexNormals(this.deformed(name), s.tris, s.nrm);
  }
  // Центр и полуразмах кадра: охват видимых частей с применёнными ползунками в осях камеры,
  // затем наведение и панорама - зеркало MorphBench.framing(). Полуразмах остаётся в ViewMirror,
  // и масштаб к точке знает, какой кадр был на экране.
  framing() {
    const shapes = this.visible_shapes().map((n) => this.shape(n)).filter((s) => s.triCount > 0);
    if (!shapes.length) throw new Error("нечего показывать: все части меша скрыты");
    const lo = [Infinity, Infinity, Infinity], hi = [-Infinity, -Infinity, -Infinity];
    for (const s of shapes) {
      const p = this.deformed(s.name);
      for (let i = 0, n = p.length; i < n; i += 3) {
        if (p[i] < lo[0]) lo[0] = p[i]; if (p[i] > hi[0]) hi[0] = p[i];
        if (p[i + 1] < lo[1]) lo[1] = p[i + 1]; if (p[i + 1] > hi[1]) hi[1] = p[i + 1];
        if (p[i + 2] < lo[2]) lo[2] = p[i + 2]; if (p[i + 2] > hi[2]) hi[2] = p[i + 2];
      }
    }
    const whole = [0.5 * (lo[0] + hi[0]), 0.5 * (lo[1] + hi[1]), 0.5 * (lo[2] + hi[2])];
    const b = this.view.basis(), r = b.right, u = b.up;
    let half = 0.0;
    for (const s of shapes) {
      const p = s.pos;
      for (let i = 0, n = p.length; i < n; i += 3) {
        const dx = p[i] - whole[0], dy = p[i + 1] - whole[1], dz = p[i + 2] - whole[2];
        const x = Math.abs(dx * r[0] + dy * r[1] + dz * r[2]);
        const y = Math.abs(dx * u[0] + dy * u[1] + dz * u[2]);
        if (x > half) half = x; if (y > half) half = y;
      }
    }
    return this.view.framing(whole, half);
  }

  // признаки раскраски: числа, а не цвета
  bone_key(name) { return this.shape(name).boneKey; }
  morph_key(name, morph) {
    const s = this.shape(name), out = new Float32Array(s.count);
    const d = this.deltas[morph] && this.deltas[morph][name];
    if (d) d.lengthsInto(out);
    return out;
  }
  strain_key(name, morph) {
    const s = this.shape(name), out = new Float32Array(s.count);
    const st = this.strainData[morph] && this.strainData[morph][name];
    if (st) st.valuesInto(out);
    return out;
  }
  vertex_colour_key(name) {
    const mode = this.view.colouring;
    if (mode === "shade") return null;
    if (mode === "bone") return this.bone_key(name);
    if (!this.morphList.length || !this.view.highlightMorph) return new Float32Array(this.shape(name).count);
    if (mode === "morph") return this.morph_key(name, this.view.highlightMorph);
    return this.strain_key(name, this.view.highlightMorph);
  }

  // состояние показа
  orbit(dYaw, dPitch) { return this.view.orbit(dYaw, dPitch).as_dict(); }
  look(yaw, pitch) { return this.view.look(yaw, pitch).as_dict(); }
  preset(name) { return this.view.preset(name).as_dict(); }
  preset_name() { return this.view.preset_name(); }
  zoom(factor) { return this.view.set_zoom(factor).as_dict(); }
  resize(width, height) { return this.view.resize(width, height).as_dict(); }
  // Масштаб к точке под курсором: кадр пересчитывается здесь же, чтобы точка бралась с того
  // кадра, который на экране, - как в фасаде.
  zoom_at(factor, fx, fy) { this.framing(); return this.view.zoom_at(factor, fx, fy).as_dict(); }
  pan(dx, dy) { return this.view.set_pan(dx, dy).as_dict(); }
  pan_by(dx, dy) { return this.view.pan_by(dx, dy).as_dict(); }
  colour_by(mode, morph) { return this.view.colour_by(mode, morph).as_dict(); }
  only(names) { return this.view.only(names).as_dict(); }
  show_all() { return this.view.show_all().as_dict(); }
  // «Видно всё» ядро хранит как null, а ViewState имён частей не знает - поэтому, как и
  // в фасаде, перечень видимых разворачивается здесь, и hide прячет одну часть, а не все.
  hide(name) { if (this.view.visible === null) this.view.only(this.shape_names()); return this.view.hide(name).as_dict(); }
  show(name) { return this.view.show(name).as_dict(); }
  view_state() { return this.view.as_dict(); }

  // свет: тоже состояние показа
  light_follow_camera(on) { return this.view.light_follow_camera(on).as_dict(); }
  light_direction(x, y, z) { return this.view.light_direction(x, y, z).as_dict(); }
  light_power(ambient, diffuse, fill) { return this.view.light_power(ambient, diffuse, fill).as_dict(); }
  light_reset() { return this.view.light_reset().as_dict(); }
  light_vector() { return this.view.light_vector(); }

  // наведение: центры и радиусы уже посчитаны ядром и лежат в focus_targets
  _target(kind, name) {
    const hit = this.targets[kind].find((t) => t.name === name);
    if (!hit) throw new Error("нет цели наведения " + kind + ":" + name);
    return hit;
  }
  focus_bone(name) { const t = this._target("bones", name); return this.view.focus_on(t.centre, t.radius, "bone:" + name).as_dict(); }
  focus_morph(name) { const t = this._target("morphs", name); return this.view.focus_on(t.centre, t.radius, "morph:" + name).as_dict(); }
  focus_shape(name) { const t = this._target("shapes", name); return this.view.focus_on(t.centre, t.radius, "shape:" + name).as_dict(); }
  focus_all() { return this.view.focus_all().as_dict(); }
  focus_targets() { return this.targets; }
}

// ---- отрисовка: WebGL2, ортографическая камера, затенение как у растеризатора --------------
// Мягкое затенение: свет считается в вершине по её нормали и растягивается по треугольнику
// вместе с цветом - ровно так складывает vcols × lit растеризатор. Формула та же:
// ambient + diffuse·max(n·L, 0) + fill·max(-n·L, 0).
const VERTEX_SHADER = "#version 300 es\n" +
  "precision highp float;\n" +
  "in vec3 aPos;\n" +
  "in vec3 aNrm;\n" +
  "in vec3 aCol;\n" +
  "uniform vec3 uRight, uUp, uForward, uCentre;\n" +
  "uniform float uScale, uZc, uZr;\n" +
  "uniform vec2 uHalf;\n" +
  "uniform vec3 uLight;\n" +
  "uniform float uAmbient, uDiffuse, uFill;\n" +
  "out vec3 vWorld;\n" +
  "out vec3 vCol;\n" +
  "out vec3 vLit;\n" +
  "void main() {\n" +
  "  vec3 d = aPos - uCentre;\n" +                         // (v - центр) @ basis.T, как в растеризаторе
  "  float x = dot(d, uRight) * uScale;\n" +
  "  float y = dot(d, uUp) * uScale;\n" +
  "  float z = dot(d, uForward);\n" +                       // глубина: меньше - ближе к зрителю
  "  gl_Position = vec4(x / uHalf.x, y / uHalf.y, (z - uZc) / uZr, 1.0);\n" +
  "  vWorld = aPos;\n" +
  "  vCol = aCol;\n" +
  "  float lam = dot(normalize(aNrm), uLight);\n" +
  "  vLit = aCol * (uAmbient + uDiffuse * clamp(lam, 0.0, 1.0) + uFill * clamp(-lam, 0.0, 1.0));\n" +
  "}\n";

// Плоское затенение (shading = flat в настройках): нормаль треугольника из производных мировой
// позиции по экрану - нормаль плоскости, направленная к зрителю, что для лицевых граней
// совпадает с геометрической нормалью растеризатора. Свет в мировых координатах, как и нормаль.
const FRAGMENT_SHADER = "#version 300 es\n" +
  "precision highp float;\n" +
  "in vec3 vWorld;\n" +
  "in vec3 vCol;\n" +
  "in vec3 vLit;\n" +
  "uniform vec3 uLight;\n" +
  "uniform float uAmbient, uDiffuse, uFill;\n" +
  "uniform int uFlat;\n" +
  "uniform float uAlpha;\n" +                                    // 1.0 у тела; у капсул - colliderOpacity
  "out vec4 outColour;\n" +
  "void main() {\n" +
  "  vec3 lit = vLit;\n" +
  "  if (uFlat == 1) {\n" +
  "    vec3 n = normalize(cross(dFdx(vWorld), dFdy(vWorld)));\n" +
  "    if (!gl_FrontFacing) n = -n;\n" +                       // нормаль по обходу, как в растеризаторе
  "    float lam = dot(n, uLight);\n" +
  "    lit = vCol * (uAmbient + uDiffuse * clamp(lam, 0.0, 1.0) + uFill * clamp(-lam, 0.0, 1.0));\n" +
  "  }\n" +
  "  outColour = vec4(clamp(lit, 0.0, 1.0), uAlpha);\n" +
  "}\n";

class Renderer {
  constructor(canvas, settings) {
    this.canvas = canvas;
    this.settings = settings;
    const gl = canvas.getContext("webgl2", { antialias: true, preserveDrawingBuffer: true });
    if (!gl) throw new Error("нет WebGL2");
    this.gl = gl;
    this.program = this._program(VERTEX_SHADER, FRAGMENT_SHADER);
    this.attr = { pos: gl.getAttribLocation(this.program, "aPos"), nrm: gl.getAttribLocation(this.program, "aNrm"),
                  col: gl.getAttribLocation(this.program, "aCol") };
    this.uni = {};
    for (const name of ["uRight", "uUp", "uForward", "uCentre", "uScale", "uZc", "uZr", "uHalf",
                        "uLight", "uAmbient", "uDiffuse", "uFill", "uFlat", "uAlpha"])
      this.uni[name] = gl.getUniformLocation(this.program, name);
    this.meshes = new Map();
    this.bg = settings.background.map((x) => x / 255.0);
    this.flat = settings.shading === "flat";
    // Слой капсул: цвет и прозрачность из тех же ключей настроек, что у растеризатора.
    this.colliderTint = settings.colliderColour.map((x) => x / 255.0);
    this.colliderAlpha = settings.colliderOpacity;
  }
  _shader(type, src) {
    const gl = this.gl, sh = gl.createShader(type);
    gl.shaderSource(sh, src); gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) throw new Error("шейдер: " + gl.getShaderInfoLog(sh));
    return sh;
  }
  _program(vs, fs) {
    const gl = this.gl, p = gl.createProgram();
    gl.attachShader(p, this._shader(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, this._shader(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error("программа: " + gl.getProgramInfoLog(p));
    return p;
  }
  _attribute(buffer, data, location, usage) {
    const gl = this.gl;
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, data, usage);
    gl.enableVertexAttribArray(location);
    gl.vertexAttribPointer(location, 3, gl.FLOAT, false, 0, 0);
  }
  // буферы части: позиции, нормали и цвета меняются, треугольники - нет
  upload(shape) {
    const gl = this.gl;
    if (!shape.triCount) return;
    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const pos = gl.createBuffer(), nrm = gl.createBuffer(), col = gl.createBuffer();
    this._attribute(pos, shape.pos, this.attr.pos, gl.DYNAMIC_DRAW);
    this._attribute(nrm, shape.nrm, this.attr.nrm, gl.DYNAMIC_DRAW);
    this._attribute(col, shape.count * 12, this.attr.col, gl.DYNAMIC_DRAW);
    const idx = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, idx);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, shape.tris, gl.STATIC_DRAW);
    gl.bindVertexArray(null);
    this.meshes.set(shape.name, { vao, pos, nrm, col, count: shape.tris.length,
      type: shape.tris instanceof Uint32Array ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT });
  }
  _refill(buffer, data) {
    if (!buffer) return;
    this.gl.bindBuffer(this.gl.ARRAY_BUFFER, buffer);
    this.gl.bufferSubData(this.gl.ARRAY_BUFFER, 0, data);
  }
  setPositions(shape) { const m = this.meshes.get(shape.name); if (m) this._refill(m.pos, shape.pos); }
  setNormals(shape) { const m = this.meshes.get(shape.name); if (m) this._refill(m.nrm, shape.nrm); }
  setColours(shape, colours) { const m = this.meshes.get(shape.name); if (m) this._refill(m.col, colours); }
  // Кусок капсул - те же буферы, что у части меша, но цвет один на все вершины: тень
  // по нормали шейдер положит на него сам, той же формулой, что на кожу.
  uploadColliders(chunk) {
    if (!chunk || !chunk.triCount) return;
    this.upload(chunk);
    const t = this.colliderTint, colours = new Float32Array(chunk.count * 3);
    for (let i = 0; i < chunk.count; i++) { colours[i * 3] = t[0]; colours[i * 3 + 1] = t[1]; colours[i * 3 + 2] = t[2]; }
    this.setColours(chunk, colours);
  }
  // Куски капсул, которые сейчас надо рисовать: тела - когда слой включён, бампер - ещё
  // и по своему флагу. Без скелета и при выключенном слое - ничего.
  _colliderChunks(bench) {
    const view = bench.view, out = [];
    if (!view.colliders || !bench.has_skeleton()) return out;
    for (const chunk of [bench.collider_mesh(), view.bumper ? bench.bumper_mesh() : null])
      if (chunk && chunk.triCount && this.meshes.has(chunk.name)) out.push(chunk);
    return out;
  }
  resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(1, Math.round(this.canvas.clientWidth * dpr));
    const h = Math.max(1, Math.round(this.canvas.clientHeight * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; }
  }
  // Диапазон глубины - проекция видимых вершин на ось взгляда, чтобы буфер ничего не отрезал.
  // Капсулы входят в него, когда включены: бампер вчетверо больше тела и иначе был бы обрезан.
  _depthRange(bench, centre, forward) {
    let zmin = Infinity, zmax = -Infinity;
    const clouds = bench.visible_shapes().map((n) => bench.shape(n)).filter((s) => s.triCount > 0)
      .concat(this._colliderChunks(bench));
    for (const s of clouds) {
      const p = s.pos;
      for (let i = 0, n = p.length; i < n; i += 3) {
        const z = (p[i] - centre[0]) * forward[0] + (p[i + 1] - centre[1]) * forward[1] + (p[i + 2] - centre[2]) * forward[2];
        if (z < zmin) zmin = z; if (z > zmax) zmax = z;
      }
    }
    return [zmin, zmax];
  }
  draw(bench) {
    const gl = this.gl, view = bench.view;
    this.resize();
    const w = this.canvas.width, h = this.canvas.height;
    gl.viewport(0, 0, w, h);
    gl.clearColor(this.bg[0], this.bg[1], this.bg[2], 1.0);
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LESS); gl.disable(gl.CULL_FACE);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    // Кадр - вся модель, сфера наведения или панорама - решает зеркало ядра; нечего
    // показывать - пустой холст, как растеризатору нечего рисовать.
    let framed;
    try { framed = bench.framing(); } catch (_) { return null; }
    const c = framed[0], half = framed[1];
    const basis = view.basis();
    const span = half * 2.0;
    const scale = (Math.min(w, h) * this.settings.frameFill) / Math.max(span, 1e-3) * view.zoom;
    const [zmin, zmax] = this._depthRange(bench, c, basis.forward);
    gl.useProgram(this.program);
    gl.uniform3fv(this.uni.uRight, basis.right);
    gl.uniform3fv(this.uni.uUp, basis.up);
    gl.uniform3fv(this.uni.uForward, basis.forward);
    gl.uniform3fv(this.uni.uCentre, c);
    gl.uniform1f(this.uni.uScale, scale);
    gl.uniform1f(this.uni.uZc, 0.5 * (zmin + zmax));
    gl.uniform1f(this.uni.uZr, Math.max(0.5 * (zmax - zmin), 1e-3) * 1.01);
    gl.uniform2f(this.uni.uHalf, w * 0.5, h * 0.5);
    // Свет - из состояния показа на каждый кадр: за камерой он меняется вместе с ракурсом.
    gl.uniform3fv(this.uni.uLight, bench.light_vector());
    gl.uniform1f(this.uni.uAmbient, view.ambient);
    gl.uniform1f(this.uni.uDiffuse, view.diffuse);
    gl.uniform1f(this.uni.uFill, view.fill);
    gl.uniform1i(this.uni.uFlat, this.flat ? 1 : 0);
    gl.uniform1f(this.uni.uAlpha, 1.0);
    for (const name of bench.visible_shapes()) {
      const m = this.meshes.get(name);
      if (!m) continue;
      gl.bindVertexArray(m.vao);
      gl.drawElements(gl.TRIANGLES, m.count, m.type, 0);
    }
    this._overlayColliders(bench);
    gl.bindVertexArray(null);
    return { scale: scale };
  }
  // Капсулы поверх тела - полупрозрачно, со своей глубиной: зеркало _overlay_colliders
  // растеризатора. Смысл в том, что видно обе оболочки сразу: внутри тела капсула
  // просвечивает сквозь кожу, снаружи ложится на фон. Поэтому глубина тела капсулы
  // не режет - перед каждым куском буфер глубины очищается, и кусок сортируется только
  // сам с собой (передняя стенка капсулы закрывает заднюю, а не тело). Тело к этому
  // моменту уже нарисовано, и его глубина больше никому не нужна. Цвет вершин - один
  // на кусок, свет - той же формулой того же шейдера, прозрачность - uAlpha.
  _overlayColliders(bench) {
    const chunks = this._colliderChunks(bench);
    if (!chunks.length) return;
    const gl = this.gl;
    gl.enable(gl.BLEND);
    // Альфа холста остаётся единицей: иначе страница просвечивала бы сквозь капсулы.
    gl.blendFuncSeparate(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA, gl.ZERO, gl.ONE);
    gl.uniform1f(this.uni.uAlpha, this.colliderAlpha);
    for (const chunk of chunks) {
      const m = this.meshes.get(chunk.name);
      gl.clear(gl.DEPTH_BUFFER_BIT);
      gl.bindVertexArray(m.vao);
      gl.drawElements(gl.TRIANGLES, m.count, m.type, 0);
    }
    gl.uniform1f(this.uni.uAlpha, 1.0);
    gl.disable(gl.BLEND);
  }
}

// ---- боковая панель ------------------------------------------------------------------------
class Panel {
  constructor(app, root) {
    this.app = app;
    this.bench = app.bench;
    this.root = root;
    this.build();
  }
  build() {
    const bench = this.bench, app = this.app, view = bench.view, st = bench.settings;
    const root = this.root;

    // модель: что открыто и, с сервера, из чего выбирать
    root.appendChild(this.buildModel());

    // ракурсы
    this.presetButtons = new Map();
    const presetRow = el("div", { class: "row" });
    for (const name of view.preset_names()) {
      const b = el("button", { text: name, on: { click: () => app.invoke("preset", name) } });
      this.presetButtons.set(name, b);
      presetRow.appendChild(b);
    }
    root.appendChild(el("section", null, [el("h2", { text: "Ракурс" }), presetRow,
      el("div", { class: "row", style: "margin-top:6px" }, [
        el("button", { text: "масштаб 1:1", on: { click: () => { app.invoke("zoom", 1.0); } } }),
        el("button", { text: "сбросить панораму", on: { click: () => app.invoke("pan", 0, 0) } }),
      ])]));

    // наведение
    const targets = bench.focus_targets();
    this.focusSelect = el("select", { on: { change: () => this.onFocus() } });
    this.focusSelect.appendChild(el("option", { value: "", text: "вся модель" }));
    const groups = [["shapes", "части меша", "shape"], ["bones", "кости", "bone"], ["morphs", "морфы", "morph"]];
    for (const [key, title, kind] of groups) {
      if (!targets[key].length) continue;
      const g = el("optgroup", { label: title });
      for (const t of targets[key]) g.appendChild(el("option", { value: kind + ":" + t.name, text: t.name }));
      this.focusSelect.appendChild(g);
    }
    this.focusInfo = el("div", { class: "muted" });
    root.appendChild(el("section", null, [el("h2", { text: "Наведение" }), this.focusSelect, this.focusInfo]));

    // части меша
    this.partBoxes = new Map();
    const parts = el("div", { class: "parts" });
    for (const name of bench.shape_names()) {
      const box = el("input", { type: "checkbox", on: { change: () => this.onPart(name, box.checked) } });
      this.partBoxes.set(name, box);
      const s = bench.shape(name);
      parts.appendChild(el("div", { class: "part" }, [
        el("label", null, [box, el("span", { text: name }), el("span", { class: "muted", text: s.count + " в." })]),
        el("span", { class: "only", text: "только", on: { click: () => app.invoke("only", [name]) } })]));
    }
    root.appendChild(el("section", null, [el("h2", { text: "Части меша" }),
      bench.shape_names().length ? parts : el("div", { class: "muted", text: "меш не открыт" }),
      el("div", { class: "row", style: "margin-top:6px" }, [
        el("button", { text: "показать все", on: { click: () => app.invoke("show_all") } })])]));

    // капсулы столкновений - раздел есть только при открытом скелете: без него слоя нет
    // и в ядре. Обе галочки - один метод фасада show_colliders(on, bumper); галочка
    // капсул бампер не трогает (null), галочка бампера оставляет слой как есть.
    this.colliderBox = null; this.bumperBox = null;
    if (bench.has_skeleton()) {
      this.colliderBox = el("input", { type: "checkbox",
        on: { change: () => app.invoke("show_colliders", this.colliderBox.checked, null) } });
      this.bumperBox = el("input", { type: "checkbox",
        on: { change: () => app.invoke("show_colliders", bench.view.colliders, this.bumperBox.checked) } });
      if (!bench.bumper_mesh()) { this.bumperBox.disabled = true; this.bumperBox.title = "в скелете нет цилиндра перемещения"; }
      root.appendChild(el("section", null, [el("h2", { text: "Капсулы" }),
        el("div", { class: "current" }, [el("span", { text: bench.names.skeleton }),
          el("span", { class: "muted", text: " · капсул " + bench.summary.colliders })]),
        el("div", { class: "row", style: "margin-top:6px" }, [
          el("label", null, [this.colliderBox, " капсулы"]),
          el("label", null, [this.bumperBox, " бампер"])]),
        el("div", { class: "muted", text: "полупрозрачно поверх тела; цвет и прозрачность — colliderColour и colliderOpacity из настроек" })]));
    }

    // раскраска
    this.colourRadios = new Map();
    const modes = [["shade", "затенение"], ["bone", "кости"], ["morph", "морф"], ["strain", "растяжение"]];
    const modeRow = el("div", { class: "row" });
    for (const [mode, title] of modes) {
      const r = el("input", { type: "radio", name: "colouring", value: mode, on: { change: () => this.onColour() } });
      this.colourRadios.set(mode, r);
      modeRow.appendChild(el("label", null, [r, " " + title]));
    }
    this.morphSelect = el("select", { on: { change: () => this.onColour() } });
    this.morphSelect.appendChild(el("option", { value: "", text: "— морф не выбран —" }));
    for (const m of bench.morphs()) this.morphSelect.appendChild(el("option", { value: m, text: m }));
    root.appendChild(el("section", null, [el("h2", { text: "Раскраска" }), modeRow,
      el("div", { class: "row", style: "margin-top:6px" }, [el("span", { class: "muted", text: "морф для режимов «морф» и «растяжение»:" })]),
      this.morphSelect]));

    // свет: за камерой или мировой, направление на источник, три силы
    this.lightFollowBox = el("input", { type: "checkbox",
      on: { change: () => app.invoke("light_follow_camera", this.lightFollowBox.checked) } });
    this.lightDirLabel = el("span", { class: "muted" });
    this.lightDirInputs = [0, 1, 2].map(() => el("input", { type: "number", step: "any", class: "short",
      on: { change: () => this.onLightDir() } }));
    this.lightPowerInputs = {};
    const powerRow = el("div", { class: "row" });
    for (const [key, title] of [["ambient", "рассеянный"], ["diffuse", "направленный"], ["fill", "встречный"]]) {
      const inp = el("input", { type: "number", step: "any", min: "0", class: "short", on: { change: () => this.onLightPower() } });
      this.lightPowerInputs[key] = inp;
      powerRow.appendChild(el("label", null, [title + " ", inp]));
    }
    root.appendChild(el("section", null, [el("h2", { text: "Свет" }),
      el("div", { class: "row" }, [el("label", null, [this.lightFollowBox, " за камерой"])]),
      el("div", { class: "row", style: "margin-top:6px" }, [this.lightDirLabel].concat(this.lightDirInputs)),
      el("div", { class: "muted", style: "margin-top:6px", text: "силы света:" }), powerRow,
      el("div", { class: "row", style: "margin-top:6px" }, [
        el("button", { text: "как в настройках", on: { click: () => this.resetLight() } }),
        el("span", { class: "muted", text: "затенение: " + st.shading })])]));

    // ползунки
    this.sliderRows = new Map();
    const range = st.sliderRange, step = String(st.sliderStep);
    const sliders = el("div");
    for (const name of bench.morphs()) {
      const rng = el("input", { type: "range", min: range[0], max: range[1], step: step });
      const num = el("input", { type: "number", step: step });
      rng.addEventListener("input", () => { num.value = rng.value; app.invoke("set_slider", name, Number(rng.value)); });
      num.addEventListener("change", () => { app.invoke("set_slider", name, Number(num.value) || 0); });
      const row = el("div", { class: "slider" }, [el("span", { class: "name", text: name, title: name }), rng, num]);
      this.sliderRows.set(name, { row, rng, num });
      sliders.appendChild(row);
    }
    root.appendChild(el("section", null, [el("h2", { text: "Ползунки" }),
      bench.morphs().length ? sliders : el("div", { class: "muted", text: bench.is_open() ? "к мешу не открыт файл морфов" : "меш не открыт" }),
      el("div", { class: "row", style: "margin-top:6px" }, [
        el("button", { text: "сбросить", on: { click: () => app.invoke("reset_sliders") } }),
        el("span", { class: "muted", text: "пределы " + range[0] + " … " + range[1] + " из настроек" })])]));

    // легенда костей
    this.legendSelect = el("select", { on: { change: () => this.refreshLegend() } });
    for (const name of bench.shape_names()) this.legendSelect.appendChild(el("option", { value: name, text: name }));
    if (bench.shapes.has(st.baseShape)) this.legendSelect.value = st.baseShape;
    this.legend = el("div", { class: "legend" });
    this.legendSection = el("section", null, [el("h2", { text: "Легенда костей" }), this.legendSelect, this.legend]);
    root.appendChild(this.legendSection);

    // состояние
    this.lastCall = el("pre", { text: "" });
    this.state = el("pre");
    this.command = el("pre");
    this.note = el("div", { class: "muted" });
    this.error = el("div", { class: "err" });
    root.appendChild(el("section", null, [el("h2", { text: "Состояние" }),
      el("div", { class: "muted", text: "последний вызов фасада:" }), this.lastCall,
      el("div", { class: "muted", text: "view_state() и sliders():" }), this.state,
      el("div", { class: "muted", text: "тот же кадр без окна:" }), this.command, this.note, this.error]));
  }

  // Раздел «Модель». В файле с диска - только имя открытого меша: выбирать не из чего, и
  // страница не обращается никуда. С сервера - список мешей под корнем обзора, папка
  // и обход без морфов; выбор ведёт на тот же сервер с другим запросом.
  buildModel() {
    const bench = this.bench, names = bench.names, srv = bench.server;
    const current = el("div", { class: "current" }, [
      el("span", { text: names.nif || "меш не открыт" }),
      names.tri ? el("span", { class: "muted", text: " · морфы: " + names.tri + " (" + bench.summary.triKind + ")" }) : null]);
    if (!srv) {
      return el("section", null, [el("h2", { text: "Модель" }), current,
        el("div", { class: "muted", text: "выбор модели — в mb.py serve" })]);
    }
    const env = srv.environment || {};
    const envLine = el("div", { class: "muted", text:
      "под MO2: " + (env.insideMo2 ? "да" : "нет") + " · корень: " + (srv.root || "не задан") });
    // список мешей: группы по папке от корня, в строке - файл и формат морфов
    this.modelSelect = el("select", { on: { change: () => this.onModel() } });
    this.modelSelect.appendChild(el("option", { value: "",
      text: srv.catalog.length ? "— выбрать меш (" + srv.catalog.length + ") —" : "— мешей под корнем нет —" }));
    const groups = new Map();
    const same = (a, b) => !!a && !!b && a.replace(/\\/g, "/").toLowerCase() === b.replace(/\\/g, "/").toLowerCase();
    let currentName = "";
    for (const e of srv.catalog) {
      let g = groups.get(e.folder);
      if (!g) { g = el("optgroup", { label: e.folder || "." }); groups.set(e.folder, g); this.modelSelect.appendChild(g); }
      g.appendChild(el("option", { value: e.name, text: e.file + " · " + (e.kind || "без морфов") }));
      if (bench.summary && same(e.nif, bench.summary.nif)) currentName = e.name;
    }
    this.modelSelect.value = currentName;
    // папка обзора и обход без морфов
    this.rootInput = el("input", { type: "text", class: "wide", value: srv.root || "", title: "папка обзора" });
    this.allBox = el("input", { type: "checkbox", on: { change: () => this.go({ root: this.rootInput.value }) } });
    this.allBox.checked = !srv.withMorphs;
    return el("section", null, [el("h2", { text: "Модель" }), current, this.modelSelect,
      el("div", { class: "row", style: "margin-top:6px" }, [this.rootInput,
        el("button", { text: "обзор", on: { click: () => this.go({ root: this.rootInput.value }) } })]),
      el("div", { class: "row" }, [el("label", null, [this.allBox, " и без морфов"])]),
      envLine, el("div", { class: "err", text: srv.error || "" })]);
  }
  // Переход на тот же сервер с другим телом или корнем: страница держит одно тело, поэтому
  // смена модели - это перезагрузка с другим запросом, а не второй набор геометрии.
  go(params) {
    const q = [];
    for (const k in params) if (params[k] !== undefined && params[k] !== null && params[k] !== "") q.push(k + "=" + encodeURIComponent(params[k]));
    if (this.allBox && this.allBox.checked) q.push("all=1");
    window.location.href = "/?" + q.join("&");
  }
  onModel() {
    const name = this.modelSelect.value;
    if (name) this.go({ name: name, root: this.bench.server.root });
  }

  // --- действия панели: каждое - вызов метода зеркала фасада ---
  onFocus() {
    const v = this.focusSelect.value;
    if (!v) return this.app.invoke("focus_all");
    const i = v.indexOf(":"), kind = v.slice(0, i), name = v.slice(i + 1);
    this.app.invoke("focus_" + kind, name);
  }
  // Галочка части - это only() со списком видимых либо show_all(), когда видны все:
  // так состояние остаётся тем же, каким его выдаст view_state() ядра.
  onPart(name, checked) {
    const view = this.bench.view, all = this.bench.shape_names();
    const names = all.filter((n) => n === name ? checked : view.is_visible(n));
    if (names.length === all.length) this.app.invoke("show_all");
    else this.app.invoke("only", names);
  }
  onColour() {
    let mode = "shade";
    for (const [m, r] of this.colourRadios) if (r.checked) mode = m;
    const morph = this.morphSelect.value || null;
    this.app.invoke("colour_by", mode, (mode === "morph" || mode === "strain") ? morph : null);
  }
  onLightDir() {
    const v = this.lightDirInputs.map((i) => Number(i.value) || 0);
    this.app.invoke("light_direction", v[0], v[1], v[2]);
    this.showLight(this.bench.view.as_dict().light, true);   // в полях - то, что принял фасад
  }
  onLightPower() {
    const v = (key) => Number(this.lightPowerInputs[key].value) || 0;
    this.app.invoke("light_power", v("ambient"), v("diffuse"), v("fill"));
    this.showLight(this.bench.view.as_dict().light, true);
  }
  // Свет как в настройках - один вызов фасада, у которого есть такой же метод в ядре.
  resetLight() {
    this.app.invoke("light_reset");
  }

  // --- отражение состояния ---
  showLight(light, force) {
    this.lightFollowBox.checked = light.follow;
    this.lightDirLabel.textContent = light.follow ? "вправо, вверх, к зрителю:" : "X, Y, Z мировые:";
    light.direction.forEach((v, i) => {
      const inp = this.lightDirInputs[i];
      if (force || document.activeElement !== inp) inp.value = v;
    });
    for (const key in this.lightPowerInputs) {
      const inp = this.lightPowerInputs[key];
      if (force || document.activeElement !== inp) inp.value = light[key];
    }
  }
  refresh() {
    const bench = this.bench, view = bench.view, state = view.as_dict();
    const preset = state.preset;
    for (const [name, b] of this.presetButtons) b.classList.toggle("on", name === preset);

    // наведение
    const focusValue = state.focus ? state.focus.name : "";
    if (focusValue && !Array.from(this.focusSelect.options).some((o) => o.value === focusValue)) {
      // цель задана из командной строки по подстроке - ядро уже сосчитало сферу, покажем её как есть
      this.focusSelect.appendChild(el("option", { value: focusValue, text: focusValue + " (из командной строки)" }));
    }
    this.focusSelect.value = focusValue;
    this.focusInfo.textContent = state.focus
      ? "центр " + state.focus.centre.join(" ") + ", радиус " + state.focus.radius + " × запас " + bench.settings.focusPadding
      : "кадр охватывает видимые части";

    // части
    for (const [name, box] of this.partBoxes) box.checked = view.is_visible(name);

    // капсулы
    if (this.colliderBox) { this.colliderBox.checked = view.colliders; this.bumperBox.checked = view.bumper; }

    // раскраска
    for (const [mode, r] of this.colourRadios) r.checked = (mode === view.colouring);
    this.morphSelect.value = view.highlightMorph || "";
    this.legendSection.style.display = view.colouring === "bone" && bench.shape_names().length ? "" : "none";
    if (view.colouring === "bone" && this.legendSelect.value && this.legendFor !== this.legendSelect.value) this.refreshLegend();

    // свет
    this.showLight(state.light, false);

    // ползунки
    const sliders = bench.sliders();
    for (const [name, r] of this.sliderRows) {
      const v = name in sliders ? sliders[name] : 0;
      if (document.activeElement !== r.rng) r.rng.value = v;
      if (document.activeElement !== r.num) r.num.value = fmt(v);
      r.row.classList.toggle("active", name in sliders);
    }

    // состояние и команда
    this.lastCall.textContent = this.app.lastCall || "—";
    this.state.textContent = JSON.stringify({ view: state, sliders: sliders }, null, 2);
    this.command.textContent = this.buildCommand(preset);
    const notes = [];
    if (state.visible !== null && state.visible.length === 0) notes.push("скрыты все части - растеризатору нечего рисовать.");
    this.note.textContent = notes.join(" ");
  }
  refreshLegend() {
    const shape = this.bench.shape(this.legendSelect.value);
    const palette = Palette.bones(shape.boneNames.length);
    this.legendFor = shape.name;
    this.legend.textContent = "";
    shape.boneNames.forEach((name, i) => {
      const c = [palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]].map((x) => Math.round(x * 255));
      this.legend.appendChild(el("div", { title: name }, [el("span", { class: "swatch", style: "background:rgb(" + c.join(",") + ")" }), name]));
    });
    const g = Palette.NO_BONE.map((x) => Math.round(x * 255));
    this.legend.appendChild(el("div", null, [el("span", { class: "swatch", style: "background:rgb(" + g.join(",") + ")" }), "без кости"]));
  }
  // Командная строка mb.py render с теми же ключами, что принимает cmd_render: всё, что
  // нажато на странице, можно повторить без окна. Пары чисел идут через знак равенства,
  // чтобы минус впереди не был принят разборщиком за ключ. Свет попадает в команду только
  // там, где отличается от настроек: без ключей render светит так же, как настройки.
  buildCommand(preset) {
    const bench = this.bench, st = bench.settings, state = bench.view.as_dict(), sliders = bench.sliders();
    if (!bench.summary) return "меш не открыт — кадр брать не с чего";
    const q = (s) => /[^\w.\-=:\\\/]/.test(s) ? '"' + s.replace(/"/g, '\\"') + '"' : s;
    const parts = ["python", "mb.py", "render", q(bench.summary.nif), "--out", "кадр.png"];
    if (bench.summary.tri) parts.push("--tri", q(bench.summary.tri));
    if (preset) parts.push("--view", preset); else parts.push("--look=" + state.yaw + "," + state.pitch);
    for (const name in sliders) parts.push("--slider", q(name + "=" + fmt(sliders[name])));
    if (state.colouring !== "shade") parts.push("--colour", state.colouring);
    if (state.highlightMorph) parts.push("--morph", q(state.highlightMorph));
    if (state.visible !== null) parts.push("--only", q(state.visible.join(",")));
    if (Math.abs(state.zoom - 1.0) > 1e-9) parts.push("--zoom", fmt(state.zoom));
    if (state.pan[0] !== 0 || state.pan[1] !== 0) parts.push("--pan=" + state.pan[0] + "," + state.pan[1]);
    if (state.width !== st.imageWidth || state.height !== st.imageHeight)
      parts.push("--size", state.width + "x" + state.height);
    if (state.focus) {
      const i = state.focus.name.indexOf(":");
      parts.push("--focus-" + state.focus.name.slice(0, i), q(state.focus.name.slice(i + 1)));
    }
    // Слой капсул: скелет называется явно, даже если render нашёл бы его рядом с мешем сам.
    if (state.colliders && bench.summary.skeleton) {
      parts.push("--skeleton", q(bench.summary.skeleton), "--colliders");
      if (state.bumper) parts.push("--bumper");
    }
    const light = state.light;
    if (light.follow !== st.lightFollowCamera) parts.push("--light", light.follow ? "camera" : "world");
    const dirDefault = (light.follow ? st.lightCameraDirection : st.lightDirection).map((x) => rnd(x, 3));
    if (light.direction.some((x, i) => x !== dirDefault[i])) parts.push("--light-dir=" + light.direction.join(","));
    if (light.ambient !== rnd(st.ambient, 3) || light.diffuse !== rnd(st.diffuse, 3) || light.fill !== rnd(st.fill, 3))
      parts.push("--light-power=" + [light.ambient, light.diffuse, light.fill].join(","));
    return parts.join(" ");
  }
}

// ---- страница целиком ---------------------------------------------------------------------
const POSITION_METHODS = new Set(["set_slider", "set_sliders", "reset_sliders"]);
const COLOUR_METHODS = new Set(["colour_by"]);

class App {
  constructor(data) {
    this.data = data;
    this.bench = new BenchMirror(data);
    this.lastCall = "";
    this.scale = 1.0;
    this.canvas = document.getElementById("canvas");
    this.renderer = new Renderer(this.canvas, data.settings);
    for (const name of this.bench.shape_names()) this.renderer.upload(this.bench.shape(name));
    // Капсулы - в буферы один раз: ползунки их не двигают, цвет у них один.
    this.renderer.uploadColliders(this.bench.collider_mesh());
    this.renderer.uploadColliders(this.bench.bumper_mesh());
    this.refreshPositions();
    this.refreshColours();
    this.panel = new Panel(this, document.getElementById("panel"));
    this.bindMouse();
    new ResizeObserver(() => this.draw()).observe(this.canvas.parentElement);
    this.panel.refresh();
    this.draw();
  }
  // Единственная дверь ко всем действиям: имя метода фасада и его доводы.
  invoke(method, ...args) {
    this.panel.error.textContent = "";
    try {
      this.bench[method](...args);
    } catch (e) {
      this.panel.error.textContent = String(e.message || e);
      return;
    }
    this.lastCall = "bench." + method + "(" + args.map((a) => JSON.stringify(a)).join(", ") + ")";
    if (POSITION_METHODS.has(method)) this.refreshPositions();
    if (COLOUR_METHODS.has(method)) this.refreshColours();
    this.panel.refresh();
    this.draw();
  }
  // Позиции с применёнными ползунками и нормали по ним - в буферы; нормали пересчитываются
  // после каждого движения ползунка, потому что затенение идёт по деформированному телу.
  refreshPositions() {
    for (const name of this.bench.shape_names()) {
      const s = this.bench.shape(name);
      this.bench.vertex_normals(name);         // внутри - deformed(): позиции и нормали разом
      this.renderer.setPositions(s);
      this.renderer.setNormals(s);
    }
  }
  // Признак у фасада, цвет - здесь: то же правило, что у растеризатора.
  refreshColours() {
    for (const name of this.bench.shape_names()) {
      const s = this.bench.shape(name);
      if (!s.triCount) continue;
      const key = this.bench.vertex_colour_key(name);
      let colours;
      if (key === null) {
        colours = new Float32Array(s.count * 3).fill(Palette.SHADE);
      } else if (this.bench.view.colouring === "bone") {
        const palette = Palette.bones(s.boneNames.length), last = Math.max(s.boneNames.length - 1, 0);
        colours = new Float32Array(s.count * 3);
        for (let i = 0; i < s.count; i++) {
          const k = key[i];
          if (k < 0) { colours[i * 3] = Palette.NO_BONE[0]; colours[i * 3 + 1] = Palette.NO_BONE[1]; colours[i * 3 + 2] = Palette.NO_BONE[2]; }
          else { const j = clamp(k, 0, last) * 3; colours[i * 3] = palette[j]; colours[i * 3 + 1] = palette[j + 1]; colours[i * 3 + 2] = palette[j + 2]; }
        }
      } else {
        colours = Palette.heat(key);
      }
      this.renderer.setColours(s, colours);
    }
  }
  // Размер холста - тоже состояние показа: он уходит в ядро тем же resize, что и --size.
  draw() {
    this.renderer.resize();
    const w = this.canvas.width, h = this.canvas.height, view = this.bench.view;
    if (w !== view.width || h !== view.height) { this.invoke("resize", w, h); return; }
    const r = this.renderer.draw(this.bench);
    if (r) this.scale = r.scale;
  }
  // Точка курсора в долях половины меньшей стороны холста от центра, вправо и вверх, -
  // в пикселях холста с учётом плотности экрана и положения холста на странице.
  cursorFraction(e) {
    const c = this.canvas, rect = c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    const px = (e.clientX - rect.left) * dpr, py = (e.clientY - rect.top) * dpr;
    const w = c.width, h = c.height, m = Math.min(w, h) * 0.5;
    return [(px - w * 0.5) / m, (h * 0.5 - py) / m];
  }
  bindMouse() {
    const c = this.canvas;
    let drag = null;
    c.addEventListener("contextmenu", (e) => e.preventDefault());
    c.addEventListener("pointerdown", (e) => {
      drag = { button: e.button, x: e.clientX, y: e.clientY };
      try { c.setPointerCapture(e.pointerId); } catch (_) { /* указатель без захвата - не беда */ }
    });
    c.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      drag.x = e.clientX; drag.y = e.clientY;
      if (drag.button === 0) {
        const k = this.bench.settings.orbitSensitivity;
        this.invoke("orbit", rnd(dx * k, 2), rnd(dy * k, 2));
      } else if (drag.button === 2) {
        // Пиксели экрана в единицы модели через масштаб кадра - и в ядро тем же методом.
        const dpr = window.devicePixelRatio || 1;
        this.invoke("pan_by", rnd(dx * dpr / this.scale, 3), rnd(-dy * dpr / this.scale, 3));
      }
    });
    const stop = (e) => { drag = null; try { c.releasePointerCapture(e.pointerId); } catch (_) {} };
    c.addEventListener("pointerup", stop);
    c.addEventListener("pointercancel", stop);
    // Колесо - масштаб к точке под курсором: zoom_at фасада с новым масштабом и долями кадра.
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const f = this.cursorFraction(e);
      const z = rnd(this.bench.view.zoom * Math.exp(-e.deltaY * this.bench.settings.wheelZoomRate), 3);
      this.invoke("zoom_at", z, rnd(f[0], 3), rnd(f[1], 3));
    }, { passive: false });
    c.addEventListener("dblclick", () => { this.invoke("pan", 0, 0); this.invoke("zoom", 1.0); });
  }
}

// ---- запуск ---------------------------------------------------------------------------------
const DATA = JSON.parse(document.getElementById("mb-data").textContent);
const s = DATA.summary;
document.getElementById("title").textContent = "morphbench — " + (DATA.names.nif || "меш не открыт");
document.getElementById("subtitle").textContent = s
  ? "морфы: " + (DATA.names.tri ? DATA.names.tri + " (" + s.triKind + ")" : "нет") +
    " · частей " + s.shapes + " · вершин " + s.vertices + " · костей " + s.bones + " · ползунков " + s.morphs +
    (DATA.names.skeleton ? " · скелет " + DATA.names.skeleton + " · капсул " + s.colliders : "")
  : (DATA.server ? "выберите меш в списке на панели" : "");
try {
  window.mb = new App(DATA);
} catch (e) {
  const box = document.getElementById("nogl");
  box.style.display = "flex";
  box.textContent = "Не удалось запустить смотрелку: " + (e.message || e);
  console.error(e);
}
})();
</script>
</body>
</html>
"""
