# -*- coding: utf-8 -*-
"""Колайдеры: капсула, посадка по коже, набор тел, точечная правка файла и слой PPB.

Ни один набор не читает настоящий скелет: капсулы собираются в памяти из известных
чисел, и ожидания считаются в уме. Файл для правки байтов собирается здесь же - крошечный
заголовок NIF с двумя блоками - либо пишется PyNifly, и тогда проверяется, что разбор
заголовка сходится с настоящим файлом. Сбой означает поломку ядра, а не изменившийся
скелет вервольфа.
"""
from __future__ import annotations

import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

import common
from common import bench, bone, grid, main, model
from morphbench.colliders import Capsule, CollisionBody, ColliderSet
from morphbench.nifpatch import NifPatch
from presenters import ppb


def rig(*bodies: CollisionBody, matrices: dict | None = None,
        bumper: CollisionBody | None = None) -> ColliderSet:
    return ColliderSet(Path("memory.nif"), {b.bone: b for b in bodies},
                       matrices or {}, bumper)


def body(name: str, *capsules: Capsule, physics: dict | None = None,
         kind: str = "bhkRigidBody") -> CollisionBody:
    return CollisionBody(name, list(capsules), physics or {}, kind)


def cap(name: str = "B", index: int = 0, p1=(0, 0, -5), p2=(0, 0, 5),
        radius: float = 2.0, block: int = -1) -> Capsule:
    return Capsule(name, index, p1, p2, radius, block)


def shift(dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
          scale: float = 1.0) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[:3, :3] *= scale
    m[:3, 3] = (dx, dy, dz)
    return m


def tube(radius: float, z_from: float, z_to: float, rings: int = 21, around: int = 24):
    """Облако точек на поверхности цилиндра вдоль Z - как кожа на кости."""
    angles = np.linspace(0, 2 * np.pi, around, endpoint=False)
    ring = np.stack([radius * np.cos(angles), radius * np.sin(angles)], axis=1)
    return np.vstack([np.hstack([ring, np.full((around, 1), z)])
                      for z in np.linspace(z_from, z_to, rings)]).astype(np.float32)


