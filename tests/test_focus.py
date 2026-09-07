# -*- coding: utf-8 -*-
"""Наведение камеры: смотреть на кость, морф или часть — числами, центром и радиусом.

Тело — кожа 4×4 на z=0 и оболочка 4×4 на z=1; кости лежат по столбцам, поэтому охват каждой
цели считается в уме. Ловит: подстроку, сработавшую вместо точного имени (в кадр попадает
«NPC Handle» вместо «NPC Hand»), наведение, пережившее открытие другого меша, запас кадра,
не взятый из настроек, и типы numpy, просочившиеся в as_dict().
"""
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench.model import sphere_of  # noqa: E402
from morphbench.view import ViewState  # noqa: E402

NX = NY = 4


def build(tmpdir, **overrides):
    body = common.grid("body", NX, NY, bones={
        "NPC Hand": common.bone("NPC Hand", common.columns(NX, NY, (0, 1))),
        "NPC Finger00": common.bone("NPC Finger00", common.columns(NX, NY, (2,))),
        "NPC Finger01": common.bone("NPC Finger01", common.columns(NX, NY, (3,)))})
    fur = common.grid("fur", NX, NY, z=1.0, bones={
        "NPC Hand": common.bone("NPC Hand", common.columns(NX, NY, (0, 1))),
        "NPC Handle": common.bone("NPC Handle", common.columns(NX, NY, (2, 3)))})
    fingers = common.columns(NX, NY, (2, 3))
    ms = common.morph_set(common.morph("Up", "body", fingers, [(0.0, 0.0, 1.0)]),
                          common.morph("Up", "fur", fingers, [(0.0, 0.0, 0.5)]),
                          common.empty_morph("Empty", "body"))
    return common.bench(tmpdir, common.model(body, fur), ms, **overrides)


class TestSphere(unittest.TestCase):

    def test_known_points(self):
        """Центр — середина охвата, радиус — до самой дальней точки."""
        centre, radius = sphere_of(np.array([[0, 0, 0], [2, 0, 0], [0, 4, 0]], np.float32))
        self.assertEqual(centre.tolist(), [1.0, 2.0, 0.0])
        self.assertAlmostEqual(radius, math.sqrt(5.0), places=6)

    def test_degenerate(self):
        centre, radius = sphere_of(np.zeros((0, 3), np.float32))
        self.assertEqual(centre.tolist(), [0.0, 0.0, 0.0])
        self.assertEqual(radius, 0.0)
        centre, radius = sphere_of([[3.0, -1.0, 2.0]])
        self.assertEqual(centre.tolist(), [3.0, -1.0, 2.0])
        self.assertEqual(radius, 0.0)


