# -*- coding: utf-8 -*-
"""Масштаб к точке: то, что было под курсором, остаётся под курсором.

Проверка идёт формулами растеризатора, а не картинкой: масштаб
scale = min(w, h) · frameFill / (2 · half) · zoom, экранное положение точки p —
((p − centre)·right)·scale + w/2 по горизонтали и h/2 − ((p − centre)·up)·scale по вертикали,
где centre и half отдаёт framing(). Точка сцены под курсором (fx, fy) берётся с текущего
кадра, затем zoom_at и новый кадр — и её экранное положение обязано совпасть до 1e-3 px.
Ловит: знак или ось панорамы, не ту сторону холста (max вместо min), масштаб, взятый
до или после пересчёта кадра, зажим снизу, забытый пересчёт кадра в фасаде.
"""
import math
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench.view import ViewState  # noqa: E402

W, H = 640, 480          # холст нарочно не квадратный: ловит max вместо min
CURSORS = ((0.4, -0.3), (-0.8, 0.6), (0.95, 0.95), (0.0, 0.0))
TOLERANCE = 1e-3


def scale_of(view, half: float) -> float:
    return (min(view.width, view.height) * float(view.cfg["frameFill"])
            / (2.0 * float(half)) * float(view.zoom))


def screen_of(point, centre, half, view) -> tuple[float, float]:
    """Экранное положение точки сцены по формулам растеризатора."""
    right, up, _ = (np.asarray(v, dtype=np.float64) for v in view.basis())
    s = scale_of(view, half)
    d = np.asarray(point, dtype=np.float64) - np.asarray(centre, dtype=np.float64)
    return (float(d @ right) * s + view.width / 2.0, view.height / 2.0 - float(d @ up) * s)


def point_under(fx: float, fy: float, centre, half, view) -> np.ndarray:
    """Точка сцены под курсором: fx, fy — доли половины меньшей стороны от центра кадра,
    вправо и вверх. Лежит в плоскости кадра, проходящей через центр."""
    right, up, _ = (np.asarray(v, dtype=np.float64) for v in view.basis())
    s = scale_of(view, half)
    px = fx * min(view.width, view.height) / 2.0
    py = fy * min(view.width, view.height) / 2.0
    return np.asarray(centre, dtype=np.float64) + right * (px / s) + up * (py / s)


