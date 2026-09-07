# -*- coding: utf-8 -*-
"""Растяжение рёбер: числа, посчитанные вручную на сетке из двух треугольников.

Мера |после / до − 1| ловит «перчатку»: если морф двигает ладонь и не трогает пальцы, рёбра
между ними растягиваются во столько же раз, во сколько разъехались их концы. Здесь известны
и длины рёбер до, и сдвиг одной вершины, поэтому ожидаемое растяжение каждого ребра
выписано явно. Морф, двигающий часть целиком, обязан дать ноль: форма не изменилась.
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
from morphbench.analysis import Analyzer  # noqa: E402

# Квадрат из двух треугольников. Рёбра (по возрастанию пар): (0,1) (0,2) (1,2) (1,3) (2,3),
# длины 1, 1, √2, 1, 1.
VERTS = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float32)
TRIS = np.array([[0, 1, 2], [1, 3, 2]], dtype=np.int32)
EDGES = [[0, 1], [0, 2], [1, 2], [1, 3], [2, 3]]
SQRT2 = math.sqrt(2.0)


class TestStrainByHand(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.body = Shape("body", VERTS, TRIS, None, None, {})
        # Pull тянет вершину 3 на +1 по X: ребро (1,3) из 1 становится √2, ребро (2,3) — 2.
        # Shift двигает всё целиком на (3, -2, 5).
        self.ms = common.morph_set(
            common.morph("Pull", "body", [3], [(1.0, 0.0, 0.0)]),
            common.morph("Shift", "body", [0, 1, 2, 3], [(3.0, -2.0, 5.0)]),
            common.empty_morph("Empty", "body"))
        self.bench = common.bench(self.tmp.name, common.model(self.body), self.ms)
        self.an = self.bench.analyzer

    def test_edges_unique_and_sorted(self):
        """Рёбра части — без повторов, каждая пара по возрастанию; общее ребро двух
        треугольников считается один раз."""
        self.assertEqual(self.an.edges("body").tolist(), EDGES)
        self.assertIs(self.an.edges("body"), self.an.edges("body"))

    def test_edge_strain(self):
        """Растяжение по рёбрам: (1,3) → √2−1, (2,3) → 1, остальные — 0."""
        edges, strain = self.an.edge_strain("body", "Pull")
        self.assertEqual(edges.tolist(), EDGES)
        self.assertTrue(np.allclose(strain, [0, 0, 0, SQRT2 - 1, 1.0], atol=1e-6), strain)

    def test_vertex_strain(self):
        """У вершины — наибольшее растяжение её рёбер: 0, √2−1, 1, 1."""
        vs = self.an.vertex_strain("body", "Pull")
        self.assertTrue(np.allclose(vs, [0, SQRT2 - 1, 1.0, 1.0], atol=1e-6), vs)
        self.assertTrue(np.array_equal(self.bench.strain_key("body", "Pull"), vs))

    def test_threshold_counts_edges(self):
        """Порог считает рёбра сверх него: 0.25 → два, 0.5 → одно, 2 → ни одного."""
        expect = np.array([0, 0, 0, SQRT2 - 1, 1.0])
        for threshold, count in ((0.25, 2), (0.5, 1), (2.0, 0)):
            st = self.an.strain("body", "Pull", threshold=threshold)
            self.assertEqual(st.over_threshold, count, threshold)
            self.assertEqual(st.threshold, threshold)
            self.assertEqual(st.edges, 5)
            self.assertAlmostEqual(st.max_strain, 1.0, places=6)
            self.assertAlmostEqual(st.p99_strain, float(np.percentile(expect, 99)), places=5)

    def test_worst_bounds(self):
        """Охват худших рёбер — по исходным координатам их концов: при 0.25 это вершины
        1, 2, 3 (0..1 по X и Y); при пороге выше всех растяжений охвата нет."""
        st = self.an.strain("body", "Pull", threshold=0.25)
        self.assertEqual(st.as_dict()["worstBounds"],
                         {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 0.0]})
        st = self.an.strain("body", "Pull", threshold=0.5)
        self.assertEqual(st.as_dict()["worstBounds"],
                         {"min": [0.0, 1.0, 0.0], "max": [1.0, 1.0, 0.0]})
        self.assertIsNone(self.an.strain("body", "Pull", threshold=2.0).worst_bounds)
        self.assertIsNone(self.an.strain("body", "Pull", threshold=2.0).as_dict()["worstBounds"])

    def test_amount_scales_the_shift(self):
        """Половина ползунка: вершина 3 уходит на 0.5, ребро (1,3) → √1.25−1, (2,3) → 0.5."""
        _, strain = self.an.edge_strain("body", "Pull", amount=0.5)
        self.assertTrue(np.allclose(strain, [0, 0, 0, math.sqrt(1.25) - 1, 0.5], atol=1e-6))
        self.assertAlmostEqual(self.an.strain("body", "Pull", amount=0.5).max_strain, 0.5, places=6)

    def test_rigid_shift_has_no_strain(self):
        """Морф, двигающий часть целиком, ничего не растягивает: ровно ноль везде."""
        _, strain = self.an.edge_strain("body", "Shift")
        self.assertTrue(np.all(strain == 0.0), strain)
        st = self.an.strain("body", "Shift", threshold=0.0)
        self.assertEqual(st.max_strain, 0.0)
        self.assertEqual(st.over_threshold, 0)
        self.assertIsNone(st.worst_bounds)
        self.assertTrue(np.all(self.an.vertex_strain("body", "Shift") == 0.0))

    def test_none_for_unknown_or_empty(self):
        """Нет части, нет морфа или морф пуст — None, а не исключение; растяжение вершин
        при этом — нули длиной в часть."""
        self.assertIsNone(self.an.edge_strain("head", "Pull"))
        self.assertIsNone(self.an.edge_strain("body", "Nope"))
        self.assertIsNone(self.an.edge_strain("body", "Empty"))
        self.assertIsNone(self.an.strain("body", "Empty"))
        self.assertTrue(np.array_equal(self.an.vertex_strain("body", "Empty"), np.zeros(4)))

    def test_report_sorted_and_filtered(self):
        """Сводка идёт по убыванию наибольшего растяжения, пропускает пустые морфы и части,
        которых в меше нет, и фильтруется по подстроке имени."""
        rows = self.an.strain_report()
        self.assertEqual([r.morph for r in rows], ["Pull", "Shift"])
        self.assertEqual([r.morph for r in self.an.strain_report(morph_filter="shi")], ["Shift"])
        orphan = common.morph_set(common.morph("Pull", "ghost", [0], [(1.0, 0.0, 0.0)]))
        self.assertEqual(Analyzer(common.model(self.body), orphan).strain_report(), [])

    def test_facade_matches_analyzer(self):
        """Фасад отдаёт те же строки, что as_dict() у StrainStat, и с теми же доводами."""
        want = [s.as_dict() for s in Analyzer(common.model(self.body), self.ms)
                .strain_report(0.5, 0.3, None)]
        self.assertEqual(self.bench.strain(0.5, 0.3), want)
        self.assertEqual(self.bench.strain(morph="pull"),
                         [s.as_dict() for s in self.an.strain_report(morph_filter="pull")])


class TestDegenerateGeometry(unittest.TestCase):
    """Вырожденные случаи, на которых легко получить NaN или падение."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_zero_length_edge(self):
        """Две совпадающие вершины дают ребро нулевой длины: его растяжение — 0, а не NaN."""
        pinched = Shape("pinched", np.array([[0, 0, 0], [0, 0, 0], [1, 0, 0]], np.float32),
                        np.array([[0, 1, 2]], np.int32), None, None, {})
        ms = common.morph_set(common.morph("Pull", "pinched", [2], [(1.0, 0.0, 0.0)]))
        an = common.bench(self.tmp.name, common.model(pinched), ms).analyzer
        edges, strain = an.edge_strain("pinched", "Pull")
        self.assertEqual(edges.tolist(), [[0, 1], [0, 2], [1, 2]])
        self.assertTrue(np.isfinite(strain).all())
        self.assertTrue(np.allclose(strain, [0.0, 1.0, 1.0]))

    def test_shape_without_triangles(self):
        """Часть из одних вершин (без треугольников) с морфом: у неё нет рёбер, и сводка
        обязана либо пропустить её, либо показать ноль рёбер — но не упасть, иначе один
        такой блок в меше ломает отчёт по всем остальным."""
        cloud = Shape("cloud", VERTS, np.zeros((0, 3), np.int32), None, None, {})
        ms = common.morph_set(common.morph("Pull", "cloud", [3], [(1.0, 0.0, 0.0)]))
        bench = common.bench(self.tmp.name, common.model(cloud), ms)
        try:
            rows = bench.strain()
        except ValueError as e:
            self.fail("strain() упал на части без треугольников: %s" % e)
        for r in rows:
            self.assertEqual(r["edges"], 0)


if __name__ == "__main__":
    common.main()
