# -*- coding: utf-8 -*-
"""Растяжение рёбер: числа, посчитанные вручную на сетке из двух треугольников.

Мера |после / до − 1| ловит «перчатку»: если морф двигает ладонь и не трогает пальцы, рёбра
между ними растягиваются во столько же раз, во сколько разъехались их концы. Здесь известны
и длины рёбер до, и сдвиг одной вершины, поэтому ожидаемое растяжение каждого ребра
выписано явно. Морф, двигающий часть целиком, обязан дать ноль: форма не изменилась.

Дальше - то же для НАБОРА ползунков: два морфа тянут концы одного ребра в разные стороны,
и вместе рвут его сильнее, чем каждый поодиночке; набор равен сумме смещений, пара стоит
наверху перебора с положительной прибавкой; бюджет амплитуды для морфа, растягивающего
ребро линейно, равен порогу, делённому на наклон. Командная строка проверяется через
`mb.main` с фасадом, подключённым к фигуре в памяти: файлов и PyNifly ей не нужно.
"""
import contextlib
import io
import json
import math
import os
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import mb  # noqa: E402 - корень программы в sys.path добавил common
from morphbench import MorphBench, Shape  # noqa: E402
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


# ---- набор ползунков и перебор пар ------------------------------------------------------
# Right тянет вершину 1 на +1 по X, Left - вершину 0 на -1 по X. Ребро (0,1) длиной 1
# от каждого становится 2 (растяжение 1), от обоих - 3 (растяжение 2): пара рвёт сильнее
# каждого поодиночке. Остальные рёбра: у Right (1,2) √2 -> √5, (1,3) 1 -> √2; у Left
# (0,2) 1 -> √2. Shift двигает всё целиком и ничего не добавляет.
RIGHT = [1.0, 0.0, math.sqrt(2.5) - 1, SQRT2 - 1, 0.0]
LEFT = [1.0, SQRT2 - 1, 0.0, 0.0, 0.0]
BOTH = [2.0, SQRT2 - 1, math.sqrt(2.5) - 1, SQRT2 - 1, 0.0]
HALF = [1.0, math.sqrt(1.25) - 1, math.sqrt(1.625) - 1, math.sqrt(1.25) - 1, 0.0]


def pair_morphs():
    return common.morph_set(
        common.morph("Right", "body", [1], [(1.0, 0.0, 0.0)]),
        common.morph("Left", "body", [0], [(-1.0, 0.0, 0.0)]),
        common.morph("Shift", "body", [0, 1, 2, 3], [(3.0, -2.0, 5.0)]),
        common.empty_morph("Empty", "body"))