class TestCapsule(unittest.TestCase):
    def test_length_and_total(self):
        """Длина - между концами, полная длина - вместе с обеими шапками."""
        c = cap(p1=(0, 0, 0), p2=(0, 0, 10), radius=3.0)
        self.assertAlmostEqual(c.length, 10.0, places=5)
        self.assertAlmostEqual(c.total, 16.0, places=5)

    def test_distance_signed(self):
        """Точка внутри даёт минус, на поверхности - ноль, снаружи - сколько не хватило."""
        c = cap(p1=(0, 0, -5), p2=(0, 0, 5), radius=2.0)
        d = c.distance_to([(0, 0, 0), (2, 0, 0), (5, 0, 0), (0, 0, 8)])
        self.assertAlmostEqual(float(d[0]), -2.0, places=5)   # на оси, глубже всего
        self.assertAlmostEqual(float(d[1]), 0.0, places=5)    # ровно на поверхности
        self.assertAlmostEqual(float(d[2]), 3.0, places=5)    # снаружи вбок
        self.assertAlmostEqual(float(d[3]), 1.0, places=5)    # снаружи за шапкой

    def test_degenerate_is_a_sphere(self):
        """Капсула нулевой длины - шар: расстояние считается от единственной точки."""
        c = cap(p1=(0, 0, 0), p2=(0, 0, 0), radius=4.0)
        d = c.distance_to([(0, 0, 6), (0, 0, 0)])
        self.assertAlmostEqual(float(d[0]), 2.0, places=5)
        self.assertAlmostEqual(float(d[1]), -4.0, places=5)

    def test_transform_moves_and_scales(self):
        """Перенос двигает концы, общий масштаб растягивает и радиус; блок едет с капсулой."""
        moved = cap(p1=(0, 0, 0), p2=(0, 0, 4), radius=1.0, block=7).transformed(shift(dz=10.0))
        self.assertAlmostEqual(float(moved.p1[2]), 10.0, places=5)
        self.assertAlmostEqual(moved.radius, 1.0, places=5)
        self.assertEqual(moved.block, 7)
        big = cap(p1=(0, 0, 0), p2=(0, 0, 4), radius=1.0).transformed(shift(scale=2.0))
        self.assertAlmostEqual(big.length, 8.0, places=4)
        self.assertAlmostEqual(big.radius, 2.0, places=4)

    def test_mesh_lies_on_the_surface(self):
        """Все вершины оболочки капсулы стоят на её поверхности: расстояние - ноль."""
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
        got = Capsule.fit(tube(3.0, -10, 10), "B", 0, percentile=90.0)
        axis = got.p2 - got.p1
        axis = axis / np.linalg.norm(axis)
        self.assertGreater(abs(float(axis[2])), 0.99)          # ось нашлась вдоль Z
        self.assertAlmostEqual(got.radius, 3.0, delta=0.2)
        # Концы отступают внутрь на радиус: полная длина - весь размах облака.
        self.assertAlmostEqual(got.total, 20.0, delta=0.6)
        self.assertEqual((got.bone, got.index, got.block), ("B", 0, -1))

    def test_one_spike_moves_neither_axis_nor_radius(self):
        """Одна выпирающая вершина не разворачивает ось и не раздувает радиус."""
        pts = np.vstack([tube(2.0, -8, 8, rings=10, around=8),
                         np.array([[40.0, 0.0, 0.0]], dtype=np.float32)])
        got = Capsule.fit(pts, percentile=90.0)
        axis = (got.p2 - got.p1) / max(got.length, 1e-6)
        self.assertGreater(abs(float(axis[2])), 0.99)
        self.assertLess(got.radius, 3.0)

    def test_too_few_points(self):
        self.assertIsNone(Capsule.fit(np.zeros((2, 3), dtype=np.float32)))


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
        self.assertGreater(cs.bumper_mesh()[1].shape[0], 0)
        self.assertEqual(rig(body("B", cap())).bumper_mesh()[1].shape[0], 0)

    def test_local_capsules_stay_in_bone_space(self):
        """Для чужих настроек капсула отдаётся как в файле - в системе кости."""
        cs = rig(body("B", cap(p1=(1, 2, 3), p2=(4, 5, 6))), matrices={"B": shift(dz=100.0)})
        rows = cs.local_capsules()
        self.assertEqual(rows[0]["bone"], "B")
        self.assertEqual(rows[0]["capsules"][0]["p1"], [1.0, 2.0, 3.0])

    def test_clearance_reports_what_sticks_out(self):
        """Точка внутри и точка снаружи: доля снаружи и худшее расстояние."""
        cs = rig(body("B", cap(p1=(0, 0, 0), p2=(0, 0, 0), radius=2.0)))
        got = cs.clearance("B", [(0, 0, 0), (0, 0, 1), (0, 0, 10)])
        self.assertEqual(got["points"], 3)
        self.assertAlmostEqual(got["worst"], 8.0, places=3)
        self.assertAlmostEqual(got["outside"], 1.0 / 3.0, places=3)

    def test_fit_returns_bone_local_and_changes_nothing(self):
        """Подгонка получает мировые точки, отдаёт капсулу в системе кости и не трогает
        набор, пока её не применили."""
        cs = rig(body("B", cap(block=5)), matrices={"B": shift(dz=100.0)})
        got = cs.fit("B", tube(1.0, 96.0, 104.0, rings=3, around=20))
        self.assertLess(abs(float(got.centre[2])), 1.0)        # вокруг начала кости
        self.assertEqual(got.block, -1)
        self.assertEqual(cs.body("B").capsules[0].block, 5)
        self.assertAlmostEqual(cs.body("B").capsules[0].radius, 2.0, places=5)

    def test_apply_fit_inherits_block_and_folds_bundle(self):
        """Севшая капсула наследует блок первой; блоки остальных капсул связки
        запоминаются, чтобы при записи получить те же числа."""
        cs = rig(body("B", cap(block=5), cap(index=1, block=6), cap(index=2, block=7)))
        fitted = cs.apply_fit("B", cap(radius=9.0))
        self.assertEqual((fitted.block, fitted.index), (5, 0))
        self.assertEqual(cs.body("B").capsules, [fitted])
        self.assertEqual(cs.body("B").spare_blocks, [6, 7])
        self.assertFalse(cs.body("B").is_bundle)
        # Повторная посадка не теряет запасных блоков и не дублирует их.
        again = cs.apply_fit("B", cap(radius=1.0))
        self.assertEqual(again.block, 5)
        self.assertEqual(cs.body("B").spare_blocks, [6, 7])

    def test_unknown_bone_names_the_near_ones(self):
        cs = rig(body("NPC L Thigh [LThg]", cap()))
        with self.assertRaises(KeyError) as ctx:
            cs.body("Thigh")
        self.assertIn("LThg", str(ctx.exception))

    def test_mesh_is_empty_without_bodies(self):
        verts, tris = rig().mesh()
        self.assertEqual(verts.shape[0], 0)
        self.assertEqual(tris.shape[0], 0)

    def test_save_refuses_without_blocks(self):
        """Капсулы, собранные в памяти, не знают блоков: записывать нечего и некуда."""
        with self.assertRaises((RuntimeError, FileNotFoundError)):
            rig(body("B", cap())).save_as(Path(tempfile.gettempdir()) / "mb-never.nif")


