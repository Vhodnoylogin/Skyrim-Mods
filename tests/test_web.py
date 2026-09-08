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


if __name__ == "__main__":
    common.main()