class TestStrainSet(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.body = Shape("body", VERTS, TRIS, None, None, {})
        self.ms = pair_morphs()
        self.bench = common.bench(self.tmp.name, common.model(self.body), self.ms)
        self.an = self.bench.analyzer

    def test_single_matches_edge_strain(self):
        """Набор из одного морфа - то же, что edge_strain по нему."""
        edges, strain = self.an.edge_strain_set("body", {"Right": 1.0})
        self.assertEqual(edges.tolist(), EDGES)
        self.assertTrue(np.allclose(strain, RIGHT, atol=1e-6), strain)
        self.assertTrue(np.allclose(strain, self.an.edge_strain("body", "Right")[1], atol=1e-6))
        self.assertTrue(np.allclose(self.an.edge_strain_set("body", {"Left": 1.0})[1], LEFT,
                                    atol=1e-6))

    def test_set_is_the_sum(self):
        """Оба вместе: ребро (0,1) из 1 становится 3 - растяжение 2, больше, чем 1 у каждого;
        и это ровно то, что даёт последовательное Morph.apply."""
        _, strain = self.an.edge_strain_set("body", {"Right": 1.0, "Left": 1.0})
        self.assertTrue(np.allclose(strain, BOTH, atol=1e-6), strain)
        moved = self.ms.get("body", "Left").apply(self.ms.get("body", "Right").apply(VERTS))
        e = np.array(EDGES)
        before = np.linalg.norm(VERTS[e[:, 0]] - VERTS[e[:, 1]], axis=1)
        after = np.linalg.norm(moved[e[:, 0]] - moved[e[:, 1]], axis=1)
        self.assertTrue(np.allclose(strain, np.abs(after / before - 1.0), atol=1e-6))

    def test_amounts_scale(self):
        """Половина каждого: (0,1) из 1 становится 2 - растяжение 1; остальные - по √."""
        _, strain = self.an.edge_strain_set("body", {"Right": 0.5, "Left": 0.5})
        self.assertTrue(np.allclose(strain, HALF, atol=1e-6), strain)

    def test_rigid_shift_adds_nothing(self):
        _, strain = self.an.edge_strain_set("body", {"Right": 1.0, "Shift": 1.0})
        self.assertTrue(np.allclose(strain, RIGHT, atol=1e-6), strain)
        _, strain = self.an.edge_strain_set("body", {"Shift": 1.0})
        self.assertTrue(np.all(strain == 0.0))

    def test_skips_zero_unknown_empty(self):
        """Ноль, чужое имя и пустой морф - не ползунки; набор из них одних не двигает ничего."""
        self.assertIsNone(self.an.edge_strain_set("body", {"Right": 0.0, "Nope": 1.0, "Empty": 1.0}))
        self.assertIsNone(self.an.edge_strain_set("head", {"Right": 1.0}))
        _, strain = self.an.edge_strain_set("body", {"Right": 0.0, "Left": 1.0, "Nope": 2.0})
        self.assertTrue(np.allclose(strain, LEFT, atol=1e-6))
        self.assertEqual(self.an.strain_set({"Right": 0.0}), [])
        self.assertEqual(self.an.strain_set({"Nope": 1.0}), [])

    def test_baseline_cached_per_shape(self):
        """Рёбра и длины «до» считаются один раз на часть: перебор пар их не пересчитывает."""
        first = self.an.edge_lengths("body")
        self.assertIs(first, self.an.edge_lengths("body"))
        self.assertIs(first[0], self.an.edges("body"))
        self.assertTrue(np.allclose(first[2], [1, 1, SQRT2, 1, 1]))
        self.assertIsNone(self.an.edge_lengths("head"))

    def test_rows_carry_the_set(self):
        """Строка сводки - как у strain_report, но с набором вместо морфа: при пороге 0.5
        сверх него два ребра, (0,1) и (1,2); охват их концов - вершины 0, 1, 2."""
        rows = self.an.strain_set({"Right": 1.0, "Left": 1.0}, threshold=0.5)
        self.assertEqual(len(rows), 1)
        st = rows[0]
        self.assertEqual((st.shape, st.morph, st.sliders), ("body", None, {"Right": 1.0, "Left": 1.0}))
        self.assertEqual((st.edges, st.over_threshold, st.threshold), (5, 2, 0.5))
        self.assertAlmostEqual(st.max_strain, 2.0, places=6)
        self.assertAlmostEqual(st.p99_strain, float(np.percentile(BOTH, 99)), places=5)
        d = st.as_dict()
        self.assertEqual(d["sliders"], {"Right": 1.0, "Left": 1.0})
        self.assertNotIn("morph", d)
        self.assertEqual(d["worstBounds"], {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 0.0]})
        self.assertTrue(common.is_plain(d))
        # Одиночный итог по-прежнему отдаёт morph и не отдаёт sliders.
        single = self.an.strain("body", "Right").as_dict()
        self.assertEqual(single["morph"], "Right")
        self.assertNotIn("sliders", single)

    def test_sorted_across_shapes(self):
        """Части идут по убыванию растяжения; часть, которой набор не касается, не в счёт."""
        head = common.grid("head", 2, 2, z=5.0)                 # та же топология, выше
        ms = common.morph_set(common.morph("Right", "body", [1], [(1.0, 0.0, 0.0)]),
                              common.morph("Nose", "head", [3], [(3.0, 0.0, 0.0)]))
        an = Analyzer(common.model(self.body, head), ms)
        rows = an.strain_set({"Right": 1.0, "Nose": 1.0})
        self.assertEqual([(r.shape, round(r.max_strain, 6)) for r in rows],
                         [("head", 3.0), ("body", 1.0)])
        self.assertEqual([r.shape for r in an.strain_set({"Right": 1.0})], ["body"])
        self.assertEqual(an.strain_extent({"Right": 1.0, "Nose": 1.0}, 0.5), (3.0, 4, "head"))
        self.assertEqual(an.strain_extent({"Nope": 1.0}), (0.0, 0, None))

    def test_facade(self):
        """Фасад: values None - нынешние ползунки; строки те же, что as_dict() у ядра;
        пустой набор и чужое имя - отказ, а не пустой ответ."""
        want = [s.as_dict() for s in self.an.strain_set({"Right": 1.0, "Left": 1.0}, 0.5)]
        self.assertEqual(self.bench.strain_set({"Right": 1, "Left": 1}, 0.5), want)
        self.bench.set_sliders({"Right": 1.0, "Left": 1.0})
        self.assertEqual(self.bench.strain_set(threshold=0.5), want)
        self.bench.reset_sliders()
        with self.assertRaises(ValueError):
            self.bench.strain_set()
        with self.assertRaises(ValueError):
            self.bench.strain_set({"Right": 0.0})
        with self.assertRaises(KeyError):
            self.bench.strain_set({"Nope": 1.0})


