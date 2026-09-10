# -*- coding: utf-8 -*-
"""Шары охвата: наименьший шар над облаком, состояния ползунков, строки фасада и запись.

Фигуры в памяти: сетка с морфом, уводящим одну вершину далеко, - ожидания считаются
в уме. Запись проверяется на крошечном блоке части, собранном здесь же по раскладке
BSTriShape, и на настоящем NIF от PyNifly: шар, прочитанный NifPatch, обязан совпасть
с тем, что читает PyNifly, - иначе раскладка не та.
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

import common
from common import bench, grid, main, model, morph, morph_set
from morphbench.bounds import Reach, Sphere, enclosing_sphere
from morphbench.nifpatch import NifPatch


class TestEnclosingSphere(unittest.TestCase):
    def test_covers_everything_and_is_tight(self):
        """Точки на сфере радиуса 5 вокруг (1,2,3): шар накрывает все и не шире 5.5."""
        rng = np.random.default_rng(3)
        v = rng.normal(size=(500, 3)).astype(np.float32)
        pts = np.array([1, 2, 3], np.float32) + 5.0 * v / np.linalg.norm(v, axis=1, keepdims=True)
        s = enclosing_sphere(pts)
        self.assertLessEqual(s.reach(pts), s.radius + 1e-4)
        self.assertLess(s.radius, 5.5)
        self.assertLess(float(np.linalg.norm(s.centre - [1, 2, 3])), 0.6)

    def test_never_worse_than_the_start(self):
        """Названный центр - кандидат: шар не выйдет шире, чем от него."""
        pts = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0]], np.float32)
        start = np.array([5, 5, 0], np.float32)
        s = enclosing_sphere(pts, start=start)
        self.assertLessEqual(s.radius, Sphere(start, 0.0).reach(pts) + 1e-5)

    def test_empty(self):
        self.assertEqual(enclosing_sphere(np.zeros((0, 3))).radius, 0.0)


class TestReach(unittest.TestCase):
    def setUp(self):
        # Сетка 4x4 в плоскости z=0; морф Up поднимает вершину 15 на 20 вверх,
        # морф Down опускает вершину 0 на 6 вниз.
        self.rest = grid("body", 4, 4).verts
        self.deltas = {"Up": np.zeros((16, 3), np.float32), "Down": np.zeros((16, 3), np.float32)}
        self.deltas["Up"][15, 2] = 20.0
        self.deltas["Down"][0, 2] = -6.0

    def test_states_include_singles_all_and_worst(self):
        r = Reach(self.rest, self.deltas, 0.0, 1.0)
        names = set(r.states([1.5, 1.5, 0.0]))
        self.assertEqual(names, {"rest", "Up=1", "Down=1", "all=1", "worst"})
        r2 = Reach(self.rest, self.deltas, -1.0, 1.0)
        self.assertIn("Down=-1", set(r2.states([0, 0, 0])))
        self.assertIn("all=-1", set(r2.states([0, 0, 0])))

    def test_needed_sphere_covers_the_lifted_vertex(self):
        r = Reach(self.rest, self.deltas)
        s = r.needed()
        top = self.rest[15] + [0, 0, 20]
        self.assertLessEqual(float(np.linalg.norm(top - s.centre)), s.radius + 1e-3)
        # Тесно: сфера через (0,0,-6) - вершина 0 под морфом Down - и (3,3,20): r = 13.17.
        self.assertLess(s.radius, 13.4)
        self.assertGreater(s.radius, 13.0)

    def test_margin_scales_the_radius(self):
        r = Reach(self.rest, self.deltas)
        self.assertAlmostEqual(r.needed(1.5).radius, r.needed(1.0).radius * 1.5, places=4)

    def test_farthest_names_the_state(self):
        r = Reach(self.rest, self.deltas)
        file_sphere = Sphere([1.5, 1.5, 0.0], 3.0)
        state, far = r.farthest(file_sphere)
        self.assertIn(state, ("Up=1", "all=1", "worst"))
        self.assertAlmostEqual(far, float(np.linalg.norm([1.5, 1.5, 20.0])), places=3)
        single, single_far = r.farthest(file_sphere, single=True)
        self.assertEqual(single, "Up=1")

    def test_corner_of_two_sliders_is_covered(self):
        """Два ползунка вместе уводят дальше любого одного и дальше «худшего набора»
        по направлению: полоска 7x3, Up, Forward и встречный Back. Радиус нужного шара
        обязан накрыть угол Up=1, Forward=1, и reach_exact называет этот угол."""
        rest = grid("body", 7, 3).verts
        n = rest.shape[0]
        d = {"Up": np.tile([0, 0, 8.0], (n, 1)).astype(np.float32),
             "Forward": np.tile([0, 8.0, 0], (n, 1)).astype(np.float32),
             "Back": np.tile([0, -3.0, -3.0], (n, 1)).astype(np.float32)}
        r = Reach(rest, d)
        s = r.needed()
        corner = rest + d["Up"] + d["Forward"]
        self.assertLessEqual(float(np.linalg.norm(corner - s.centre, axis=1).max()), s.radius + 1e-3)
        far, state, over = r.reach_exact(s.centre)
        self.assertAlmostEqual(far, s.radius, places=3)
        self.assertEqual(over, 0)
        self.assertEqual(set(state.split(",")), {"Up=1", "Forward=1"})
        # Перебор всех углов вручную - тот же ответ.
        best = 0.0
        for mask in range(8):
            pts = rest + sum(list(d.values())[j] for j in range(3) if (mask >> j) & 1)
            best = max(best, float(np.linalg.norm(pts - s.centre, axis=1).max()))
        self.assertAlmostEqual(best, far, places=3)

    def test_corner_cap_falls_back_and_reports(self):
        rest = grid("body", 2, 2).verts
        d = {"m%d" % i: np.full((4, 3), 0.5, np.float32) for i in range(6)}
        far, state, over = Reach(rest, d).reach_exact([0.5, 0.5, 0.0], cap=3)
        self.assertEqual(over, 4)
        self.assertEqual(state, "worst")
        self.assertGreater(far, 0.0)

    def test_without_morphs_only_rest(self):
        r = Reach(self.rest, {})
        self.assertEqual(list(r.states([0, 0, 0])), ["rest"])
        self.assertAlmostEqual(r.needed().radius, float(np.linalg.norm([1.5, 1.5, 0])), places=3)


class TestFacadeBounds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        skin = grid("body", 4, 4)
        skin.bound = Sphere([1.5, 1.5, 0.0], 2.2)          # как в файле: только покой
        skin.block = 7
        fur = grid("fur", 4, 4, z=1.0)                      # без шара в файле
        up = morph("Up", "body", [15], [(0, 0, 20)])
        self.bench = bench(self.tmp.name, model(skin, fur), morph_set(up))

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_are_numbers(self):
        from common import is_plain
        rows = self.bench.bounds()
        self.assertTrue(is_plain(rows))
        by = {r["shape"]: r for r in rows}
        body = by["body"]
        self.assertAlmostEqual(body["file"]["radius"], 2.2, places=3)
        self.assertGreater(body["reach"], 20.0)
        self.assertGreater(body["excess"], 8.0)
        self.assertFalse(body["ok"])
        self.assertEqual(body["single"], "Up=1")
        self.assertGreater(body["needed"]["radius"], 10.0)
        self.assertIsNone(by["fur"]["file"])
        self.assertIsNone(by["fur"]["ok"])
        self.assertGreater(by["fur"]["needed"]["radius"], 2.0)

    def test_ok_when_the_file_sphere_already_covers(self):
        self.bench.model.shape("body").bound = Sphere([1.5, 1.5, 10.0], 50.0)
        row = self.bench.bounds("body")[0]
        self.assertTrue(row["ok"])
        self.assertLessEqual(row["excess"], 0.0)

    def test_margin_from_config_and_argument(self):
        base = self.bench.bounds("body", margin=1.0)[0]["needed"]["radius"]
        self.assertAlmostEqual(self.bench.bounds("body", margin=1.1)[0]["needed"]["radius"],
                               base * 1.1, places=3)


# ---- запись: блок части, собранный по раскладке ------------------------------------------
def shape_block(extra_refs: int, centre=(1.0, 2.0, 3.0), radius: float = 4.0) -> bytes:
    """Голова BSTriShape до шара охвата включительно; хвост блока - нули."""
    b = bytearray()
    b += struct.pack("<I", 0)                       # имя
    b += struct.pack("<I", extra_refs) + struct.pack("<%dI" % extra_refs, *([9] * extra_refs))
    b += struct.pack("<I", 0xFFFFFFFF)              # контроллер
    b += struct.pack("<I", 14)                      # флаги
    b += struct.pack("<3f", 0, 0, 0)                # перенос
    b += struct.pack("<9f", 1, 0, 0, 0, 1, 0, 0, 0, 1)   # поворот
    b += struct.pack("<f", 1.0)                     # масштаб
    b += struct.pack("<I", 0xFFFFFFFF)              # коллизия
    b += struct.pack("<4f", *centre, radius)        # шар охвата
    b += bytes(40)
    return bytes(b)


def tiny_nif(blocks: list[tuple[str, bytes]], bs_version: int = 100) -> bytes:
    """Заголовок NIF того вида, который читает NifPatch, и блоки за ним."""
    kinds = sorted({k for k, _ in blocks})
    out = bytearray(b"Gamebryo File Format, Version 20.2.0.7\n")
    out += struct.pack("<IBI", 0x14020007, 1, 12)
    out += struct.pack("<II", len(blocks), bs_version)
    for s in (b"morphbench", b"", b""):
        out += struct.pack("<B", len(s)) + s
    out += struct.pack("<H", len(kinds))
    for k in kinds:
        out += struct.pack("<I", len(k)) + k.encode("ascii")
    out += struct.pack("<%dH" % len(blocks), *[kinds.index(k) for k, _ in blocks])
    out += struct.pack("<%dI" % len(blocks), *[len(b) for _, b in blocks])
    out += struct.pack("<II", 1, 4) + struct.pack("<I", 4) + b"root"
    out += struct.pack("<I", 0)
    for _, b in blocks:
        out += b
    out += struct.pack("<I", 1) + struct.pack("<I", 0)
    return bytes(out)


class TestBoundsPatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "tiny.nif"
        self.path.write_bytes(tiny_nif([("NiNode", bytes(60)),
                                        ("BSTriShape", shape_block(2, (1, 2, 3), 4.0)),
                                        ("BSTriShape", shape_block(0, (5, 6, 7), 8.0))]))

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_the_sphere_past_the_extra_refs(self):
        patch = NifPatch(self.path)
        self.assertEqual(patch.types, ["NiNode", "BSTriShape", "BSTriShape"])
        self.assertEqual(patch.read_bounds(1), ((1.0, 2.0, 3.0), 4.0))
        self.assertEqual(patch.read_bounds(2), ((5.0, 6.0, 7.0), 8.0))
        self.assertTrue(patch.consistent())

    def test_writes_in_place_and_refuses_other_blocks(self):
        patch = NifPatch(self.path)
        before = bytes(patch.raw)
        patch.write_bounds(1, (9, 9, 9), 42.0)
        self.assertEqual(patch.read_bounds(1), ((9.0, 9.0, 9.0), 42.0))
        self.assertEqual(patch.read_bounds(2), ((5.0, 6.0, 7.0), 8.0))
        self.assertEqual(len(patch.raw), len(before))
        with self.assertRaises(ValueError):
            patch.write_bounds(0, (0, 0, 0), 1.0)
        with self.assertRaises(KeyError):
            patch.read_bounds(5)

    def test_old_versions_are_refused(self):
        old = Path(self.tmp.name) / "old.nif"
        old.write_bytes(tiny_nif([("BSTriShape", shape_block(0))], bs_version=83))
        with self.assertRaises(ValueError):
            NifPatch(old).read_bounds(0)

    def test_real_file_from_pynifly_reads_the_same_sphere(self):
        """Настоящий NIF: шар, прочитанный по раскладке, совпадает с тем, что читает PyNifly."""
        cfg = common.config(self.tmp.name)
        pynifly = common.load_pynifly(cfg)
        nif_path = common.write_nif(pynifly, Path(self.tmp.name) / "real.nif", {"body": {
            "verts": [(0, 0, 0), (2, 0, 0), (0, 2, 0)], "tris": [(0, 1, 2)],
            "uvs": [(0, 0), (1, 0), (0, 1)], "normals": [(0, 0, 1)] * 3}}, game="SKYRIMSE")
        nif = pynifly.NifFile(str(nif_path))
        shape = nif.shapes[0]
        patch = NifPatch(nif_path)
        centre, radius = patch.read_bounds(int(shape.id))
        self.assertAlmostEqual(radius, float(shape.properties.boundingSphereRadius), places=5)
        for a, b in zip(centre, shape.properties.boundingSphereCenter):
            self.assertAlmostEqual(a, float(b), places=5)

    def test_write_never_shrinks_and_refuses_the_source(self):
        cfg = common.config(self.tmp.name)
        pynifly = common.load_pynifly(cfg)
        nif_path = common.write_nif(pynifly, Path(self.tmp.name) / "wide.nif", {"body": {
            "verts": [(0, 0, 0), (2, 0, 0), (0, 2, 0), (1, 1, 0)], "tris": [(0, 1, 2), (1, 3, 2)],
            "uvs": [(0, 0), (1, 0), (0, 1), (1, 1)], "normals": [(0, 0, 1)] * 4}}, game="SKYRIMSE")
        from morphbench import MorphBench
        b = MorphBench(cfg)
        b.open(nif_path, tri="", skeleton="")
        with self.assertRaises(ValueError):                       # без морфов писать нечего
            b.bounds_write(Path(self.tmp.name) / "x.nif")
        b.morph_set = morph_set(morph("Up", "body", [3], [(0, 0, 30)]))
        with self.assertRaises(ValueError):                       # поверх исходника нельзя
            b.bounds_write(nif_path)
        # Намеренно широкий шар - в самом файле, как его оставил бы человек под SMP.
        patch = NifPatch(nif_path)
        patch.write_bounds(b.model.shape("body").block, (1, 1, 15), 50.0)
        wide = patch.save(Path(self.tmp.name) / "wide2.nif")
        b.open(wide, tri="", skeleton="")
        b.morph_set = morph_set(morph("Up", "body", [3], [(0, 0, 30)]))
        self.assertAlmostEqual(b.model.shape("body").bound.radius, 50.0, places=4)
        out = b.bounds_write(Path(self.tmp.name) / "kept.nif")
        self.assertEqual((out["shapes"], out["kept"]), ([], ["body"]))
        out = b.bounds_write(Path(self.tmp.name) / "shrunk.nif", shrink=True)
        self.assertEqual(out["shapes"], ["body"])

    def test_bounds_write_makes_a_new_file_that_pynifly_reads_back(self):
        """Запись через фасад: новый файл, старый цел, PyNifly читает новый шар."""
        cfg = common.config(self.tmp.name)
        pynifly = common.load_pynifly(cfg)
        nif_path = common.write_nif(pynifly, Path(self.tmp.name) / "real.nif", {"body": {
            "verts": [(0, 0, 0), (2, 0, 0), (0, 2, 0), (1, 1, 0)], "tris": [(0, 1, 2), (1, 3, 2)],
            "uvs": [(0, 0), (1, 0), (0, 1), (1, 1)], "normals": [(0, 0, 1)] * 4}}, game="SKYRIMSE")
        from morphbench import MorphBench
        b = MorphBench(cfg)
        b.open(nif_path, tri="", skeleton="")
        b.morph_set = morph_set(morph("Up", "body", [3], [(0, 0, 30)]))
        before = nif_path.read_bytes()
        out = b.bounds_write(Path(self.tmp.name) / "fixed.nif")
        self.assertEqual(out["shapes"], ["body"])
        self.assertEqual(nif_path.read_bytes(), before)
        fixed = pynifly.NifFile(out["saved"]).shapes[0]
        self.assertGreater(float(fixed.properties.boundingSphereRadius), 14.0)
        self.assertAlmostEqual(float(fixed.properties.boundingSphereRadius),
                               out["rows"][0]["needed"]["radius"], places=3)


if __name__ == "__main__":
    main()