# ---- точечная правка файла --------------------------------------------------------------
def tiny_nif(block_sizes: list[int], roots: int = 1) -> bytes:
    """Заголовок NIF ровно того вида, который читает NifPatch, и пустые блоки за ним."""
    out = bytearray(b"Gamebryo File Format, Version 20.2.0.7\n")
    out += struct.pack("<IBI", 0x14020007, 1, 12)
    out += struct.pack("<II", len(block_sizes), 100)
    for s in (b"morphbench", b"", b""):
        out += struct.pack("<B", len(s)) + s
    out += struct.pack("<H", 1) + struct.pack("<I", 6) + b"NiNode"
    out += struct.pack("<%dH" % len(block_sizes), *([0] * len(block_sizes)))
    out += struct.pack("<%dI" % len(block_sizes), *block_sizes)
    out += struct.pack("<II", 1, 4) + struct.pack("<I", 4) + b"root"
    out += struct.pack("<I", 0)
    for size in block_sizes:
        out += bytes(size)
    out += struct.pack("<I", roots) + struct.pack("<%dI" % roots, *([0] * roots))
    return bytes(out)


class TestNifPatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "tiny.nif"
        self.path.write_bytes(tiny_nif([60, 48]))

    def tearDown(self):
        self.tmp.cleanup()

    def test_header_walk_matches_the_file(self):
        patch = NifPatch(self.path)
        self.assertEqual(patch.block_count, 2)
        self.assertEqual(patch.sizes, [60, 48])
        self.assertEqual(patch.offsets[1] - patch.offsets[0], 60)
        self.assertTrue(patch.consistent())

    def test_capsule_roundtrip_in_its_block(self):
        """Что записано в блок капсулы, то из него и читается; соседний блок цел."""
        patch = NifPatch(self.path)
        before = bytes(patch.raw)
        patch.write_capsule(1, (1.0, 2.0, 3.0), (4.0, 5.0, 6.0), 0.5)
        p1, p2, r = patch.read_capsule(1)
        self.assertEqual((p1, p2, r), ((1.0, 2.0, 3.0), (4.0, 5.0, 6.0), 0.5))
        self.assertEqual(bytes(patch.raw[:patch.offsets[1]]), before[:patch.offsets[1]])
        self.assertEqual(bytes(patch.raw[patch.end:]), before[patch.end:])
        saved = patch.save(Path(self.tmp.name) / "out" / "tiny.nif")
        self.assertEqual(len(saved.read_bytes()), len(before))

    def test_refuses_a_block_that_is_not_a_capsule(self):
        patch = NifPatch(self.path)
        with self.assertRaises(ValueError):
            patch.write_capsule(0, (0, 0, 0), (0, 0, 1), 1.0)
        with self.assertRaises(KeyError):
            patch.write_capsule(9, (0, 0, 0), (0, 0, 1), 1.0)

    def test_set_writes_through_the_patch(self):
        """Набор с капсулой, знающей блок, пишет НОВЫЙ файл в единицах Havok."""
        from morphbench.colliders import HAVOK_SCALE
        cs = ColliderSet(self.path, {"B": body("B", cap(p1=(0, 0, 0), p2=(0, 0, 70.0),
                                                       radius=7.0, block=1))}, {})
        out = cs.save_as(Path(self.tmp.name) / "fitted.nif")
        self.assertNotEqual(out, self.path)
        p1, p2, r = NifPatch(out).read_capsule(1)
        self.assertAlmostEqual(p2[2], 70.0 / HAVOK_SCALE, places=5)
        self.assertAlmostEqual(r, 7.0 / HAVOK_SCALE, places=5)

    def test_real_file_from_pynifly_walks_consistently(self):
        """Заголовок настоящего NIF, записанного PyNifly, сходится с длиной файла."""
        cfg = common.config(self.tmp.name)
        pynifly = common.load_pynifly(cfg)
        nif = common.write_nif(pynifly, Path(self.tmp.name) / "real.nif", {"body": {
            "verts": [(0, 0, 0), (1, 0, 0), (0, 1, 0)], "tris": [(0, 1, 2)],
            "uvs": [(0, 0), (1, 0), (0, 1)], "normals": [(0, 0, 1)] * 3}})
        patch = NifPatch(nif)
        self.assertGreaterEqual(patch.block_count, 2)
        self.assertTrue(patch.consistent(), (patch.end, len(patch.raw)))


