# -*- coding: utf-8 -*-
"""Слои и смежность: следует ли оболочка за кожей, и обязана ли она следовать вообще.

Кожа — плоская сетка 6×4; морф поднимает её правую половину (столбцы 3-5) на 2, а один
угол — на 3. Над сдвигаемой половиной в одной единице лежит оболочка A, над несдвигаемой —
B, далеко вверху (за пределами contactRadius) — C. Отсюда все ожидания считаются в уме:
у A каждая вершина стоит ровно над своей вершиной кожи на расстоянии 1; у B под ногами
ничего не двигается; у C под ногами вообще ничего нет.
"""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench.analysis import Analyzer, Proximity  # noqa: E402

NX, NY = 6, 4
MOVED_COLS = (3, 4, 5)
CORNER = 3 * NX + 5          # вершина (5, 3): единственная со сдвигом 3


def body_offsets(indices):
    """Сдвиг (0, 0, 2) у всех сдвигаемых вершин кожи, у угла — (0, 0, 3)."""
    return [(0.0, 0.0, 3.0 if int(i) == CORNER else 2.0) for i in indices]


def shell(name, cols, z):
    """Копия столбцов cols сетки кожи, поднятая на высоту z."""
    return common.grid(name, len(cols), NY, z=z, x0=float(cols[0]))


def under(cols):
    """Для вершин оболочки над столбцами cols — номера вершин кожи прямо под ними,
    в порядке вершин оболочки."""
    return np.array([iy * NX + c for iy in range(NY) for c in cols], dtype=np.int32)


def build(tmpdir, **overrides):
    body = common.grid("body", NX, NY)
    moved = common.columns(NX, NY, MOVED_COLS)
    fur_a, fur_b, fur_c = (shell("furA", MOVED_COLS, 1.0), shell("furB", (0, 1, 2), 1.0),
                           shell("furC", MOVED_COLS, 100.0))
    # У furA под каждой вершиной j лежит вершина кожи under(MOVED_COLS)[j]; копия морфа
    # повторяет сдвиг кожи в тех же местах.
    a_copy = [(0.0, 0.0, 3.0 if int(b) == CORNER else 2.0) for b in under(MOVED_COLS)]
    ms = common.morph_set(
        common.morph("Bulge", "body", moved, body_offsets(moved)),
        common.morph("Bulge", "furA", range(fur_a.vertex_count), a_copy),
        common.morph("Lone", "body", moved, body_offsets(moved)),
        common.morph("Own", "furA", [0], [(0.0, 1.0, 0.0)]),
        common.empty_morph("Lone", "furB"))
    return common.bench(tmpdir, common.model(body, fur_a, fur_b, fur_c), ms, **overrides)


class TestProximity(unittest.TestCase):
    """Кто под кем лежит — на примерах, где ответ виден глазом."""

    def test_small_example(self):
        base = [(0, 0, 0), (1, 0, 0), (-3, -3, -3)]
        follower = [(0, 0, 1), (10, 10, 10), (0.4, 0, 0), (0.6, 0, 0), (-3, -3, -2.5)]
        p = Proximity(np.array(follower, np.float32), np.array(base, np.float32), 1.5)
        self.assertEqual(p.nearest.tolist(), [0, -1, 0, 1, 2])
        self.assertTrue(np.allclose(p.distance[[0, 2, 3, 4]], [1.0, 0.4, 0.4, 0.5], atol=1e-6))
        self.assertTrue(np.isinf(p.distance[1]))
        self.assertEqual(p.covered.tolist(), [True, False, True, True, True])

    def test_neighbour_across_cell_boundary(self):
        """Поиск идёт по ячейкам в радиус; пара по разные стороны границы ячейки обязана
        находиться, иначе смежность зависела бы от того, где прошла сетка."""
        p = Proximity(np.array([[1.05, 0, 0]], np.float32), np.array([[0.95, 0, 0]], np.float32), 1.0)
        self.assertEqual(p.nearest.tolist(), [0])
        self.assertAlmostEqual(float(p.distance[0]), 0.1, places=5)

    def test_radius_is_inclusive_and_zero_disables(self):
        f = np.array([[0, 0, 1]], np.float32)
        b = np.array([[0, 0, 0]], np.float32)
        self.assertEqual(Proximity(f, b, 1.0).nearest.tolist(), [0])
        self.assertEqual(Proximity(f, b, 0.999).nearest.tolist(), [-1])
        self.assertEqual(Proximity(f, b, 0.0).nearest.tolist(), [-1])

    def test_empty_inputs(self):
        z = np.zeros((0, 3), np.float32)
        self.assertEqual(Proximity(z, np.ones((2, 3), np.float32), 1.0).nearest.shape, (0,))
        p = Proximity(np.ones((2, 3), np.float32), z, 1.0)
        self.assertEqual(p.nearest.tolist(), [-1, -1])
        self.assertTrue(np.isinf(p.distance).all())