class TestStrainPairs(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.body = Shape("body", VERTS, TRIS, None, None, {})
        self.bench = common.bench(self.tmp.name, common.model(self.body), pair_morphs())
        self.an = self.bench.analyzer

    def test_active_morphs_skip_empty(self):
        self.assertEqual(self.an.active_morphs(), ["Left", "Right", "Shift"])

    def test_pair_on_top_with_gain(self):
        """Три непустых морфа - три пары. Left+Right вместе 2 при 1 у каждого: прибавка 1,
        наверху; пары с Shift равны своему одиночке, прибавка 0."""
        rows = self.an.strain_pairs(1.0, 0.5, top=None)
        self.assertEqual([(r["a"], r["b"]) for r in rows],
                         [("Left", "Right"), ("Left", "Shift"), ("Right", "Shift")])
        top = rows[0]
        self.assertAlmostEqual(top["maxStrain"], 2.0, places=6)
        self.assertAlmostEqual(top["gain"], 1.0, places=6)
        self.assertEqual((top["maxA"], top["maxB"]), (1.0, 1.0))
        self.assertEqual((top["overThreshold"], top["shape"], top["threshold"], top["amount"]),
                         (2, "body", 0.5, 1.0))
        for r in rows[1:]:
            self.assertAlmostEqual(r["maxStrain"], 1.0, places=6)
            self.assertAlmostEqual(r["gain"], 0.0, places=6)
        self.assertEqual(rows[1]["overThreshold"], 1)      # у Left сверх 0.5 только (0,1)
        self.assertEqual(rows[2]["overThreshold"], 2)      # у Right ещё и (1,2)

    def test_top_and_order(self):
        self.assertEqual(len(self.an.strain_pairs(top=1)), 1)
        self.assertEqual(len(self.an.strain_pairs(top=0)), 3)
        self.assertEqual(len(self.an.strain_pairs(top=None)), 3)
        by_gain = self.an.strain_pairs(top=None, by="gain")
        self.assertEqual((by_gain[0]["a"], by_gain[0]["b"]), ("Left", "Right"))
        with self.assertRaises(ValueError):
            self.an.strain_pairs(by="worst")

    def test_amount_scales_pairs(self):
        """При половине ползунков пара даёт 1, одиночки - по 0.5: прибавка 0.5."""
        rows = self.an.strain_pairs(0.5, top=1)
        self.assertAlmostEqual(rows[0]["maxStrain"], 1.0, places=6)
        self.assertAlmostEqual(rows[0]["gain"], 0.5, places=6)

    def test_fewer_than_two(self):
        ms = common.morph_set(common.morph("Right", "body", [1], [(1.0, 0.0, 0.0)]))
        self.assertEqual(Analyzer(common.model(self.body), ms).strain_pairs(), [])

    def test_facade_rounds(self):
        rows = self.bench.strain_pairs(top=2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(common.is_plain(rows))
        self.assertEqual(rows[0]["gain"], 1.0)
        self.assertEqual(rows[0]["maxStrain"], 2.0)


# ---- бюджет амплитуд ----------------------------------------------------------------------
class TestBudget(unittest.TestCase):
    """Pull тянет вершину 3 на +1 по X: ребро (2,3) длиной 1 становится 1+t, растяжение
    ровно t, а (1,3) даёт √(1+t²)-1 < t, - наибольшее растяжение линейно с наклоном 1.
    Pull2 - наклон 2, Tiny - наклон 0.1: на верхнем пределе 1 порога 0.25 не достигает."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.body = Shape("body", VERTS, TRIS, None, None, {})
        self.ms = common.morph_set(
            common.morph("Pull", "body", [3], [(1.0, 0.0, 0.0)]),
            common.morph("Pull2", "body", [3], [(2.0, 0.0, 0.0)]),
            common.morph("Tiny", "body", [3], [(0.1, 0.0, 0.0)]),
            common.morph("Shift", "body", [0, 1, 2, 3], [(3.0, -2.0, 5.0)]),
            common.empty_morph("Empty", "body"))
        self.bench = common.bench(self.tmp.name, common.model(self.body), self.ms)
        self.an = self.bench.analyzer

    def test_limits_by_hand(self):
        """Порог 0.25: Pull - 0.25/1, Pull2 - 0.25/2; Tiny и Shift в пределах не рвут."""
        rows = common.by_key(self.an.budget(), "morph")
        self.assertEqual(set(rows), {"Pull", "Pull2", "Tiny", "Shift"})
        self.assertAlmostEqual(rows["Pull"]["limit"], 0.25, delta=0.005)
        self.assertAlmostEqual(rows["Pull2"]["limit"], 0.125, delta=0.005)
        self.assertIsNone(rows["Tiny"]["limit"])
        self.assertAlmostEqual(rows["Tiny"]["maxAt"], 0.1, places=5)
        self.assertIsNone(rows["Shift"]["limit"])
        self.assertAlmostEqual(rows["Shift"]["maxAt"], 0.0, places=5)
        for r in rows.values():
            self.assertEqual((r["shape"], r["threshold"], r["high"]), ("body", 0.25, 1.0))
        self.assertAlmostEqual(rows["Pull"]["maxAt"], 1.0, places=6)
        self.assertAlmostEqual(rows["Pull2"]["maxAt"], 2.0, places=6)

    def test_order_tearing_first(self):
        """Рвущие - по возрастанию предела, потом не рвущие - по убыванию растяжения."""
        self.assertEqual([r["morph"] for r in self.an.budget()], ["Pull2", "Pull", "Tiny", "Shift"])

    def test_threshold_and_range(self):
        rows = common.by_key(self.an.budget(threshold=0.5), "morph")
        self.assertAlmostEqual(rows["Pull"]["limit"], 0.5, delta=0.005)
        self.assertAlmostEqual(rows["Pull2"]["limit"], 0.25, delta=0.005)
        rows = common.by_key(self.an.budget(high=0.2), "morph")
        self.assertIsNone(rows["Pull"]["limit"])
        self.assertAlmostEqual(rows["Pull"]["maxAt"], 0.2, places=5)
        self.assertAlmostEqual(rows["Pull2"]["limit"], 0.125, delta=0.005)
        self.assertEqual(rows["Pull2"]["high"], 0.2)
        coarse = common.by_key(self.an.budget(resolution=0.1), "morph")
        self.assertAlmostEqual(coarse["Pull"]["limit"], 0.25, delta=0.1)

    def test_facade_takes_settings(self):
        """Порог, пределы и точность - из настроек; числа округлены и пригодны для JSON."""
        rows = common.by_key(self.bench.budget(), "morph")
        self.assertAlmostEqual(rows["Pull"]["limit"], 0.25, delta=0.005)
        self.assertTrue(common.is_plain(list(rows.values())))
        b = common.bench(self.tmp.name, common.model(self.body), self.ms,
                         strainThreshold=0.5, sliderRange=[0.0, 0.2])
        rows = common.by_key(b.budget(), "morph")
        self.assertIsNone(rows["Pull"]["limit"])
        self.assertEqual(rows["Pull"]["maxAt"], 0.2)
        self.assertIsNone(rows["Pull2"]["limit"])            # 2*0.2 = 0.4 < 0.5
        self.assertEqual(rows["Pull2"]["maxAt"], 0.4)
        rows = common.by_key(b.budget(threshold=0.1), "morph")
        self.assertAlmostEqual(rows["Pull"]["limit"], 0.1, delta=0.005)
        self.assertAlmostEqual(rows["Pull2"]["limit"], 0.05, delta=0.005)


# ---- командная строка -----------------------------------------------------------------------
class TestCommandLine(unittest.TestCase):
    """strain без новых ключей - как раньше; --slider меряет набор, --pairs перебирает пары,
    budget даёт бюджет. Фасад подключён к фигуре в памяти, а open подменён: файлов нет."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.body = Shape("body", VERTS, TRIS, None, None, {})

    def fresh(self, morphs=None) -> MorphBench:
        bench = common.bench(self.tmp.name, common.model(self.body), morphs or pair_morphs())
        bench.open = lambda nif, tri=None, skeleton=None: bench.summary()
        return bench

    def cli(self, argv, bench):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(mb, "MorphBench", lambda: bench):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = mb.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def run_json(self, argv, bench):
        code, out, err = self.cli(argv, bench)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_plain_strain_unchanged(self):
        bench = self.fresh()
        self.assertEqual(self.run_json(["strain", "x.nif", "--json"], bench), bench.strain())
        self.assertEqual(self.run_json(["--json", "strain", "x.nif", "--morph", "left",
                                        "--threshold", "0.5", "--amount", "0.5"], bench),
                         bench.strain(0.5, 0.5, "left"))
        code, out, _ = self.cli(["strain", "x.nif"], bench)
        self.assertEqual(code, 0)
        self.assertIn("morph", out.splitlines()[0])

    def test_sliders_measure_the_set(self):
        rows = self.run_json(["--json", "strain", "x.nif", "--slider", "Right=1",
                              "--slider", "Left=1", "--threshold", "0.5"], self.fresh())
        self.assertEqual(rows, self.fresh().strain_set({"Right": 1.0, "Left": 1.0}, 0.5))
        self.assertEqual(rows[0]["sliders"], {"Right": 1.0, "Left": 1.0})
        self.assertNotIn("morph", rows[0])
        code, out, _ = self.cli(["strain", "x.nif", "--slider", "Right=1", "--slider", "Left=0.5"],
                                self.fresh())
        self.assertEqual(code, 0)
        self.assertIn("набор", out.splitlines()[0])
        self.assertIn("Right=1, Left=0.5", out)

    def test_bad_sliders_refused(self):
        code, _, err = self.cli(["strain", "x.nif", "--slider", "Right"], self.fresh())
        self.assertEqual(code, 2)
        self.assertIn("NAME=NUMBER", err)
        code, _, err = self.cli(["strain", "x.nif", "--slider", "Nope=1"], self.fresh())
        self.assertEqual(code, 2)
        self.assertIn("нет ползунка", err)

    def test_pairs(self):
        rows = self.run_json(["strain", "x.nif", "--pairs", "--top", "1", "--json"], self.fresh())
        self.assertEqual(rows, self.fresh().strain_pairs(1.0, None, 1))
        self.assertEqual((rows[0]["a"], rows[0]["b"], rows[0]["gain"]), ("Left", "Right", 1.0))
        rows = self.run_json(["strain", "x.nif", "--pairs", "--top", "0", "--by", "gain",
                              "--threshold", "0.5", "--amount", "0.5", "--json"], self.fresh())
        self.assertEqual(rows, self.fresh().strain_pairs(0.5, 0.5, 0, "gain"))
        self.assertEqual(len(rows), 3)
        code, out, _ = self.cli(["strain", "x.nif", "--pairs"], self.fresh())
        self.assertEqual(code, 0)
        self.assertIn("прибавка", out.splitlines()[0])
        self.assertEqual(len(out.splitlines()), 2 + 3)

    def test_budget(self):
        ms = common.morph_set(common.morph("Pull", "body", [3], [(1.0, 0.0, 0.0)]),
                              common.morph("Pull2", "body", [3], [(2.0, 0.0, 0.0)]),
                              common.morph("Tiny", "body", [3], [(0.1, 0.0, 0.0)]))
        rows = self.run_json(["budget", "x.nif", "--json"], self.fresh(ms))
        self.assertEqual(rows, self.fresh(ms).budget())
        self.assertEqual([r["morph"] for r in rows], ["Pull2", "Pull", "Tiny"])
        rows = self.run_json(["--json", "budget", "x.nif", "--threshold", "0.5"], self.fresh(ms))
        self.assertEqual(rows, self.fresh(ms).budget(0.5))
        code, out, _ = self.cli(["budget", "x.nif"], self.fresh(ms))
        self.assertEqual(code, 0)
        self.assertIn("предел", out.splitlines()[0])
        self.assertIn("в пределах не рвёт", out)
        self.assertIn("Pull2", out)


if __name__ == "__main__":
    common.main()