# ---- слой PPB -----------------------------------------------------------------------------
class TestPPB(unittest.TestCase):
    def test_slot_key_strips_side_and_prefix(self):
        self.assertEqual(ppb.slot_key("NPC L Thigh [LThg]"), "thigh")
        self.assertEqual(ppb.slot_key("NPC R UpperArm [RUar]"), "upperarm")
        self.assertEqual(ppb.slot_key("TailBone03"), "tailbone03")

    def test_lines_name_the_slot_and_the_child(self):
        """Ручки PPB складываются как cap<Слот>[C<номер>]<поле> по капсулам в системе кости."""
        cs = rig(body("NPC L Calf [LClf]",
                      cap(p1=(1, 2, 3), p2=(4, 5, 6), radius=7.0),
                      cap(index=1, p1=(0, 0, 0), p2=(0, 0, 1), radius=0.5)),
                 matrices={"NPC L Calf [LClf]": shift(dz=500.0)})
        lines = ppb.lines(cs.local_capsules())
        self.assertIn("capCalfEnable 1", lines)
        self.assertIn("capCalfAX 1.0000", lines)
        self.assertIn("capCalfR 7.0000", lines)
        self.assertIn("capCalfC1Enable 1", lines)

    def test_unknown_bone_is_skipped(self):
        """У PPB нет слота под хвост, и выдумывать имя ручки нельзя."""
        self.assertEqual(ppb.lines(rig(body("TailBone03", cap())).local_capsules()), [])


# ---- кому принадлежит вершина --------------------------------------------------------------
class TestOwnedVertices(unittest.TestCase):
    def setUp(self):
        # Сетка 4x3: кость A держит вершины 0..7 весом 1, кость B - 4..11 весом 0.6.
        self.shape = grid("body", 4, 3, bones={"A": bone("A", range(8)),
                                                "B": bone("B", range(4, 12), 0.6)})

    def test_dominant_gives_shared_vertices_to_the_stronger(self):
        self.assertEqual(list(self.shape.owned_vertices("A")), list(range(8)))
        self.assertEqual(list(self.shape.owned_vertices("B")), list(range(8, 12)))

    def test_without_dominance_everyone_keeps_what_it_holds(self):
        self.assertEqual(list(self.shape.owned_vertices("B", dominant=False)),
                         list(range(4, 12)))

    def test_min_weight_is_a_floor(self):
        self.assertEqual(self.shape.owned_vertices("B", min_weight=0.7).size, 0)
        self.assertEqual(self.shape.owned_vertices("nobody").size, 0)

    def test_dominant_bone_is_computed_once(self):
        first = self.shape.dominant_bone()
        self.assertIs(self.shape.dominant_bone(), first)


class TestSkeletonBeside(unittest.TestCase):
    """Скелет в папке меша открывается вместе с телом сам - как файл морфов."""

    def test_open_pairs_the_skeleton_regardless_of_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = common.config(tmp)
            pynifly = common.load_pynifly(cfg)
            spec = {"body": {"verts": [(0, 0, 0), (1, 0, 0), (0, 1, 0)], "tris": [(0, 1, 2)],
                             "uvs": [(0, 0), (1, 0), (0, 1)], "normals": [(0, 0, 1)] * 3}}
            nif = common.write_nif(pynifly, Path(tmp) / "tiny_0.nif", spec)
            common.write_nif(pynifly, Path(tmp) / "Skeleton.NIF", spec)
            b = common.MorphBench(cfg)
            s = b.open(nif)
            self.assertTrue(b.has_skeleton())
            self.assertEqual(Path(s["skeleton"]).name, "Skeleton.NIF")
            self.assertEqual(s["colliders"], 0)              # тел столкновений в нём нет
            self.assertEqual(b.view_state()["colliders"], False)
            s = b.open(nif, skeleton="")
            self.assertFalse(b.has_skeleton())
            self.assertIsNone(s["skeleton"])