class TestLayers(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bench = build(self.tmp.name)
        self.an = self.bench.analyzer

    def test_proximity_under_shells(self):
        """Под каждой вершиной A — своя вершина кожи на расстоянии ровно 1; под C нет ничего."""
        p = self.an.proximity("furA", "body")
        self.assertEqual(p.nearest.tolist(), under(MOVED_COLS).tolist())
        self.assertTrue(np.all(p.distance == 1.0))
        self.assertTrue(p.covered.all())
        c = self.an.proximity("furC", "body")
        self.assertTrue(np.all(c.nearest == -1))
        self.assertFalse(c.covered.any())
        self.assertIs(p, self.an.proximity("furA", "body"))

    def test_shell_over_moved_half(self):
        """A лежит над сдвигом целиком: contact 1, смежна, должна сдвинуться на 3 (под ней
        и угол), своя копия морфа даёт ratio 1 и missing False."""
        row = common.by_key(self.bench.layers("Bulge"), "follower")["furA"]
        self.assertEqual(row["contact"], 1.0)
        self.assertTrue(row["adjacent"])
        self.assertEqual(row["expectedMax"], 3.0)
        self.assertEqual(row["baseMax"], 3.0)
        self.assertEqual(row["followerMax"], 3.0)
        self.assertEqual(row["ratio"], 1.0)
        self.assertFalse(row["missing"])
        self.assertEqual(row["base"], "body")
        self.assertEqual(row["morph"], "Bulge")

    def test_shell_over_still_half(self):
        """B стоит над несдвигаемой половиной: под ногами кожа есть, но не двигается."""
        row = common.by_key(self.bench.layers("Bulge"), "follower")["furB"]
        self.assertEqual(row["contact"], 0.0)
        self.assertFalse(row["adjacent"])
        self.assertEqual(row["expectedMax"], 0.0)
        self.assertTrue(row["missing"])

    def test_shell_far_away(self):
        """C дальше contactRadius от кожи: ни одной вершины над сдвигом."""
        row = common.by_key(self.bench.layers("Bulge"), "follower")["furC"]
        self.assertEqual(row["contact"], 0.0)
        self.assertFalse(row["adjacent"])
        self.assertTrue(row["missing"])

    def test_shell_without_own_copy(self):
        """Lone есть у кожи и нет у A: A смежна и обязана следовать, но не следует."""
        row = common.by_key(self.bench.layers("Lone"), "follower")["furA"]
        self.assertTrue(row["adjacent"])
        self.assertTrue(row["missing"])
        self.assertEqual(row["followerMax"], 0.0)
        self.assertEqual(row["ratio"], 0.0)
        self.assertEqual(row["expectedMax"], 3.0)

    def test_empty_follower_copy_counts_as_missing(self):
        """Пустая копия морфа у оболочки — то же, что её отсутствие."""
        row = common.by_key(self.bench.layers("Lone"), "follower")["furB"]
        self.assertTrue(row["missing"])
        self.assertEqual(row["followerMax"], 0.0)

    def test_only_adjacent(self):
        """С only_adjacent остаётся одна A; без него перечислены все оболочки, кожа — нет."""
        self.assertEqual([r["follower"] for r in self.bench.layers("Bulge", only_adjacent=True)],
                         ["furA"])
        self.assertEqual([r["follower"] for r in self.bench.layers("Bulge")],
                         ["furA", "furB", "furC"])

    def test_base_without_morph(self):
        """Морф есть только у оболочки: у кожи сдвига нет, ничего не двигается, ratio 0."""
        rows = common.by_key(self.bench.layers("Own"), "follower")
        self.assertEqual(rows["furA"]["baseMax"], 0.0)
        self.assertEqual(rows["furA"]["followerMax"], 1.0)
        self.assertEqual(rows["furA"]["ratio"], 0.0)
        self.assertFalse(rows["furA"]["missing"])
        self.assertEqual(rows["furA"]["contact"], 0.0)
        self.assertFalse(rows["furA"]["adjacent"])

    def test_base_absent_from_mesh(self):
        """Базовой части в меше нет: смежность не считалась — None, а не ложь."""
        rows = self.bench.layers("Bulge", base="skin")
        self.assertEqual([r["follower"] for r in rows], ["body", "furA", "furB", "furC"])
        for r in rows:
            self.assertIsNone(r["contact"])
            self.assertIsNone(r["adjacent"])
            self.assertIsNone(r["expectedMax"])
        self.assertEqual(self.bench.layers("Bulge", base="skin", only_adjacent=True), [])

    def test_facade_matches_analyzer(self):
        """Фасад отдаёт as_dict() тех же LayerStat, что даёт Analyzer с настройками из Config."""
        an = Analyzer(self.bench.model, self.bench.morph_set, 6.0, 0.02)
        for morph in ("Bulge", "Lone"):
            for adj in (False, True):
                self.assertEqual(self.bench.layers(morph, "body", adj),
                                 [s.as_dict() for s in an.layers(morph, "body", adj)])


class TestExpectedMaxIsUnderTheShell(unittest.TestCase):
    """expectedMax — сдвиг кожи прямо под оболочкой, а не наибольший сдвиг всей кожи."""

    def test_partial_cover(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = common.grid("body", NX, NY)
            moved = common.columns(NX, NY, MOVED_COLS)
            narrow = shell("furN", (3, 4), 1.0)       # угол со сдвигом 3 — не под ней
            ms = common.morph_set(common.morph("Bulge", "body", moved, body_offsets(moved)))
            row = common.bench(tmp, common.model(body, narrow), ms).layers("Bulge")[0]
            self.assertEqual(row["contact"], 1.0)
            self.assertEqual(row["baseMax"], 3.0)
            self.assertEqual(row["expectedMax"], 2.0)


class TestConfigReachesAnalyzer(unittest.TestCase):
    """contactRadius и minContact из morphbench.json доезжают до Analyzer через фасад."""

    def test_contact_radius(self):
        """Радиус 0.5 меньше расстояния до кожи (1): A перестаёт быть смежной."""
        with tempfile.TemporaryDirectory() as tmp:
            bench = build(tmp, contactRadius=0.5)
            self.assertEqual(bench.analyzer.contact_radius, 0.5)
            self.assertEqual(bench.analyzer.min_contact, 0.02)
            row = common.by_key(bench.layers("Bulge"), "follower")["furA"]
            self.assertEqual(row["contact"], 0.0)
            self.assertFalse(row["adjacent"])
            self.assertEqual(bench.layers("Bulge", only_adjacent=True), [])
        with tempfile.TemporaryDirectory() as tmp:
            bench = build(tmp, contactRadius=1.0)
            self.assertEqual(common.by_key(bench.layers("Bulge"), "follower")["furA"]["contact"], 1.0)

    def test_min_contact(self):
        """Оболочка над столбцами 2-3 стоит над сдвигом наполовину: contact 0.5. Порог 0.6
        делает её несмежной, порог 0.4 — смежной."""
        for min_contact, adjacent in ((0.6, False), (0.4, True), (0.5, True)):
            with tempfile.TemporaryDirectory() as tmp:
                body = common.grid("body", NX, NY)
                moved = common.columns(NX, NY, MOVED_COLS)
                half = shell("furD", (2, 3), 1.0)
                ms = common.morph_set(common.morph("Bulge", "body", moved, body_offsets(moved)))
                bench = common.bench(tmp, common.model(body, half), ms, minContact=min_contact)
                self.assertEqual(bench.analyzer.min_contact, min_contact)
                row = bench.layers("Bulge")[0]
                self.assertEqual(row["contact"], 0.5)
                self.assertEqual(row["adjacent"], adjacent, min_contact)
                self.assertEqual(len(bench.layers("Bulge", only_adjacent=True)), 1 if adjacent else 0)


if __name__ == "__main__":
    common.main()
