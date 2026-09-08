# -*- coding: utf-8 -*-
"""Колайдеры: капсула, посадка по коже и слой поверх тела.

Ни один набор не читает настоящий скелет: капсулы собираются в памяти из известных
чисел, и ожидания считаются в уме. Сбой здесь означает поломку ядра, а не изменившийся
скелет вервольфа.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from common import bench, bone, grid, main, model
from morphbench.colliders import (Capsule, CollisionBody, ColliderSet, _slot_key,
                                  fit_capsule)


def rig(*bodies: CollisionBody, matrices: dict | None = None,
        bumper: CollisionBody | None = None) -> ColliderSet:
    return ColliderSet(Path("memory.nif"), {b.bone: b for b in bodies},
                       matrices or {}, bumper)


def body(name: str, *capsules: Capsule, physics: dict | None = None,
         kind: str = "bhkRigidBody") -> CollisionBody:
    return CollisionBody(name, list(capsules), physics or {}, kind)


def cap(name: str = "B", index: int = 0, p1=(0, 0, -5), p2=(0, 0, 5),
        radius: float = 2.0) -> Capsule:
    return Capsule(name, index, p1, p2, radius)


def shift(dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
          scale: float = 1.0) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[:3, :3] *= scale
    m[:3, 3] = (dx, dy, dz)
    return m


class TestCapsule(unittest.TestCase):
    def test_length_and_total(self):
        """Длина — между концами, полная длина — вместе с обеими шапками."""
        c = cap(p1=(0, 0, 0), p2=(0, 0, 10), radius=3.0)
        self.assertAlmostEqual(c.length, 10.0, places=5)
        self.assertAlmostEqual(c.total, 16.0, places=5)

    def test_distance_signed(self):
        """Точка внутри даёт минус, на поверхности — ноль, снаружи — сколько не хватило."""
        c = cap(p1=(0, 0, -5), p2=(0, 0, 5), radius=2.0)
        d = c.distance_to([(0, 0, 0), (2, 0, 0), (5, 0, 0), (0, 0, 8)])
        self.assertAlmostEqual(float(d[0]), -2.0, places=5)   # на оси, глубже всего
        self.assertAlmostEqual(float(d[1]), 0.0, places=5)    # ровно на поверхности
        self.assertAlmostEqual(float(d[2]), 3.0, places=5)    # снаружи вбок
        self.assertAlmostEqual(float(d[3]), 1.0, places=5)    # снаружи за шапкой

    def test_degenerate_is_a_sphere(self):
        """Капсула нулевой длины — шар: расстояние считается от единственной точки."""
        c = cap(p1=(0, 0, 0), p2=(0, 0, 0), radius=4.0)
        d = c.distance_to([(0, 0, 6), (0, 0, 0)])
        self.assertAlmostEqual(float(d[0]), 2.0, places=5)
        self.assertAlmostEqual(float(d[1]), -4.0, places=5)

    def test_transform_moves_and_scales(self):
        """Перенос двигает концы, общий масштаб растягивает и радиус."""
        moved = cap(p1=(0, 0, 0), p2=(0, 0, 4), radius=1.0).transformed(shift(dz=10.0))
        self.assertAlmostEqual(float(moved.p1[2]), 10.0, places=5)
        self.assertAlmostEqual(moved.radius, 1.0, places=5)
        big = cap(p1=(0, 0, 0), p2=(0, 0, 4), radius=1.0).transformed(shift(scale=2.0))
        self.assertAlmostEqual(big.length, 8.0, places=4)
        self.assertAlmostEqual(big.radius, 2.0, places=4)

    def test_mesh_lies_on_the_surface(self):
        """Все вершины оболочки капсулы стоят на её поверхности: расстояние — ноль."""
        c = cap(p1=(0, 0, -3), p2=(0, 0, 3), radius=2.0)
        verts, tris = c.mesh(segments=12)
        self.assertGreater(tris.shape[0], 0)
        self.assertLess(float(np.abs(c.distance_to(verts)).max()), 1e-3)

    def test_mesh_triangles_reference_real_vertices(self):
        verts, tris = cap().mesh(segments=8)
        self.assertTrue((tris >= 0).all() and (tris < verts.shape[0]).all())


class TestFit(unittest.TestCase):
    def test_recovers_a_cylinder(self):
        """Облако точек вокруг оси Z даёт капсулу вдоль Z с тем же радиусом."""
        angles = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        ring = np.stack([3.0 * np.cos(angles), 3.0 * np.sin(angles)], axis=1)
        pts = np.vstack([np.hstack([ring, np.full((24, 1), z)])
                         for z in np.linspace(-10, 10, 21)])
        got = fit_capsule(pts, "B", 0, percentile=90.0)
        axis = got.p2 - got.p1
        axis = axis / np.linalg.norm(axis)
        self.assertGreater(abs(float(axis[2])), 0.99)          # ось нашлась вдоль Z
        self.assertAlmostEqual(got.radius, 3.0, delta=0.2)
        # Концы отступают внутрь на радиус: полная длина — весь размах облака.
        self.assertAlmostEqual(got.total, 20.0, delta=0.6)

    def test_percentile_ignores_one_spike(self):
        """Одна выпирающая вершина не должна раздувать капсулу на всю конечность."""
        angles = np.linspace(0, 2 * np.pi, 40, endpoint=False)
        pts = np.vstack([
            np.stack([2.0 * np.cos(angles), 2.0 * np.sin(angles),
                      np.linspace(-8, 8, 40)], axis=1),
            np.array([[40.0, 0.0, 0.0]], dtype=np.float32)])
        self.assertLess(fit_capsule(pts, percentile=90.0).radius, 6.0)

    def test_too_few_points(self):
        self.assertIsNone(fit_capsule(np.zeros((2, 3), dtype=np.float32)))


class TestColliderSet(unittest.TestCase):
    def test_world_capsules_follow_the_bone(self):
        """Капсула лежит в системе своей кости и выходит наружу уже мировой."""
        cs = rig(body("B", cap(p1=(0, 0, 0), p2=(0, 0, 2))),
                 matrices={"B": shift(dz=50.0)})
        got = cs.world_capsules()
        self.assertEqual(len(got), 1)
        self.assertAlmostEqual(float(got[0].p1[2]), 50.0, places=4)

    def test_bumper_is_kept_apart(self):
        """Цилиндр перемещения не попадает в тела: он вчетверо больше и закрыл бы всё."""
        cs = rig(body("B", cap()), bumper=body("Bump", cap(radius=25.0),
                                               kind="bhkSimpleShapePhantom"))
        self.assertEqual(cs.bone_names(), ["B"])
        self.assertEqual(len(cs.world_capsules()), 1)
        self.assertEqual(len(cs.world_capsules(bumper=True)), 2)
        self.assertEqual(cs.summary()["bumper"], "Bump")

    def test_clearance_reports_what_sticks_out(self):
        """Точка внутри и точка снаружи: доля снаружи и худшее расстояние."""
        cs = rig(body("B", cap(p1=(0, 0, 0), p2=(0, 0, 0), radius=2.0)))
        got = cs.clearance("B", [(0, 0, 0), (0, 0, 1), (0, 0, 10)])
        self.assertEqual(got["points"], 3)
        self.assertAlmostEqual(got["worst"], 8.0, places=3)
        self.assertAlmostEqual(got["outside"], 1.0 / 3.0, places=3)

    def test_fit_returns_bone_local(self):
        """Подгонка получает мировые точки, а капсулу отдаёт в системе кости."""
        cs = rig(body("B", cap()), matrices={"B": shift(dz=100.0)})
        angles = np.linspace(0, 2 * np.pi, 20, endpoint=False)
        pts = np.vstack([np.stack([np.cos(angles), np.sin(angles),
                                   np.full(20, 100.0 + z)], axis=1)
                         for z in (-4.0, 0.0, 4.0)])
        got = cs.fit("B", pts)
        self.assertLess(abs(float(got.centre[2])), 1.0)        # вокруг начала кости
        self.assertEqual(got.block, cs.body("B").capsules[0].block)

    def test_unknown_bone_names_the_near_ones(self):
        cs = rig(body("NPC L Thigh [LThg]", cap()))
        with self.assertRaises(KeyError) as ctx:
            cs.body("Thigh")
        self.assertIn("LThg", str(ctx.exception))

    def test_mesh_is_empty_without_bodies(self):
        verts, tris = rig().mesh()
        self.assertEqual(verts.shape[0], 0)
        self.assertEqual(tris.shape[0], 0)


class TestPPB(unittest.TestCase):
    def test_slot_key_strips_side_and_prefix(self):
        self.assertEqual(_slot_key("NPC L Thigh [LThg]"), "thigh")
        self.assertEqual(_slot_key("NPC R UpperArm [RUar]"), "upperarm")
        self.assertEqual(_slot_key("TailBone03"), "tailbone03")

    def test_lines_name_the_slot_and_the_child(self):
        """Ручки PPB складываются как cap<Слот>[C<номер>]<поле>."""
        cs = rig(body("NPC L Calf [LClf]",
                      cap(p1=(1, 2, 3), p2=(4, 5, 6), radius=7.0),
                      cap(index=1, p1=(0, 0, 0), p2=(0, 0, 1), radius=0.5)))
        lines = cs.ppb_lines()
        self.assertIn("capCalfEnable 1", lines)
        self.assertIn("capCalfAX 1.0000", lines)
        self.assertIn("capCalfR 7.0000", lines)
        self.assertIn("capCalfC1Enable 1", lines)

    def test_unknown_bone_is_skipped(self):
        """У PPB нет слота под хвост, и выдумывать имя ручки нельзя."""
        self.assertEqual(rig(body("TailBone03", cap())).ppb_lines(), [])


class TestFacade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        skin = grid("body", 4, 4, bones={"B": bone("B", range(16))})
        self.bench = bench(self.tmp.name, model(skin))
        self.bench.rig = rig(body("B", cap(radius=1.0)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_layer_is_off_until_asked(self):
        self.assertFalse(self.bench.view.colliders)
        self.assertFalse(self.bench.view.bumper)
        self.assertTrue(self.bench.show_colliders()["colliders"])
        self.assertFalse(self.bench.view.bumper)               # бампер отдельно
        self.assertTrue(self.bench.show_colliders(True, True)["bumper"])

    def test_refuses_without_a_skeleton(self):
        self.bench.rig = None
        self.assertFalse(self.bench.has_skeleton())
        with self.assertRaises(RuntimeError):
            self.bench.colliders()

    def test_skin_points_follow_the_sliders(self):
        """Точки для посадки берутся с применёнными ползунками, а не с исходного меша."""
        base = self.bench.skin_points("B", min_weight=0.5)
        self.assertEqual(base.shape[0], 16)
        self.bench.rig = rig(body("B", cap(radius=1.0)))
        self.assertTrue(np.allclose(base[:, 2], 0.0))

    def test_skin_points_only_from_visible_shapes(self):
        """Скрыл шерсть — садишься по коже; это и есть управление тем, по чему сажать."""
        skin = grid("body", 4, 4, bones={"B": bone("B", range(16))})
        fur = grid("fur", 4, 4, z=3.0, bones={"B": bone("B", range(16))})
        b = bench(self.tmp.name, model(skin, fur))
        b.rig = rig(body("B", cap()))
        self.assertEqual(b.skin_points("B").shape[0], 32)
        b.only(["body"])
        self.assertEqual(b.skin_points("B").shape[0], 16)

    def test_collider_set_edits_one_capsule(self):
        got = self.bench.collider_set("B", 0, radius=9.0)
        self.assertAlmostEqual(got["radius"], 9.0, places=4)
        with self.assertRaises(IndexError):
            self.bench.collider_set("B", 7, radius=1.0)

    def test_output_is_machine_readable(self):
        from common import is_plain
        self.assertTrue(is_plain(self.bench.colliders()))
        self.assertTrue(is_plain(self.bench.collider_clearance()))


if __name__ == "__main__":
    main()