class TestFacade(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        skin = grid("body", 4, 4, bones={"B": bone("B", range(16))})
        self.bench = bench(self.tmp.name, model(skin))
        self.bench.rig = rig(body("B", cap(radius=1.0)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_layer_is_off_until_asked_and_lives_in_the_view(self):
        state = self.bench.view_state()
        self.assertFalse(state["colliders"])
        self.assertFalse(state["bumper"])
        self.assertTrue(self.bench.show_colliders()["colliders"])
        self.assertFalse(self.bench.view.bumper)               # бампер отдельно
        self.assertTrue(self.bench.show_colliders(True, True)["bumper"])
        self.assertEqual(self.bench.view_state()["bumper"], True)

    def test_summary_names_the_skeleton(self):
        s = self.bench.summary()
        self.assertEqual(Path(s["skeleton"]).name, "memory.nif")
        self.assertEqual(s["colliders"], 1)
        self.bench.rig = None
        self.assertEqual((self.bench.summary()["skeleton"], self.bench.summary()["colliders"]),
                         (None, 0))

    def test_refuses_without_a_skeleton(self):
        self.bench.rig = None
        self.assertFalse(self.bench.has_skeleton())
        with self.assertRaises(RuntimeError):
            self.bench.colliders()

    def test_skin_points_follow_the_sliders(self):
        """Точки для посадки берутся с применёнными ползунками, а не с исходного меша."""
        base = self.bench.skin_points("B", min_weight=0.5)
        self.assertEqual(base.shape[0], 16)
        self.assertTrue(np.allclose(base[:, 2], 0.0))

    def test_skin_points_only_from_visible_shapes(self):
        """Скрыл шерсть - садишься по коже; это и есть управление тем, по чему сажать."""
        skin = grid("body", 4, 4, bones={"B": bone("B", range(16))})
        fur = grid("fur", 4, 4, z=3.0, bones={"B": bone("B", range(16))})
        b = bench(self.tmp.name, model(skin, fur))
        b.rig = rig(body("B", cap()))
        self.assertEqual(b.skin_points("B").shape[0], 32)
        b.only(["body"])
        self.assertEqual(b.skin_points("B").shape[0], 16)

    def test_capsules_follow_the_visible_parts(self):
        """Скрыл часть - пропали капсулы костей, чьи вершины держала только она."""
        skin = grid("body", 4, 4, bones={"A": bone("A", range(16))})
        head = grid("head", 4, 4, z=5.0, bones={"H": bone("H", range(16))})
        b = bench(self.tmp.name, model(skin, head))
        b.rig = rig(body("A", cap()), body("H", cap()), body("Nobody", cap()))
        self.assertEqual(b.visible_collider_bones(), ["A", "H"])   # Nobody никого не держит
        b.only(["body"])
        self.assertEqual(b.visible_collider_bones(), ["A"])
        one = b.collider_mesh()[0].shape[0]
        b.show_all()
        self.assertEqual(b.collider_mesh()[0].shape[0], 2 * one)
        self.assertEqual([m["bone"] for m in b.collider_meshes()], ["A", "H", "Nobody"])
        b.only([])
        self.assertEqual(b.collider_mesh()[1].shape[0], 0)
        b.cfg._values["collidersFollowParts"] = False        # выключенное правило - все кости
        self.assertEqual(b.visible_collider_bones(), ["A", "H", "Nobody"])

    def test_fit_without_apply_changes_nothing(self):
        rows = self.bench.collider_fit(apply=False)
        self.assertTrue(rows and rows[0]["fitted"])
        self.assertAlmostEqual(self.bench.rig.body("B").capsules[0].radius, 1.0, places=5)
        self.bench.collider_fit()
        self.assertNotAlmostEqual(self.bench.rig.body("B").capsules[0].radius, 1.0, places=3)

    def test_collider_set_edits_one_capsule(self):
        got = self.bench.collider_set("B", 0, radius=9.0)
        self.assertAlmostEqual(got["radius"], 9.0, places=4)
        with self.assertRaises(IndexError):
            self.bench.collider_set("B", 7, radius=1.0)

    def test_output_is_machine_readable(self):
        from common import is_plain
        self.assertTrue(is_plain(self.bench.colliders()))
        self.assertTrue(is_plain(self.bench.collider_local()))
        self.assertTrue(is_plain(self.bench.collider_clearance()))
        self.assertTrue(is_plain(self.bench.collider_fit(apply=False)))


if __name__ == "__main__":
    main()