def distance(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class TestFormulas(unittest.TestCase):
    """Сами формулы проверки согласованы: точка под курсором проецируется в курсор.
    Оси камеры ядро считает в float32, поэтому допуск тот же, что и у главной проверки."""

    def test_point_under_projects_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = ViewState(common.config(tmp, imageWidth=W, imageHeight=H)).look(40, 15)
            view.set_zoom(1.7)
            centre, half = view.framing((3.0, -2.0, 5.0), 4.0)
            for fx, fy in CURSORS:
                p = point_under(fx, fy, centre, half, view)
                expected = (W / 2.0 + fx * min(W, H) / 2.0, H / 2.0 - fy * min(W, H) / 2.0)
                self.assertLess(distance(screen_of(p, centre, half, view), expected), TOLERANCE)


class TestViewStateZoomAt(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = common.config(self.tmp.name, imageWidth=W, imageHeight=H)
        self.view = ViewState(self.cfg)

    def test_without_frame_only_zoom_changes(self):
        """Пока кадра не было, точка под курсором неизвестна: меняется только масштаб."""
        self.assertIsNone(self.view.frame_half)
        state = self.view.zoom_at(2.0, 0.5, -0.5).as_dict()
        self.assertEqual(self.view.zoom, 2.0)
        self.assertEqual(self.view.pan.tolist(), [0.0, 0.0])
        self.assertIsNone(self.view.frame_half)
        self.assertEqual(state["zoom"], 2.0)
        self.assertEqual(state["pan"], [0.0, 0.0])

    def test_framing_remembers_half(self):
        """framing() оставляет полуразмах кадра — и переданный, и взятый от наведения."""
        self.view.framing((1.0, 2.0, 3.0), 7.5)
        self.assertEqual(self.view.frame_half, 7.5)
        self.view.focus_on((0.0, 0.0, 0.0), 2.0, "x")
        self.view.framing((1.0, 2.0, 3.0), 7.5)
        self.assertAlmostEqual(self.view.frame_half, 2.0 * float(self.cfg["focusPadding"]), places=6)

    def assertPointStays(self, view, centre0, half0, factor, fx, fy):
        centre, half = view.framing(centre0, half0)
        p = point_under(fx, fy, centre, half, view)
        before = screen_of(p, centre, half, view)
        view.zoom_at(factor, fx, fy)
        centre, half = view.framing(centre0, half0)
        after = screen_of(p, centre, half, view)
        self.assertLess(distance(before, after), TOLERANCE,
                        (view.yaw, view.pitch, factor, fx, fy, before, after))

    def test_point_stays_put(self):
        """С любого ракурса и при любом курсоре точка сцены под ним не сдвигается —
        ни при увеличении, ни при следующем уменьшении к другой точке."""
        for yaw, pitch in ((0, 0), (40, 15), (90, 0), (0, -60), (180, 0)):
            for fx, fy in CURSORS:
                view = ViewState(self.cfg).look(yaw, pitch)
                self.assertPointStays(view, (3.0, -2.0, 5.0), 4.0, 2.5, fx, fy)
                self.assertPointStays(view, (3.0, -2.0, 5.0), 4.0, 0.7, -fy, fx)
                self.assertPointStays(view, (3.0, -2.0, 5.0), 4.0, 3.0, fx, fy)

    def test_small_factor_clamped(self):
        """Масштаб меньше 0.05 зажимается, и панорама считается по зажатому — точка
        под курсором всё равно на месте."""
        self.view.framing((0.0, 0.0, 0.0), 1.0)
        self.view.zoom_at(0.01, 0.3, 0.3)
        self.assertEqual(self.view.zoom, 0.05)
        view = ViewState(self.cfg)
        self.assertPointStays(view, (0.0, 0.0, 0.0), 1.0, 0.001, 0.6, -0.4)
        self.assertEqual(view.zoom, 0.05)

    def test_same_factor_moves_nothing(self):
        """factor, равный текущему масштабу, не трогает ни масштаб, ни панораму."""
        self.view.set_pan(1.5, -2.0)
        self.view.framing((0.0, 0.0, 0.0), 3.0)
        self.view.zoom_at(1.0, 0.9, 0.9)
        self.assertEqual(self.view.pan.tolist(), [1.5, -2.0])
        self.assertEqual(self.view.zoom, 1.0)
        self.view.set_zoom(2.0)
        self.view.zoom_at(2.0, -0.9, 0.2)
        self.assertEqual(self.view.pan.tolist(), [1.5, -2.0])

    def test_centre_cursor_keeps_pan(self):
        """Курсор в центре кадра — обычный масштаб от центра: панорама не меняется."""
        self.view.set_pan(0.25, 0.75)
        self.view.framing((0.0, 0.0, 0.0), 3.0)
        self.view.zoom_at(4.0, 0.0, 0.0)
        self.assertEqual(self.view.pan.tolist(), [0.25, 0.75])
        self.assertEqual(self.view.zoom, 4.0)


class TestFacadeZoomAt(unittest.TestCase):
    """MorphBench.zoom_at считает кадр сам: точка берётся с кадра, который на экране."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def build(self):
        return common.bench(self.tmp.name, common.sample_model(), common.sample_morphs(),
                            imageWidth=W, imageHeight=H)

    def test_facade_computes_framing_itself(self):
        """У свежего бенча кадра не было; после zoom_at он есть, панорама сдвинута,
        а ответ — тот же словарь, что view_state()."""
        bench = self.build()
        self.assertIsNone(bench.view.frame_half)
        state = bench.zoom_at(2.0, 0.5, 0.5)
        self.assertEqual(state, bench.view_state())
        self.assertIsNotNone(bench.view.frame_half)
        self.assertEqual(state["zoom"], 2.0)
        self.assertNotEqual(state["pan"], [0.0, 0.0])
        self.assertTrue(common.is_plain(state), state)

    def assertPointStays(self, bench, factor, fx, fy):
        view = bench.view
        centre, half = bench.framing()
        p = point_under(fx, fy, centre, half, view)
        before = screen_of(p, centre, half, view)
        bench.zoom_at(factor, fx, fy)
        centre, half = bench.framing()
        after = screen_of(p, centre, half, view)
        self.assertLess(distance(before, after), TOLERANCE,
                        (view.yaw, view.pitch, factor, fx, fy, before, after))

    def test_point_stays_under_cursor(self):
        for preset in ("front", "quarter", "top", "side"):
            bench = self.build()
            bench.preset(preset)
            for fx, fy in CURSORS:
                self.assertPointStays(bench, 2.0, fx, fy)
                self.assertPointStays(bench, 0.5, -fx, -fy)

    def test_with_focus_and_sliders(self):
        """Наведение и ползунки меняют кадр — точка под курсором всё равно на месте."""
        bench = self.build()
        bench.preset("quarter")
        bench.focus_shape("fur")
        bench.set_slider("Up", 1.0)
        for fx, fy in CURSORS:
            self.assertPointStays(bench, 3.0, fx, fy)
        bench.focus_all()
        for fx, fy in CURSORS:
            self.assertPointStays(bench, 0.4, fx, fy)

    def test_frame_half_matches_framing(self):
        bench = self.build()
        _, half = bench.framing()
        self.assertEqual(bench.view.frame_half, half)


if __name__ == "__main__":
    common.main()
