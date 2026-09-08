# -*- coding: utf-8 -*-
"""Страница со смотрелкой: собирается из бенча в памяти и ни к чему снаружи не обращается.

Страница обязана быть самодостаточной — открываться с диска без сети, — поэтому в ней не
может быть ни одной ссылки на http:// или https://. Если слоя `presenters.web` ещё нет,
набор пропускается: его пишут отдельно, и отсутствие модуля — не сбой ядра.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

try:
    from presenters.web import WebPage
except ImportError as e:  # noqa: N816
    WebPage = None
    IMPORT_ERROR = e


@unittest.skipIf(WebPage is None, "presenters/web.py ещё нет: %s" % (
    IMPORT_ERROR if WebPage is None else ""))
class TestWebPage(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bench = common.bench(self.tmp.name, common.sample_model(), common.sample_morphs())
        self.html = WebPage(self.bench).html()

    def test_is_a_page_with_canvas(self):
        self.assertIsInstance(self.html, str)
        self.assertIn("<canvas", self.html)

    def test_names_of_shapes_and_morphs(self):
        """Части и ползунки видны на странице по имени — иначе нечем управлять."""
        for name in ("body", "fur"):
            self.assertIn(name, self.html, name)
        for name in ("Up", "Wide", "Tip"):
            self.assertIn(name, self.html, name)

    def test_no_external_links(self):
        """Ни одной ссылки наружу: страница обязана открываться без сети."""
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)

    def test_payload_matches_facade(self):
        """Вложенные в страницу числа — те же, что отдаёт фасад: вершины и признак кости
        побитно, смещения int16 × множитель и растяжение uint8 × максимум — в пределах
        кванта, состояние показа — тем же словарём. Иначе страница показывала бы не то тело."""
        import base64
        import numpy as np

        def unpack(b64, dtype):
            return np.frombuffer(base64.b64decode(b64), dtype=dtype)

        def index_dtype(kind):
            return "<u2" if kind == "u16" else "<u4"

        payload = WebPage(self.bench).payload()
        counts = {}
        for shape in payload["shapes"]:
            name = shape["name"]
            counts[name] = shape["vertexCount"]
            np.testing.assert_array_equal(unpack(shape["boneKey"], "<i2"), self.bench.bone_key(name))
            np.testing.assert_array_equal(unpack(shape["vertices"], "<f4").reshape(-1, 3),
                                          self.bench.model.shape(name).verts)
        self.assertTrue(payload["deltas"], "в образце есть морфы - смещения должны быть вложены")
        for morph, per_shape in payload["deltas"].items():
            for name, d in per_shape.items():
                raw = self.bench.morph_deltas(name, morph)
                keep = raw["indices"] < counts[name]
                idx = unpack(d["indices"], index_dtype(d["indexType"]))
                q = unpack(d["offsets"], "<i2").reshape(-1, 3).astype(np.float32)
                np.testing.assert_array_equal(idx, raw["indices"][keep])
                err = float(np.abs(q * d["scale"] - raw["offsets"][keep]).max())
                self.assertLessEqual(err, d["scale"] / 2 + 1e-6, (morph, name))
        for morph, per_shape in payload["strain"].items():
            for name, s in per_shape.items():
                full = self.bench.strain_key(name, morph)
                idx = unpack(s["indices"], index_dtype(s["indexType"]))
                values = unpack(s["values"], "u1").astype(np.float32) * s["max"] / 255.0
                self.assertEqual(sorted(idx.tolist()), np.nonzero(full > 0)[0].tolist())
                self.assertLessEqual(float(np.abs(values - full[idx]).max()), s["max"] / 510 + 1e-6)
        # Страница строит кадр по этим числам, поэтому получает их без округления.
        self.assertEqual(payload["view"], self.bench.view_state(precise=True))
        self.assertEqual(payload["sliders"], self.bench.sliders())

    def test_targets_include_command_line_focus(self):
        """Наведение по подстроке из командной строки нет среди целей, но ядро сосчитало
        его сферу — страница получает её под тем же именем и может выбрать снова."""
        self.bench.focus_bone("Han")     # подстрока, объединяющая кости
        targets = WebPage(self.bench).payload()["targets"]
        hit = [t for t in targets["bones"] if t["name"] == "Han"]
        self.assertEqual(len(hit), 1)
        focus = self.bench.view_state()["focus"]
        self.assertEqual([round(x, 2) for x in hit[0]["centre"]], focus["centre"])
        self.assertEqual(round(hit[0]["radius"], 2), focus["radius"])

    def test_save(self):
        path = Path(self.tmp.name) / "out" / "page.html"
        saved = Path(WebPage(self.bench).save(path))
        self.assertTrue(saved.is_file())
        text = saved.read_text(encoding="utf-8")
        self.assertIn("<canvas", text)
        self.assertNotIn("https://", text)


def _unpack(b64, dtype):
    import base64
    import numpy as np
    return np.frombuffer(base64.b64decode(b64), dtype=dtype)


def _index_dtype(kind):
    return "<u2" if kind == "u16" else "<u4"


def _rig(with_bumper: bool = False):
    """Скелет в памяти помощниками из test_colliders: одна кость с одной капсулой и,
    по просьбе, бампер. Путь у него - memory.nif, как у всех фигур в памяти."""
    from test_colliders import body, cap, rig
    bumper = body("Bump", cap("Bump", radius=25.0), kind="bhkSimpleShapePhantom") if with_bumper else None
    return rig(body("B", cap(radius=2.0)), bumper=bumper)


@unittest.skipIf(WebPage is None, "presenters/web.py ещё нет")
class TestWebPageColliders(unittest.TestCase):
    """Слой капсул: без скелета его в странице нет, со скелетом капсулы вложены целиком —
    теми же треугольниками, что отдаёт фасад, — а состояние слоя идёт из view_state()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bench = common.bench(self.tmp.name, common.sample_model(), common.sample_morphs())

    def test_without_skeleton(self):
        """Скелета нет — colliders None, имя скелета None, слой в состоянии выключен."""
        page = WebPage(self.bench)
        payload = page.payload()
        self.assertFalse(self.bench.has_skeleton())
        self.assertIsNone(payload["colliders"])
        self.assertIsNone(payload["names"]["skeleton"])
        self.assertFalse(payload["view"]["colliders"])
        self.assertFalse(payload["view"]["bumper"])
        # Раздел «Капсулы» панель строит по этому же признаку, поэтому в данных
        # страницы капсул нет вовсе.
        self.assertIn('"colliders":null', page.html())

    def test_with_skeleton_in_memory(self):
        """Капсулы в странице — те же вершины и треугольники, что у collider_mesh()."""
        import numpy as np
        self.bench.rig = _rig()
        payload = WebPage(self.bench).payload()
        verts, tris = self.bench.collider_mesh()
        got = payload["colliders"]
        self.assertIsNotNone(got)
        self.assertEqual(got["vertexCount"], verts.shape[0])
        np.testing.assert_array_equal(_unpack(got["vertices"], "<f4").reshape(-1, 3), verts)
        np.testing.assert_array_equal(
            _unpack(got["triangles"], _index_dtype(got["indexType"])).reshape(-1, 3), tris)
        self.assertIsNone(got["bumper"], "бампера в этом скелете нет")
        self.assertEqual(payload["names"]["skeleton"], "memory.nif")
        self.assertEqual(payload["summary"]["colliders"], 1)
        # Слой выключен, пока не попросили, и включается тем же методом фасада.
        self.assertFalse(payload["view"]["colliders"])
        self.bench.show_colliders(True)
        payload = WebPage(self.bench).payload()
        self.assertTrue(payload["view"]["colliders"])
        self.assertFalse(payload["view"]["bumper"])
        self.assertEqual(payload["view"], self.bench.view_state(precise=True))

    def test_bumper_is_packed_apart(self):
        """Цилиндр перемещения — отдельным куском, чтобы страница клала его по своему флагу."""
        self.bench.rig = _rig(with_bumper=True)
        got = WebPage(self.bench).payload()["colliders"]
        self.assertIsNotNone(got["bumper"])
        self.assertEqual(got["bumper"]["vertexCount"], self.bench.bumper_mesh()[0].shape[0])
        self.assertEqual(got["vertexCount"], self.bench.collider_mesh()[0].shape[0])

    def test_settings_carry_colour_and_opacity(self):
        """Цвет и прозрачность слоя — из тех же ключей настроек, что у растеризатора."""
        st = WebPage(self.bench).payload()["settings"]
        self.assertEqual(st["colliderColour"], [float(x) for x in self.bench.cfg["colliderColour"]])
        self.assertEqual(st["colliderOpacity"], float(self.bench.cfg["colliderOpacity"]))


if __name__ == "__main__":
    common.main()
