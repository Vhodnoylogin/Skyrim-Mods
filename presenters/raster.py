"""Слой показа: картинка PNG прямо из чисел ядра.

Своими средствами, без Blender и без игры: ортографическая камера, буфер глубины и затенение
по нормали вершины. Тело вервольфа - тридцать четыре тысячи треугольников - рисуется за секунды,
а не за минуту, и это единственное, ради чего слой существует: увидеть результат сразу
после сборки, а не в следующем игровом прогоне.

Ничего не вычисляет сам. Вершины берёт у `MorphBench.deformed`, нормали - у `vertex_normals`,
кадр - у `framing`, признак раскраски - у `vertex_colour_key`, направление и силы света -
у `ViewState`. Перевод признака в цвет живёт здесь, потому что цвет - это уже показ.
"""
from __future__ import annotations

import colorsys
from pathlib import Path

import numpy as np
from PIL import Image


class Raster:
    """Растеризатор поверх фасада."""

    def __init__(self, bench):
        self.bench = bench
        self.cfg = bench.cfg

    # ---- цвета ------------------------------------------------------------------------
    @staticmethod
    def _bone_palette(count: int) -> np.ndarray:
        """Разные кости — заметно разные цвета. Золотой угол по кругу оттенков даёт
        соседям контраст, а не соседний оттенок одного цвета."""
        out = np.zeros((max(count, 1), 3), dtype=np.float32)
        for i in range(max(count, 1)):
            h = (i * 0.61803398875) % 1.0
            s = 0.55 + 0.25 * ((i * 7) % 3) / 2.0
            v = 0.70 + 0.25 * ((i * 5) % 2)
            out[i] = colorsys.hsv_to_rgb(h, s, v)
        return out

    @staticmethod
    def _heat(values: np.ndarray) -> np.ndarray:
        """Серое - ноль, дальше жёлтое и красное. Для величины сдвига и растяжения."""
        v = np.asarray(values, dtype=np.float32)
        top = float(v.max()) if v.size else 0.0
        t = np.zeros_like(v) if top <= 1e-6 else np.clip(v / top, 0.0, 1.0)
        rgb = np.zeros((v.shape[0], 3), dtype=np.float32)
        rgb[:, 0] = 0.35 + 0.65 * t
        rgb[:, 1] = 0.35 + 0.55 * np.clip(1.6 * t, 0, 1) * (1.0 - 0.85 * t)
        rgb[:, 2] = 0.35 * (1.0 - t)
        return rgb

    def _vertex_colours(self, shape_name: str, count: int) -> np.ndarray | None:
        key = self.bench.vertex_colour_key(shape_name)
        if key is None:
            return None
        if self.bench.view.colouring == "bone":
            shape = self.bench.model.shape(shape_name)
            palette = self._bone_palette(len(shape.bones))
            idx = np.clip(key, 0, max(len(palette) - 1, 0))
            col = palette[idx]
            col[key < 0] = np.array([0.30, 0.30, 0.33], np.float32)
            return col
        return self._heat(key)

    # ---- геометрия сцены --------------------------------------------------------------
    def _collect(self):
        """Все видимые части в одном массиве: вершины, нормали, треугольники, цвета вершин."""
        verts, norms, tris, cols = [], [], [], []
        base = 0
        for name in self.bench.visible_shapes():
            shape = self.bench.model.shape(name)
            if shape.triangle_count == 0:
                continue
            v = self.bench.deformed(name)
            c = self._vertex_colours(name, shape.vertex_count)
            verts.append(v)
            norms.append(self.bench.vertex_normals(name))
            tris.append(shape.tris + base)
            cols.append(np.full((shape.vertex_count, 3), 0.72, np.float32) if c is None else c)
            base += shape.vertex_count
        if not verts:
            raise RuntimeError("нечего рисовать: все части меша скрыты")
        return (np.vstack(verts), np.vstack(norms), np.vstack(tris), np.vstack(cols))

    # ---- свет -------------------------------------------------------------------------
    def _lit(self, normals: np.ndarray) -> np.ndarray:
        """Сила света на нормали: рассеянная плюс направленная с той стороны, откуда светит,
        плюс встречная подсветка с противоположной - чтобы тень не была слепой."""
        view = self.bench.view
        light = np.asarray(view.light_vector(), dtype=np.float32)
        lam = normals @ light
        return (view.ambient + view.diffuse * np.clip(lam, 0.0, 1.0)
                + view.fill * np.clip(-lam, 0.0, 1.0)).astype(np.float32)

    # ---- рисование --------------------------------------------------------------------
    def _screen(self, verts: np.ndarray):
        """Вершины в координатах холста: вправо, вниз и глубина от зрителя."""
        view = self.bench.view
        w, h = view.width, view.height
        basis = view.basis()
        # Кадр - вся модель, сфера наведения или панорама - решает ядро.
        centre, half = self.bench.framing()
        local = (verts - centre) @ basis.T          # x вправо, y вверх, z от зрителя
        scale = ((min(w, h) * float(self.cfg["frameFill"]))
                 / max(half * 2.0, 1e-3) * view.zoom)
        return (local[:, 0] * scale + w * 0.5,
                h * 0.5 - local[:, 1] * scale,
                local[:, 2])

    def image(self) -> Image.Image:
        view = self.bench.view
        w, h = view.width, view.height
        verts, normals, tris, vcols = self._collect()

        sx, sy, depth = self._screen(verts)

        bg = np.array(self.cfg["background"], dtype=np.float32) / 255.0
        colour = np.tile(bg, (h, w, 1)).astype(np.float32)
        zbuf = np.full((h, w), np.inf, dtype=np.float32)

        a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
        ax, ay, bx, by, cx, cy = sx[a], sy[a], sx[b], sy[b], sx[c], sy[c]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)

        # Затенение. Мягкое - свет считается в вершинах и растягивается по треугольнику
        # вместе с цветом; плоское - одна сила света на треугольник, по его нормали.
        if str(self.cfg["shading"]) == "flat":
            n = np.cross(verts[b] - verts[a], verts[c] - verts[a])
            n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-6)
            shade = self._lit(n)
        else:
            vcols = vcols * self._lit(normals)[:, None]
            shade = np.ones(tris.shape[0], dtype=np.float32)

        keep = np.abs(area) > 1e-9
        order = np.nonzero(keep)[0]
        x0 = np.clip(np.floor(np.minimum(np.minimum(ax, bx), cx)).astype(np.int32), 0, w - 1)
        x1 = np.clip(np.ceil(np.maximum(np.maximum(ax, bx), cx)).astype(np.int32), 0, w - 1)
        y0 = np.clip(np.floor(np.minimum(np.minimum(ay, by), cy)).astype(np.int32), 0, h - 1)
        y1 = np.clip(np.ceil(np.maximum(np.maximum(ay, by), cy)).astype(np.int32), 0, h - 1)

        for t in order:
            xa, xb = x0[t], x1[t]
            ya, yb = y0[t], y1[t]
            if xb < xa or yb < ya:
                continue
            xs = np.arange(xa, xb + 1, dtype=np.float32) + 0.5
            ys = np.arange(ya, yb + 1, dtype=np.float32) + 0.5
            gx, gy = np.meshgrid(xs, ys)
            inv = 1.0 / area[t]
            w0 = ((bx[t] - ax[t]) * (gy - ay[t]) - (by[t] - ay[t]) * (gx - ax[t])) * inv
            w1 = ((gx - ax[t]) * (cy[t] - ay[t]) - (gy - ay[t]) * (cx[t] - ax[t])) * inv
            inside = (w0 >= 0) & (w1 >= 0) & (w0 + w1 <= 1.0)
            if not inside.any():
                continue
            u = w1[inside]
            v = w0[inside]
            s = 1.0 - u - v
            z = s * depth[a[t]] + u * depth[b[t]] + v * depth[c[t]]
            sub = zbuf[ya:yb + 1, xa:xb + 1]
            mask = np.zeros_like(inside)
            mask[inside] = z < sub[inside]
            if not mask.any():
                continue
            u = w1[mask]
            v = w0[mask]
            s = 1.0 - u - v
            z = s * depth[a[t]] + u * depth[b[t]] + v * depth[c[t]]
            base = (s[:, None] * vcols[a[t]] + u[:, None] * vcols[b[t]] + v[:, None] * vcols[c[t]])
            sub[mask] = z
            csub = colour[ya:yb + 1, xa:xb + 1]
            csub[mask] = np.clip(base * shade[t], 0.0, 1.0)

        if view.colliders and self.bench.has_skeleton():
            self._overlay_colliders(colour, zbuf)
        return Image.fromarray((colour * 255.0).astype(np.uint8), mode="RGB")

    def _overlay_colliders(self, colour: np.ndarray, zbuf: np.ndarray) -> None:
        """Капсулы поверх тела - полупрозрачно, с собственной глубиной.

        Смысл прозрачности в том, что видно обе оболочки сразу: там, где капсула лежит
        внутри тела, она просвечивает сквозь кожу, а там, где вылезает наружу, ложится
        прямо на фон и сразу бросается в глаза. Ради этого капсулы НЕ пишут в общий
        буфер глубины - иначе они закрыли бы собой то, что мы и хотим с ними сравнить.
        """
        verts, tris = self.bench.collider_mesh()
        if tris.shape[0] == 0:
            return
        alpha = float(self.cfg["colliderOpacity"])
        tint = np.array(self.cfg["colliderColour"], dtype=np.float32) / 255.0
        sx, sy, depth = self._screen(verts)
        normals = self._face_normals(verts, tris)
        shade = self._lit(normals)
        own = np.full(zbuf.shape, np.inf, dtype=np.float32)
        for t in range(tris.shape[0]):
            a, b, c = tris[t]
            self._paint_triangle(colour, own, sx, sy, depth, a, b, c,
                                 np.clip(tint * shade[t], 0.0, 1.0), alpha)

    @staticmethod
    def _face_normals(verts: np.ndarray, tris: np.ndarray) -> np.ndarray:
        n = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]],
                     verts[tris[:, 2]] - verts[tris[:, 0]])
        return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-6)

    @staticmethod
    def _paint_triangle(colour, zbuf, sx, sy, depth, a, b, c, rgb, alpha) -> None:
        """Один треугольник ровным цветом с проверкой глубины и подмешиванием."""
        h, w = zbuf.shape
        ax, ay, bx, by, cx, cy = sx[a], sy[a], sx[b], sy[b], sx[c], sy[c]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-9:
            return
        xa = max(int(np.floor(min(ax, bx, cx))), 0)
        xb = min(int(np.ceil(max(ax, bx, cx))), w - 1)
        ya = max(int(np.floor(min(ay, by, cy))), 0)
        yb = min(int(np.ceil(max(ay, by, cy))), h - 1)
        if xb < xa or yb < ya:
            return
        gx, gy = np.meshgrid(np.arange(xa, xb + 1, dtype=np.float32) + 0.5,
                             np.arange(ya, yb + 1, dtype=np.float32) + 0.5)
        inv = 1.0 / area
        w0 = ((bx - ax) * (gy - ay) - (by - ay) * (gx - ax)) * inv
        w1 = ((gx - ax) * (cy - ay) - (gy - ay) * (cx - ax)) * inv
        inside = (w0 >= 0) & (w1 >= 0) & (w0 + w1 <= 1.0)
        if not inside.any():
            return
        z = np.where(inside,
                     (1.0 - w1 - w0) * depth[a] + w1 * depth[b] + w0 * depth[c],
                     np.inf)
        sub = zbuf[ya:yb + 1, xa:xb + 1]
        mask = inside & (z < sub)
        if not mask.any():
            return
        sub[mask] = z[mask]
        csub = colour[ya:yb + 1, xa:xb + 1]
        csub[mask] = csub[mask] * (1.0 - alpha) + rgb * alpha

    def save(self, path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.image().save(path)
        return path

    def contact_sheet(self, out_dir, views=None, prefix="view") -> list[Path]:
        """Несколько ракурсов подряд — обычный способ посмотреть, что получилось."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        names = list(views) if views else self.bench.view.preset_names()
        saved = []
        for name in names:
            self.bench.preset(name)
            saved.append(self.save(out_dir / ("%s-%s.png" % (prefix, name))))
        return saved
