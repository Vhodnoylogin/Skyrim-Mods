# -*- coding: utf-8 -*-
"""Кадр: центр и полуразмах, которые ядро отдаёт рисующему слою.

Кожа — сетка 6×4 на z=0 (x 0..5, y 0..3), оболочка — сетка 4×4 на z=1 (x 0..3), «точки» —
часть без треугольников далеко в стороне. Центр — середина охвата видимых частей
с треугольниками по деформированным вершинам, полуразмах — наибольшая из |x| и |y|
в осях камеры; всё считается в уме. Ловит: невидимую часть в кадре, ползунок, не доехавший
до кадра, точки без треугольников, растянувшие кадр, наведение и панораму, не учтённые
ядром, и кадр, посчитанный в мировых осях вместо осей камеры.
"""
import math
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench import Shape  # noqa: E402

NX, NY = 6, 4
WHOLE_CENTRE = (2.5, 1.5, 0.5)
FUR_CENTRE = (1.5, 1.5, 1.0)


def dots() -> Shape:
    """Две вершины далеко в стороне и ни одного треугольника."""
    verts = np.array([[100.0, 100.0, 100.0], [-100.0, -100.0, -100.0]], dtype=np.float32)
    return Shape("dots", verts, np.zeros((0, 3), dtype=np.int32), None, None, {})


def build(tmpdir, with_dots: bool = False, **overrides):
    shapes = [common.grid("body", NX, NY), common.grid("fur", 4, 4, z=1.0)]
    if with_dots:
        shapes.append(dots())
    # Up поднимает крайний столбец кожи на 10: охват по z становится 0..10.
    ms = common.morph_set(common.morph("Up", "body", common.columns(NX, NY, (5,)),
                                       [(0.0, 0.0, 10.0)]))
    return common.bench(tmpdir, common.model(*shapes), ms, **overrides)


class TestFraming(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bench = build(self.tmp.name)

    def assertFrame(self, centre, half, places=5):
        got_centre, got_half = self.bench.framing()
        self.assertIsInstance(got_centre, np.ndarray)
        self.assertIsInstance(got_half, float)
        self.assertTrue(np.allclose(got_centre, centre, atol=1e-5), (got_centre, centre))
        self.assertAlmostEqual(got_half, half, places=places)
        self.assertEqual(self.bench.view.frame_half, got_half)

    def test_whole_model_front(self):
        """Спереди (yaw 0): вправо — ось X, вверх — Z. Охват x 0..5 даёт |x| ≤ 2.5,
        z 0..1 даёт |z| ≤ 0.5 — полуразмах 2.5, центр — середина охвата."""
        self.bench.preset("front")
        self.assertFrame(WHOLE_CENTRE, 2.5)

    def test_side_view_uses_camera_axes(self):
        """Сбоку (yaw 90): вправо — ось Y, y 0..3 даёт 1.5; глубина (X) в кадр не входит.
        Полуразмах 2.5 здесь — это кадр в мировых осях, а не в осях камеры."""
        self.bench.look(90.0, 0.0)
        self.assertFrame(WHOLE_CENTRE, 1.5)
        self.bench.look(180.0, 0.0)
        self.assertFrame(WHOLE_CENTRE, 2.5)

    def test_only_visible_shapes(self):
        """Скрытая часть в кадр не входит: одна оболочка — центр (1.5,1.5,1), полуразмах 1.5;
        одна кожа — центр (2.5,1.5,0), полуразмах 2.5."""
        self.bench.preset("front")
        self.bench.only(["fur"])
        self.assertFrame(FUR_CENTRE, 1.5)
        self.bench.show_all()
        self.bench.hide("fur")
        self.assertFrame((2.5, 1.5, 0.0), 2.5)
        self.bench.show("fur")
        self.assertFrame(WHOLE_CENTRE, 2.5)

    def test_sliders_change_frame(self):
        """Ползунок Up на 1: охват по z 0..10, центр z = 5, полуразмах 5 (по вертикали).
        После сброса — прежний кадр."""
        self.bench.preset("front")
        self.bench.set_slider("Up", 1.0)
        self.assertFrame((2.5, 1.5, 5.0), 5.0)
        self.bench.set_slider("Up", 0.5)
        self.assertFrame((2.5, 1.5, 2.5), 2.5)
        self.bench.reset_sliders()
        self.assertFrame(WHOLE_CENTRE, 2.5)

    def test_focus_overrides_centre_and_half(self):
        """Наведение подменяет кадр сферой цели с запасом focusPadding из настроек."""
        self.bench.preset("front")
        self.bench.focus_shape("fur")
        self.assertFrame(FUR_CENTRE, math.sqrt(4.5) * 1.25)
        self.bench.look(90.0, 0.0)
        self.assertFrame(FUR_CENTRE, math.sqrt(4.5) * 1.25)
        self.bench.focus_all()
        self.assertFrame(WHOLE_CENTRE, 1.5)

    def test_focus_padding_from_config(self):
        bench = build(self.tmp.name, focusPadding=2.0)
        bench.focus_shape("fur")
        _, half = bench.framing()
        self.assertAlmostEqual(half, math.sqrt(4.5) * 2.0, places=5)

    def test_pan_shifts_centre(self):
        """Панорама (1, 2) — вправо и вверх в единицах модели — сдвигает центр вдоль осей
        экрана: спереди вправо — это -X, вверх — +Z; сбоку вправо — +Y."""
        self.bench.preset("front")
        self.bench.pan(1.0, 2.0)
        self.assertFrame((3.5, 1.5, -1.5), 2.5)
        self.bench.look(90.0, 0.0)
        self.assertFrame((2.5, 0.5, -1.5), 1.5)
        self.bench.pan(0.0, 0.0)
        self.assertFrame(WHOLE_CENTRE, 1.5)

    def test_all_hidden(self):
        self.bench.only([])
        with self.assertRaises(RuntimeError):
            self.bench.framing()
        self.bench.only(["ghost"])
        with self.assertRaises(RuntimeError):
            self.bench.framing()

    def test_shape_without_triangles_does_not_count(self):
        """«Точки» в модели есть (охват модели их видит), а в кадре их нет."""
        bench = build(self.tmp.name, with_dots=True)
        self.assertEqual(bench.summary()["bounds"]["max"], [100.0, 100.0, 100.0])
        bench.preset("front")
        centre, half = bench.framing()
        self.assertTrue(np.allclose(centre, WHOLE_CENTRE, atol=1e-5), centre)
        self.assertAlmostEqual(half, 2.5, places=5)
        bench.only(["dots"])
        with self.assertRaises(RuntimeError):
            bench.framing()

    def test_requires_open(self):
        bench = common.MorphBench(common.config(self.tmp.name))
        with self.assertRaises(RuntimeError):
            bench.framing()


if __name__ == "__main__":
    common.main()