class TestFocus(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bench = build(self.tmp.name)

    def focus(self):
        return self.bench.view_state()["focus"]

    def assertSphere(self, focus, centre, radius, name):
        self.assertEqual(focus["name"], name)
        self.assertEqual(focus["centre"], [round(c, 2) for c in centre])
        self.assertEqual(focus["radius"], round(radius, 2))

    def test_bone_exact(self):
        """Кость по точному имени: столбец 2 кожи — x=2, y=0..3."""
        state = self.bench.focus_bone("NPC Finger00")
        self.assertSphere(state["focus"], (2.0, 1.5, 0.0), 1.5, "bone:NPC Finger00")
        self.assertEqual(state, self.bench.view_state())
        self.assertTrue(self.bench.view.has_focus)

    def test_bone_substring_joins_bones(self):
        """По подстроке без учёта регистра собираются оба пальца: столбцы 2-3."""
        focus = self.bench.focus_bone("finger")["focus"]
        self.assertSphere(focus, (2.5, 1.5, 0.0), math.sqrt(2.5), "bone:finger")

    def test_exact_name_wins_over_substring(self):
        """«NPC Hand» есть точно — значит «NPC Handle» в кадр не попадает. Обе части:
        кожа z=0 и оболочка z=1, столбцы 0-1."""
        focus = self.bench.focus_bone("NPC Hand")["focus"]
        self.assertSphere(focus, (0.5, 1.5, 0.5), math.sqrt(2.75), "bone:NPC Hand")
        # А по подстроке «hand» — уже и Handle: вся оболочка плюс половина кожи.
        focus = self.bench.focus_bone("hand")["focus"]
        self.assertSphere(focus, (1.5, 1.5, 0.5), math.sqrt(4.75), "bone:hand")

    def test_bone_limited_to_shape(self):
        focus = self.bench.focus_bone("NPC Hand", shape="fur")["focus"]
        self.assertSphere(focus, (0.5, 1.5, 1.0), math.sqrt(2.5), "bone:NPC Hand")

    def test_bone_unknown(self):
        with self.assertRaises(KeyError):
            self.bench.focus_bone("Tail")
        with self.assertRaises(KeyError):
            self.bench.focus_bone("NPC Hand", shape="head")
        self.assertIsNone(self.focus())

    def test_morph(self):
        """Область морфа по всем частям: столбцы 2-3 кожи и оболочки, по исходным
        координатам, без учёта сдвига."""
        focus = self.bench.focus_morph("Up")["focus"]
        self.assertSphere(focus, (2.5, 1.5, 0.5), math.sqrt(2.75), "morph:Up")
        with self.assertRaises(KeyError):
            self.bench.focus_morph("Ghost")
        with self.assertRaises(KeyError):
            self.bench.focus_morph("Empty")

    def test_shape(self):
        focus = self.bench.focus_shape("fur")["focus"]
        self.assertSphere(focus, (1.5, 1.5, 1.0), math.sqrt(4.5), "shape:fur")
        with self.assertRaises(KeyError):
            self.bench.focus_shape("head")

    def test_focus_all_resets(self):
        self.bench.focus_shape("fur")
        self.assertIsNotNone(self.focus())
        state = self.bench.focus_all()
        self.assertIsNone(state["focus"])
        self.assertFalse(self.bench.view.has_focus)

    def test_framing(self):
        """Без наведения кадр — то, что передал рисующий слой; с наведением — сфера цели
        с запасом focusPadding из настроек (по умолчанию 1.25)."""
        centre, half = self.bench.view.framing([9.0, 9.0, 9.0], 42.0)
        self.assertEqual(centre.tolist(), [9.0, 9.0, 9.0])
        self.assertEqual(half, 42.0)
        self.bench.focus_shape("fur")
        centre, half = self.bench.view.framing([9.0, 9.0, 9.0], 42.0)
        self.assertTrue(np.allclose(centre, [1.5, 1.5, 1.0]))
        self.assertAlmostEqual(half, math.sqrt(4.5) * 1.25, places=5)
        self.bench.focus_all()
        self.assertEqual(self.bench.view.framing([1.0, 2.0, 3.0], 4.0)[1], 4.0)

    def test_padding_from_config(self):
        bench = build(self.tmp.name, focusPadding=2.0)
        bench.focus_shape("fur")
        self.assertAlmostEqual(bench.view.framing([0, 0, 0], 1.0)[1], math.sqrt(4.5) * 2.0, places=5)

    def test_as_dict_rounded_and_plain(self):
        """Центр и радиус округлены до сотых, типы — обычные, json их принимает."""
        self.bench.focus_bone("finger")
        focus = self.focus()
        self.assertEqual(set(focus), {"name", "centre", "radius"})
        self.assertEqual(focus["centre"], [2.5, 1.5, 0.0])
        self.assertEqual(focus["radius"], 1.58)
        self.assertTrue(common.is_plain(focus), focus)
        json.dumps(self.bench.view_state())

    def test_radius_floor(self):
        """Наведение на точку не даёт нулевой сферы: радиус не меньше 0.001."""
        self.bench.view.focus_on([1.0, 1.0, 1.0], 0.0, "point")
        self.assertEqual(self.bench.view.focus_radius, 1e-3)

    def test_attach_resets_focus(self):
        self.bench.focus_shape("fur")
        self.bench.attach(self.bench.model, self.bench.morph_set)
        self.assertIsNone(self.focus())
        self.bench.focus_shape("fur")
        self.bench.attach(self.bench.model, None)
        self.assertIsNone(self.focus())

    def test_open_resets_focus(self):
        """open() тоже сбрасывает наведение; нужен настоящий меш — пишется PyNifly."""
        pynifly = common.load_pynifly(self.bench.cfg)
        nif = common.write_nif(pynifly, Path(self.tmp.name) / "tiny.nif", {"body": {
            "verts": [(0, 0, 0), (1, 0, 0), (0, 1, 0)], "tris": [(0, 1, 2)],
            "uvs": [(0, 0), (1, 0), (0, 1)], "normals": [(0, 0, 1)] * 3}})
        self.bench.focus_shape("fur")
        summary = self.bench.open(nif)
        self.assertIsNone(self.focus())
        self.assertEqual(summary["shapes"], 1)
        self.assertIsNone(summary["tri"])

    def test_targets(self):
        """Перечень целей: все кости (по всем частям), непустые морфы, все части; у каждой
        центр и радиус те же, что даст наведение на неё."""
        t = self.bench.focus_targets()
        self.assertEqual([b["name"] for b in t["bones"]],
                         ["NPC Finger00", "NPC Finger01", "NPC Hand", "NPC Handle"])
        self.assertEqual([m["name"] for m in t["morphs"]], ["Up"])
        self.assertEqual([s["name"] for s in t["shapes"]], ["body", "fur"])
        by_name = {kind: common.by_key(t[kind], "name") for kind in t}
        for bone in by_name["bones"]:
            focus = self.bench.focus_bone(bone)["focus"]
            self.assertEqual((focus["centre"], focus["radius"]),
                             (by_name["bones"][bone]["centre"], by_name["bones"][bone]["radius"]), bone)
        focus = self.bench.focus_morph("Up")["focus"]
        self.assertEqual((focus["centre"], focus["radius"]),
                         (by_name["morphs"]["Up"]["centre"], by_name["morphs"]["Up"]["radius"]))
        focus = self.bench.focus_shape("fur")["focus"]
        self.assertEqual((focus["centre"], focus["radius"]),
                         (by_name["shapes"]["fur"]["centre"], by_name["shapes"]["fur"]["radius"]))
        self.assertTrue(common.is_plain(t))

    def test_targets_without_morphs(self):
        bench = common.bench(self.tmp.name, self.bench.model, None)
        self.assertEqual(bench.focus_targets()["morphs"], [])


class TestViewStateAlone(unittest.TestCase):
    """ViewState без фасада: наведение — просто сфера, ей всё равно, что это."""

    def test_focus_on_and_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = ViewState(common.config(tmp, focusPadding=1.5))
            self.assertIsNone(view.as_dict()["focus"])
            view.focus_on((1.234567, -2.0, 0.0), 3.14159, "anything")
            self.assertEqual(view.as_dict()["focus"],
                             {"name": "anything", "centre": [1.23, -2.0, 0.0], "radius": 3.14})
            centre, half = view.framing((0, 0, 0), 100.0)
            self.assertTrue(np.allclose(centre, [1.234567, -2.0, 0.0]))
            self.assertAlmostEqual(half, 3.14159 * 1.5, places=5)
            view.focus_all()
            self.assertIsNone(view.as_dict()["focus"])
            self.assertEqual(view.framing((0, 0, 0), 100.0)[1], 100.0)


if __name__ == "__main__":
    common.main()
