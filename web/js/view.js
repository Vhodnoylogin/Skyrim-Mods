"use strict";

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
    if (!(name in this.presets)) throw new Error(say(T.errNoPreset, { name }));
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
    if (norm(v) < 1e-6) throw new Error(T.errZeroLight);
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
    if (!["shade", "bone", "morph", "strain"].includes(mode)) throw new Error(T.errColourMode);
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
