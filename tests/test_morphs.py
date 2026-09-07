# -*- coding: utf-8 -*-
"""Морфы в памяти: пустой ползунок, объявленный-но-отсутствующий, применение с долей
и с номерами вершин за пределами меша.

Пустой морф — тихая поломка: он есть в файле, принимает значение и читается обратно тем же
числом, но не двигает ни одной вершины. Здесь проверяется, что верстак его видит, отличает
от отсутствующего вовсе и что ни один расчёт на нём не падает. Номера вершин за пределами
меша — вторая тихая поломка: файл морфов собран под другой меш; верстак обязан обрезать
такие номера, а не падать посреди отчёта.
"""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench import Morph  # noqa: E402


class TestEmptyMorph(unittest.TestCase):
    """Морф без единой вершины."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.body = common.grid("body", 3, 3)
        self.empty = common.empty_morph("Empty", "body")
        self.up = common.morph("Up", "body", [4], [(0.0, 0.0, 1.0)])
        self.ms = common.morph_set(self.empty, self.up)
        self.bench = common.bench(self.tmp.name, common.model(self.body), self.ms)

    def test_flags_and_measures(self):
        """Пустой морф так и представляется: ноль вершин, нулевые сдвиги, нет области."""
        self.assertTrue(self.empty.is_empty)
        self.assertEqual(self.empty.vertex_count, 0)
        self.assertEqual(self.empty.max_shift, 0.0)
        self.assertEqual(self.empty.mean_shift, 0.0)
        self.assertEqual(self.empty.lengths().shape, (0,))
        self.assertIsNone(self.empty.region(self.body))
        self.assertFalse(self.up.is_empty)

    def test_apply_returns_same_vertices(self):
        """Применение пустого морфа ничего не меняет и не плодит копий."""
        out = self.empty.apply(self.body.verts, 1.0)
        self.assertIs(out, self.body.verts)
        self.assertTrue(np.array_equal(out, self.body.verts))

    def test_listed_as_empty(self):
        """Пустой морф попадает в перечень пустых, рабочий — нет."""
        self.assertEqual([m.name for m in self.ms.empty()], ["Empty"])
        rows = self.bench.empty_morphs()
        self.assertEqual(rows, [{"shape": "body", "morph": "Empty", "vertices": 0,
                                 "maxShift": 0.0, "meanShift": 0.0, "bounds": None}])
        stats = common.by_key(self.bench.morph_stats(), "morph")
        self.assertEqual(stats["Up"]["vertices"], 1)
        self.assertEqual(stats["Up"]["maxShift"], 1.0)
        self.assertEqual(stats["Up"]["bounds"], {"min": [1.0, 1.0, 0.0], "max": [1.0, 1.0, 0.0]})

    def test_nothing_crashes_on_empty(self):
        """Ни один разбор не падает на пустом морфе: растяжение и наведение его не считают,
        раскраска даёт нули, слои — отсутствие."""
        self.assertIsNone(self.bench.analyzer.edge_strain("body", "Empty"))
        self.assertIsNone(self.bench.analyzer.strain("body", "Empty"))
        self.assertEqual([r["morph"] for r in self.bench.strain()], ["Up"])
        self.assertTrue(np.all(self.bench.morph_key("body", "Empty") == 0))
        self.assertTrue(np.all(self.bench.strain_key("body", "Empty") == 0))
        self.assertEqual(self.bench.morph_bones("body", "Empty"), [])
        self.assertEqual(self.bench.bones_left_behind("body", "Empty"), [])
        with self.assertRaises(KeyError):
            self.bench.focus_morph("Empty")
        self.assertEqual([t["name"] for t in self.bench.focus_targets()["morphs"]], ["Up"])

    def test_missing_morphs(self):
        """Объявленный, но отсутствующий ползунок называется по имени; существующие — даже
        пустые — не трогаются; порядок запроса сохраняется."""
        self.assertEqual(self.bench.missing_morphs(["Up", "Ghost", "Empty", "Other"]),
                         ["Ghost", "Other"])
        self.assertEqual(self.bench.missing_morphs([]), [])
        self.assertEqual(self.bench.analyzer.declared_but_absent(["Empty"]), [])


class TestApply(unittest.TestCase):
    """Morph.apply: доля, неприкосновенность исходника, номера за пределами меша."""

    def setUp(self):
        self.verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float32)
        self.m = common.morph("Up", "body", [1, 3], [(0.0, 0.0, 2.0), (1.0, 0.0, 0.0)])

    def test_amount(self):
        """Смещение умножается на долю; нетронутые вершины остаются на месте."""
        out = self.m.apply(self.verts, 0.5)
        self.assertTrue(np.allclose(out[1], [1, 0, 1]))
        self.assertTrue(np.allclose(out[3], [1.5, 1, 0]))
        self.assertTrue(np.array_equal(out[[0, 2]], self.verts[[0, 2]]))
        back = self.m.apply(self.verts, -1.0)
        self.assertTrue(np.allclose(back[1], [1, 0, -2]))

    def test_source_untouched(self):
        """Исходное облако не меняется: apply возвращает копию."""
        before = self.verts.copy()
        out = self.m.apply(self.verts, 1.0)
        self.assertIsNot(out, self.verts)
        self.assertTrue(np.array_equal(self.verts, before))

    def test_zero_amount(self):
        """Нулевая доля — те же вершины без копирования."""
        self.assertIs(self.m.apply(self.verts, 0.0), self.verts)

    def test_indices_beyond_mesh_are_clipped(self):
        """Морф, собранный под меш побольше: лишние номера обрезаются, остальные работают."""
        m = common.morph("Big", "body", [1, 99, 7], [(0.0, 0.0, 1.0)])
        out = m.apply(self.verts, 1.0)
        self.assertEqual(out.shape, self.verts.shape)
        self.assertTrue(np.allclose(out[1], [1, 0, 1]))
        self.assertTrue(np.array_equal(out[[0, 2, 3]], self.verts[[0, 2, 3]]))


class TestOutOfRangeAcrossFacade(unittest.TestCase):
    """Файл морфов под другой меш: номера вершин за пределами части. Все разборы обязаны
    обрезать их, как это делает apply, — падение посреди отчёта хуже неверной строки."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        nx = ny = 4
        body = common.grid("body", nx, ny, bones={
            "Hand": common.bone("Hand", common.columns(nx, ny, (0, 1))),
            "Finger": common.bone("Finger", common.columns(nx, ny, (2, 3)))})
        fur = common.grid("fur", nx, ny, z=1.0)
        # Вершины 2, 3 существуют, 40 и 99 — нет.
        self.m = common.morph("Up", "body", [2, 3, 40, 99], [(0.0, 0.0, 1.0)])
        self.bench = common.bench(self.tmp.name, common.model(body, fur), common.morph_set(self.m))

    def test_keys_and_bindings(self):
        key = self.bench.morph_key("body", "Up")
        self.assertEqual(key.shape, (16,))
        self.assertTrue(np.all(key[[2, 3]] == 1.0))
        self.assertEqual(float(key.sum()), 2.0)
        self.assertEqual(self.bench.morph_bones("body", "Up"), [{"bone": "Finger", "share": 1.0}])
        self.assertEqual(self.bench.bones_left_behind("body", "Up"),
                         [{"bone": "Finger", "leftBehind": 0.75}])

    def test_strain_layers_focus_deformed(self):
        self.assertEqual(len(self.bench.strain()), 1)
        self.assertTrue(np.isfinite(self.bench.strain_key("body", "Up")).all())
        rows = common.by_key(self.bench.layers("Up"), "follower")
        self.assertEqual(rows["fur"]["expectedMax"], 1.0)
        self.assertEqual(rows["fur"]["contact"], 0.125)
        self.bench.focus_morph("Up")
        self.assertEqual(self.bench.view_state()["focus"]["centre"], [2.5, 0.0, 0.0])
        self.assertEqual([t["name"] for t in self.bench.focus_targets()["morphs"]], ["Up"])
        self.bench.set_slider("Up", 1.0)
        self.assertTrue(np.allclose(self.bench.deformed("body")[[2, 3], 2], 1.0))

    def test_morph_stats_survive(self):
        """Карточка морфа — первое, что спрашивают о паре «меш + морфы». Она обязана
        показать морф с лишними номерами, а не упасть с IndexError."""
        try:
            rows = self.bench.morph_stats()
        except IndexError as e:
            self.fail("morph_stats упал на номере вершины за пределами меша: %s" % e)
        self.assertEqual(rows[0]["morph"], "Up")
        self.assertEqual(rows[0]["bounds"], {"min": [2.0, 0.0, 0.0], "max": [3.0, 0.0, 0.0]})


class TestMorphSetLookup(unittest.TestCase):
    """Справочные методы набора: имена, части, поиск."""

    def test_names_and_lookup(self):
        ms = common.morph_set(
            common.morph("B", "body", [0], [(1.0, 0.0, 0.0)]),
            common.morph("A", "body", [0], [(1.0, 0.0, 0.0)]),
            common.morph("B", "fur", [0], [(1.0, 0.0, 0.0)]),
            common.morph("C", "fur", [0], [(1.0, 0.0, 0.0)]))
        self.assertEqual(ms.names(), ["A", "B", "C"])
        self.assertEqual(ms.shape_names(), ["body", "fur"])
        self.assertIsNone(ms.get("body", "C"))
        self.assertIsNone(ms.get("head", "A"))
        self.assertIsInstance(ms.get("fur", "B"), Morph)
        self.assertEqual(sorted(ms.for_morph("B")), ["body", "fur"])
        self.assertEqual(list(ms.for_morph("A")), ["body"])
        self.assertEqual(ms.for_morph("Z"), {})
        self.assertEqual(ms.empty(), [])


if __name__ == "__main__":
    common.main()
