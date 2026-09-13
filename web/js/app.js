"use strict";

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
    // Капсулы - в буферы один раз, все куски по костям: ползунки их не двигают, цвет
    // у них один, а какие из них рисовать, решает collider_mesh() на каждый кадр.
    for (const chunk of this.bench.collider_meshes()) this.renderer.uploadColliders(chunk);
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
