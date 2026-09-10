# -*- coding: utf-8 -*-
"""Цепочки костей для качающейся физики: имя звена, порядок по дереву, кожа по звеньям,
обрывы, назначение движку. Фигуры в памяти: две части, у которых вершины держат звенья
хвоста и уха, - ожидания считаются в уме."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

import common
from common import bench, bone, grid, main, model
from morphbench.chains import Chain, Link, assign_engine, find_chains, split_name
from morphbench.colliders import Capsule, CollisionBody, ColliderSet


class TestNames(unittest.TestCase):
    def test_split(self):
        self.assertEqual(split_name("TailBone03"), ("TailBone", 3))
        self.assertEqual(split_name("NPC L Breast01"), ("NPC L Breast", 1))
        self.assertEqual(split_name("NPC EarL Bone02"), ("NPC EarL Bone", 2))
        self.assertEqual(split_name("GenitalsLag04"), ("GenitalsLag", 4))
        self.assertIsNone(split_name("NPC Head [Head]"))
        self.assertEqual(split_name("NPC L Finger00 [RF00]"), ("NPC L Finger", 0))   # тег снимается
        self.assertEqual(split_name("NPC Genitals03 [Gen03]"), ("NPC Genitals", 3))

    def test_engine_by_substring(self):
        engines = {"tail": "smp", "breast": "CBPC"}
        self.assertEqual(assign_engine("TailBone", engines), "smp")
        self.assertEqual(assign_engine("NPC L Breast", engines), "cbpc")
        self.assertIsNone(assign_engine("Genitals", engines))
        self.assertIsNone(assign_engine("TailBone", None))


class TestFindChains(unittest.TestCase):
    def test_orders_by_the_bone_tree_and_finds_the_break(self):
        counts = {"TailBone01": {"body": 30}, "TailBone02": {"body": 20, "fur": 5},
                  "TailBone03": {}, "TailBone04": {"body": 9},
                  "NPC Head [Head]": {"head": 100}, "Lonely07": {"body": 3}}
        # Дерево нарочно не по номерам: 02 - корень, 01 - его потомок.
        parents = {"TailBone01": "TailBone02", "TailBone02": "Spine", "TailBone03": "TailBone01",
                   "TailBone04": "TailBone03"}
        chains = find_chains(counts, parents, {"tail": "smp"})
        self.assertEqual([c.stem for c in chains], ["TailBone"])
        tail = chains[0]
        self.assertEqual(tail.bones, ["TailBone02", "TailBone01", "TailBone03", "TailBone04"])
        self.assertEqual(tail.engine, "smp")
        # Звено без кожи посреди - шарнир, не обрыв: цепочка годится.
        self.assertIsNone(tail.first_break(8))
        self.assertTrue(tail.fit(8))
        d = tail.as_dict(8)
        self.assertEqual((d["break"], d["tip"], d["vertices"]), (None, 9, 64))
        self.assertEqual((d["anchors"], d["gaps"], d["tail"]), ([], ["TailBone03"], []))
        self.assertEqual(d["links"][0]["shapes"], {"body": 20, "fur": 5})   # корень - 02
        self.assertEqual(d["parent"], "Spine")
        self.assertEqual([l["parent"] for l in d["links"]],
                         ["Spine", "TailBone02", "TailBone01", "TailBone03"])

    def test_without_a_tree_the_number_orders(self):
        counts = {"Ear02": {"head": 8}, "Ear01": {"head": 300}}
        chains = find_chains(counts)
        self.assertEqual(chains[0].bones, ["Ear01", "Ear02"])
        self.assertTrue(chains[0].fit(8))
        # Кончик из восьми вершин - дощечка: при пороге 9 он хвост без кожи, цепочка
        # годится одним звеном, и это видно по tail.
        self.assertTrue(chains[0].fit(9))
        self.assertEqual([l.bone for l in chains[0].tail(9)], ["Ear02"])

    def test_anchors_gaps_and_tail(self):
        """3BBB: Breast00 и 01 без кожи - опора, 02 и 03 - кожа, 04 без кожи - хвост."""
        counts = {"Breast0%d" % i: ({"body": [0, 0, 723, 1820, 0][i]} if i in (2, 3) else {})
                  for i in range(5)}
        parents = {"Breast0%d" % i: "Breast0%d" % (i - 1) for i in range(1, 5)}
        parents["Breast00"] = "NPC Spine2 [Spn2]"
        c = find_chains(counts, parents)[0]
        d = c.as_dict(8)
        self.assertTrue(d["fit"])
        self.assertEqual((d["anchors"], d["gaps"], d["tail"]),
                         (["Breast00", "Breast01"], [], ["Breast04"]))
        self.assertEqual(d["parent"], "NPC Spine2 [Spn2]")
        self.assertIsNone(d["break"])
        # Кожи нет ни на одном звене - вот это обрыв.
        bare = find_chains({"Cloak01": {}, "Cloak02": {}}, {"Cloak02": "Cloak01"})[0]
        self.assertFalse(bare.fit(8))
        self.assertEqual(bare.as_dict(8)["break"], "Cloak01")

    def test_parallel_bones_are_not_a_chain_but_layers_are_seen_through(self):
        """P1, P2, P3 под разными родителями - не цепочка; прослойка CME между звеньями -
        цепочка по дереву; ветвление - обе ветви крепятся к одной кости."""
        parents = {"Breast P1": "CME A", "Breast P2": "CME B", "Breast P3": "CME C"}
        self.assertEqual(find_chains({b: {"body": 5} for b in parents}, parents), [])
        parents = {"Tail01": "Spine", "CME Tail01": "Tail01", "Tail02": "CME Tail01",
                   "CME Tail02": "Tail02", "Tail03": "CME Tail02"}
        c = find_chains({"Tail01": {"b": 5}, "Tail02": {"b": 5}, "Tail03": {"b": 5}}, parents)[0]
        self.assertEqual(c.bones, ["Tail01", "Tail02", "Tail03"])
        self.assertEqual([l.parent for l in c.links], ["Spine", "Tail01", "Tail02"])
        parents = {"Br01": "Root", "Br02": "Br01", "Br03": "Br01"}
        c = find_chains({"Br01": {"b": 5}, "Br02": {"b": 5}, "Br03": {"b": 5}}, parents)[0]
        self.assertEqual([l.parent for l in c.links], ["Root", "Br01", "Br01"])

    def test_fingers_split_into_one_chain_per_root(self):
        """Пальцы: пять корней одного ствола - пять цепочек с номером корня в имени."""
        names = ["NPC L Finger%d%d [RF%d%d]" % (f, j, f, j) for f in range(3) for j in range(3)]
        parents = {}
        for f in range(3):
            parents["NPC L Finger%d0 [RF%d0]" % (f, f)] = "NPC L Hand [LHnd]"
            for j in (1, 2):
                parents["NPC L Finger%d%d [RF%d%d]" % (f, j, f, j)] = "NPC L Finger%d%d [RF%d%d]" % (f, j - 1, f, j - 1)
        chains = find_chains({n: {"body": 20} for n in names}, parents)
        self.assertEqual([c.stem for c in chains], ["NPC L Finger#00", "NPC L Finger#10", "NPC L Finger#20"])
        self.assertEqual(chains[1].bones, ["NPC L Finger10 [RF10]", "NPC L Finger11 [RF11]", "NPC L Finger12 [RF12]"])
        # Без дерева - непрерывные ряды номеров дают то же деление.
        flat = find_chains({n: {"body": 20} for n in names})
        self.assertEqual([c.stem for c in flat], ["NPC L Finger#00", "NPC L Finger#10", "NPC L Finger#20"])

    def test_single_link_is_not_a_chain(self):
        self.assertEqual(find_chains({"Bone01": {"body": 5}, "Other": {}}), [])


class TestFacadeChains(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Кожа 4x4: хвост держит два столбца, ухо - остальное; шерсть висит на кончике хвоста.
        skin = grid("body", 4, 4, bones={"TailBone01": bone("TailBone01", range(8)),
                                          "TailBone02": bone("TailBone02", range(8, 16), 0.9),
                                          "NPC EarL Bone01": bone("NPC EarL Bone01", range(12, 16), 0.5)})
        fur = grid("fur", 3, 3, z=2.0, bones={"TailBone02": bone("TailBone02", range(9))})
        self.bench = bench(self.tmp.name, model(skin, fur), boneMinVertices=2)
        self.bench.rig = ColliderSet(Path("memory.nif"), {}, {}, None,
                                     parents={"TailBone02": "TailBone01", "TailBone01": "Spine",
                                              "TailBone03": "TailBone02"})
        self.bench.rig.matrices = {"TailBone03": np.eye(4, dtype=np.float32)}

    def tearDown(self):
        self.tmp.cleanup()

    def test_counts_follow_the_dominant_bone(self):
        counts = self.bench.bone_counts()
        self.assertEqual(counts["TailBone01"], {"body": 8})
        self.assertEqual(counts["TailBone02"], {"body": 8, "fur": 9})   # 0.9 > 0.5 у уха
        self.assertEqual(counts["NPC EarL Bone01"], {})
        self.assertIn("TailBone03", counts)                             # из скелета, без кожи

    def test_chains_rows_name_the_break_and_the_engine(self):
        from common import is_plain
        rows = self.bench.chains()
        self.assertTrue(is_plain(rows))
        by = {r["chain"]: r for r in rows}
        self.assertEqual(sorted(by), ["TailBone"])            # у уха одно звено - не цепочка
        tail = by["TailBone"]
        self.assertEqual([l["bone"] for l in tail["links"]], ["TailBone01", "TailBone02", "TailBone03"])
        self.assertIsNone(tail["break"])
        self.assertEqual(tail["tail"], ["TailBone03"])          # хвост без кожи - отбрасывается
        self.assertTrue(tail["fit"])
        self.assertIsNone(tail["engine"])
        self.bench.cfg._values["chainEngines"] = {"tailbone": "smp"}
        self.assertEqual(self.bench.chains()[0]["engine"], "smp")
        self.assertEqual(self.bench.chains(engine="cbpc"), [])

    def test_hidden_parts_do_not_count(self):
        self.bench.only(["body"])
        rows = self.bench.chains(shapes=self.bench.visible_shapes())
        tail = rows[0]
        self.assertEqual(tail["links"][1]["shapes"], {"body": 8})


if __name__ == "__main__":
    main()
