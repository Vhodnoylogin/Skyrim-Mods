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
        self.assertIsNone(split_name("NPC L Finger00 [RF00]"))

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
        self.assertEqual(tail.first_break(8).bone, "TailBone03")
        self.assertFalse(tail.fit(8))
        d = tail.as_dict(8)
        self.assertEqual((d["break"], d["tip"], d["vertices"]), ("TailBone03", 9, 64))
        self.assertEqual(d["links"][0]["shapes"], {"body": 20, "fur": 5})   # корень - 02

    def test_without_a_tree_the_number_orders(self):
        counts = {"Ear02": {"head": 8}, "Ear01": {"head": 300}}
        chains = find_chains(counts)
        self.assertEqual(chains[0].bones, ["Ear01", "Ear02"])
        self.assertTrue(chains[0].fit(8))
        self.assertFalse(chains[0].fit(9))       # кончик из восьми вершин - дощечка

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
        self.assertEqual(tail["break"], "TailBone03")
        self.assertFalse(tail["fit"])
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
