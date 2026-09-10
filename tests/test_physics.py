# -*- coding: utf-8 -*-
"""Качающаяся физика: назначение цепочек движкам, капсулы по звеньям, слои smp и cbpc,
команда `physics`. Фигуры в памяти: кожа 10x4, у которой столбцы держат звенья хвоста,
уха и «шипа», шерсть на втором звене хвоста; скелет - матрицы и дерево без тел.
Хвост отдан SMP, ухо - CBPC, шип - никому: так проверяется, что чужая цепочка в вывод
не попадает, а шапка перечисляет всех.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import common
from common import bench, bone, columns, grid, is_plain, main, model
import mb
from presenters import cbpc, smp
from test_colliders import rig, shift

NX, NY = 10, 4


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        skin = grid("body", NX, NY, bones={
            "TailBone01": bone("TailBone01", columns(NX, NY, (0, 1))),
            "TailBone02": bone("TailBone02", columns(NX, NY, (2, 3))),
            "NPC EarL Bone01": bone("NPC EarL Bone01", columns(NX, NY, (4, 5))),
            "NPC EarL Bone02": bone("NPC EarL Bone02", columns(NX, NY, (6, 7))),
            # По одному столбцу: четыре точки в линию - кожа есть, а капсуле сесть не на что.
            "SpikeBone01": bone("SpikeBone01", columns(NX, NY, (8,))),
            "SpikeBone02": bone("SpikeBone02", columns(NX, NY, (9,)))})
        fur = grid("fur", 2, NY, z=1.0, x0=2.0, bones={"TailBone02": bone("TailBone02", range(8))})
        self.bench = bench(self.tmp.name, model(skin, fur), boneMinVertices=2,
                           chainEngines={"tail": "smp", "ear": "cbpc"})
        self.bench.rig = rig(matrices={
            "TailBone01": shift(dz=10.0), "TailBone02": shift(dz=20.0),
            "NPC EarL Bone01": shift(dx=4.0, dz=30.0), "NPC EarL Bone02": shift(dz=40.0),
            "SpikeBone01": shift(), "SpikeBone02": shift()})
        self.bench.rig.parents = {
            "TailBone01": "Tails", "TailBone02": "TailBone01",
            "NPC EarL Bone01": "NPC Head [Head]", "NPC EarL Bone02": "NPC EarL Bone01",
            "SpikeBone01": "Spine", "SpikeBone02": "SpikeBone01"}

    def tearDown(self):
        self.tmp.cleanup()


class TestFacade(Fixture):
    def test_assignment_comes_from_settings(self):
        by = {r["chain"]: r["engine"] for r in self.bench.chains()}
        self.assertEqual(by, {"TailBone": "smp", "NPC EarL Bone": "cbpc", "SpikeBone": None})
        self.assertEqual([r["chain"] for r in self.bench.chains("smp")], ["TailBone"])

    def test_assign_overrides_for_this_run_and_keeps_the_file(self):
        self.assertEqual(self.bench.assign_chains(), {"tail": "smp", "ear": "cbpc"})
        got = self.bench.assign_chains({"spike": "CBPC", "tail": "cbpc"})
        self.assertEqual(got, {"spike": "cbpc", "tail": "cbpc", "ear": "cbpc"})
        self.assertEqual(list(got)[:2], ["spike", "tail"])          # названное сверяется первым
        by = {r["chain"]: r["engine"] for r in self.bench.chains()}
        self.assertEqual(set(by.values()), {"cbpc"})
        with self.assertRaises(ValueError):
            self.bench.assign_chains({"tail": "havok"})
        raw = json.loads((Path(self.tmp.name) / "morphbench.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["chainEngines"], {"tail": "smp", "ear": "cbpc"})

    def test_chain_capsules_sit_in_bone_space(self):
        rows = self.bench.chain_capsules("cbpc")
        self.assertTrue(is_plain(rows))
        self.assertEqual([r["chain"] for r in rows], ["NPC EarL Bone"])
        ear = rows[0]
        self.assertEqual(ear["parent"], "NPC Head [Head]")
        first = ear["links"][0]
        self.assertEqual((first["bone"], first["points"], first["vertices"]), ("NPC EarL Bone01", 8, 8))
        cap = first["capsule"]
        # Кость стоит на (4, 0, 30), кожа на z=0: в системе кости капсула лежит на z=-30.
        self.assertAlmostEqual(cap["p1"][2], -30.0, delta=0.01)
        self.assertAlmostEqual(cap["p2"][2], -30.0, delta=0.01)
        self.assertAlmostEqual(cap["p1"][0], 0.5, delta=0.01)
        self.assertAlmostEqual(cap["radius"], 0.5, delta=0.05)
        by = {r["chain"]: r for r in self.bench.chain_capsules()}
        self.assertEqual(by["TailBone"]["parent"], "Tails")
        self.assertEqual(by["TailBone"]["links"][1]["shapes"], {"body": 8, "fur": 8})
        self.assertIsNone(by["SpikeBone"]["links"][0]["capsule"])   # четыре точки в линию

    def test_capsules_need_a_skeleton(self):
        self.bench.rig = None
        with self.assertRaises(RuntimeError):
            self.bench.chain_capsules()


def _code(text_out: str) -> list[str]:
    """Строки CBPC без комментариев и пустых."""
    return [l for l in text_out.splitlines() if l and not l.startswith("#")]


class TestCBPC(Fixture):
    def text(self) -> str:
        return cbpc.text(self.bench.chain_capsules("cbpc"), self.bench.chains(), self.bench.cfg, "memory")

    def test_only_its_chains_and_the_three_files(self):
        out = self.text()
        code = _code(out)
        self.assertIn("[ConfigMap]", code)
        self.assertIn("NPC EarL Bone01=MBEarLBone", code)
        self.assertIn("NPC EarL Bone02=MBEarLBone", code)
        self.assertLess(code.index("<"), code.index("NPC EarL Bone01=MBEarLBone"))
        self.assertGreater(code.index(">"), code.index("NPC EarL Bone02=MBEarLBone"))
        self.assertIn("MBEarLBone.stiffness 0.03", code)
        self.assertIn("MBEarLBone.Xminoffset -3", code)
        self.assertIn("MBEarLBone.linearXrotationY 1", code)
        self.assertIn("MBEarLBone.collisionZminOffset -100", code)
        self.assertIn("[AffectedNodes]", code)
        self.assertEqual(code[code.index("[AffectedNodes]") + 1], "NPC EarL Bone01")
        line = code[code.index("[NPC EarL Bone01]") + 1]
        self.assertRegex(line, r"^-?[\d.]+,-?[\d.]+,-?[\d.]+,[\d.]+ & -?[\d.]+,-?[\d.]+,-?[\d.]+,[\d.]+ \| "
                               r"-?[\d.]+,-?[\d.]+,-?[\d.]+,[\d.]+ & -?[\d.]+,-?[\d.]+,-?[\d.]+,[\d.]+$")
        half1, half2 = line.split(" | ")
        self.assertEqual(half1, half2)                       # вес 0 и вес 100 - одно тело
        self.assertIn("-30", half1)                          # в системе кости
        self.assertFalse(any("Tail" in l or "Spike" in l for l in code))

    def test_header_names_every_assignment(self):
        head = [l for l in self.text().splitlines() if l.startswith("#")]
        self.assertIn("memory", head[0])
        self.assertTrue(any("TailBone -> smp: другому движку" in l for l in head))
        self.assertTrue(any("NPC EarL Bone -> cbpc: здесь" in l for l in head))
        self.assertTrue(any("SpikeBone -> никому" in l for l in head))

    def test_numbers_come_from_settings(self):
        self.bench.cfg.set("cbpcStiffness", 0.42)
        self.bench.cfg.set("cbpcLinear", [7, 8, 9])
        code = _code(self.text())
        self.assertIn("MBEarLBone.stiffness 0.42", code)
        self.assertIn("MBEarLBone.linearZ 9", code)

    def test_link_without_a_capsule_bounces_but_does_not_collide(self):
        self.bench.assign_chains({"spike": "cbpc"})
        out = self.text()
        self.assertIn("SpikeBone01=MBSpikeBone", _code(out))
        self.assertNotIn("[SpikeBone01]", out)
        self.assertIn("# SpikeBone01: кожи на капсулу не хватило (4 точек)", out)

    def test_nothing_to_write_is_said_not_silent(self):
        self.bench.assign_chains({"ear": "smp"})
        out = self.text()
        self.assertIn("писать нечего", out)
        self.assertEqual(_code(out), [])
        self.assertIn("NPC EarL Bone -> smp: другому движку", out)

    def test_alias(self):
        self.assertEqual(cbpc.alias("NPC EarL [EarL]Bone"), "MBEarLBone")
        self.assertEqual(cbpc.alias("TailBone"), "MBTailBone")


class TestSMP(Fixture):
    def text(self) -> str:
        return smp.text(self.bench.chain_capsules("smp"), self.bench.chains(), self.bench.cfg, "memory")

    def test_bones_constraints_and_shapes(self):
        out = self.text()
        root = ET.fromstring(out.encode("utf-8"))               # XML верный
        self.assertEqual(root.tag, "system")
        bones = [(b.get("name"), len(b) > 0) for b in root.findall("bone")]
        self.assertEqual(bones, [("Tails", False), ("TailBone01", True), ("TailBone02", True)])
        dyn = {b.get("name"): b for b in root.findall("bone") if len(b)}
        self.assertEqual(dyn["TailBone01"].find("mass").text, "0.5")
        self.assertEqual(dyn["TailBone02"].find("mass").text, "0.35")     # легчает к кончику
        self.assertEqual(dyn["TailBone01"].find("inertia").get("x"), "200")
        cons = [(c.get("bodyA"), c.get("bodyB")) for c in root.findall("generic-constraint")]
        self.assertEqual(cons, [("TailBone01", "Tails"), ("TailBone02", "TailBone01")])
        first = root.find("generic-constraint")
        self.assertEqual(first.find("angularUpperLimit").get("y"), "0.2")
        self.assertEqual(first.find("linearStiffness").get("x"), "250")
        self.assertEqual([s.get("name") for s in root.findall("per-vertex-shape")], ["body", "fur"])
        self.assertEqual(root.find("per-vertex-shape").find("tag").text, "body")
        body_xml = out.split("-->", 1)[1]
        self.assertNotIn("EarL", body_xml)
        self.assertNotIn("Spike", body_xml)

    def test_header_names_every_assignment(self):
        head = self.text().split("-->", 1)[0]
        self.assertIn("memory", head)
        self.assertIn("TailBone -> smp: здесь", head)
        self.assertIn("NPC EarL Bone -> cbpc: другому движку", head)
        self.assertIn("SpikeBone -> никому", head)
        self.assertIn("капсул по костям он не читает", head)

    def test_numbers_come_from_settings(self):
        self.bench.cfg.set("smpMass", 2.0)
        self.bench.cfg.set("smpAngularLowerLimit", [-1, -2, -3])
        root = ET.fromstring(self.text().encode("utf-8"))
        self.assertEqual(root.find("bone[@name='TailBone01']").find("mass").text, "2")
        self.assertEqual(root.find("generic-constraint").find("angularLowerLimit").get("z"), "-3")

    def test_static_links_from_settings(self):
        self.bench.cfg.set("smpStaticLinks", 1)
        root = ET.fromstring(self.text().encode("utf-8"))
        bones = [(b.get("name"), len(b) > 0) for b in root.findall("bone")]
        self.assertEqual(bones, [("TailBone01", False), ("TailBone02", True)])
        cons = [(c.get("bodyA"), c.get("bodyB")) for c in root.findall("generic-constraint")]
        self.assertEqual(cons, [("TailBone02", "TailBone01")])

    def test_without_a_tree_the_first_link_anchors(self):
        self.bench.rig.parents = {}
        root = ET.fromstring(self.text().encode("utf-8"))
        self.assertEqual([(b.get("name"), len(b) > 0) for b in root.findall("bone")],
                         [("TailBone01", False), ("TailBone02", True)])

    def test_nothing_to_write_is_said_not_silent(self):
        self.bench.assign_chains({"tail": "cbpc"})
        out = self.text()
        root = ET.fromstring(out.encode("utf-8"))
        self.assertEqual(list(root), [])
        self.assertIn("писать нечего", out)


class TestCommandLine(Fixture):
    """`mb.py physics` и `chains --assign` с фасадом в памяти вместо файлов."""

    def main(self, argv) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(mb, "MorphBench", lambda: self.bench), \
                mock.patch.object(self.bench, "open", lambda *a, **k: {}), \
                mock.patch.object(self.bench, "open_skeleton", lambda *a, **k: {}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = mb.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def run_ok(self, argv) -> str:
        code, out, err = self.main(argv)
        self.assertEqual(code, 0, err)
        return out

    def test_physics_json(self):
        data = json.loads(self.run_ok(["physics", "memory.nif", "--engine", "cbpc", "--json"]))
        self.assertEqual(set(data), {"engine", "chains", "text"})
        self.assertEqual(data["engine"], "cbpc")
        by = {c["chain"]: c for c in data["chains"]}
        self.assertEqual(set(by), {"TailBone", "NPC EarL Bone", "SpikeBone"})
        self.assertTrue(by["NPC EarL Bone"]["written"])
        self.assertEqual((by["TailBone"]["engine"], by["TailBone"]["written"]), ("smp", False))
        self.assertEqual((by["SpikeBone"]["engine"], by["SpikeBone"]["written"]), (None, False))
        self.assertIn("[AffectedNodes]", data["text"])

    def test_physics_prints_the_text_without_out(self):
        out = self.run_ok(["physics", "memory.nif", "--engine", "smp", "--skeleton", "s.nif"])
        self.assertTrue(out.startswith("<?xml"))
        ET.fromstring(out.encode("utf-8"))

    def test_physics_out_and_assign(self):
        path = Path(self.tmp.name) / "out" / "tail.xml"
        data = json.loads(self.run_ok(["--json", "physics", "memory.nif", "--engine", "smp",
                                       "--assign", "ear=smp,tail=cbpc", "--out", str(path)]))
        self.assertEqual(Path(data["saved"]), path.resolve())
        self.assertEqual(path.read_text(encoding="utf-8"), data["text"])
        by = {c["chain"]: c for c in data["chains"]}
        self.assertTrue(by["NPC EarL Bone"]["written"])
        self.assertEqual((by["TailBone"]["engine"], by["TailBone"]["written"]), ("cbpc", False))
        root = ET.fromstring(data["text"].encode("utf-8"))
        self.assertEqual(root.find("bone").get("name"), "NPC Head [Head]")
        printed = self.run_ok(["physics", "memory.nif", "--engine", "smp", "--out", str(path)])
        self.assertIn("записан", printed)

    def test_physics_takes_sliders_and_only(self):
        """Кожа - то, что видно: спрятал шерсть - у звена нет шерсти в частях."""
        data = json.loads(self.run_ok(["physics", "memory.nif", "--engine", "smp", "--json",
                                       "--only", "body"]))
        self.assertNotIn('per-vertex-shape name="fur"', data["text"])

    def test_chains_assign(self):
        rows = json.loads(self.run_ok(["chains", "memory.nif", "--json", "--assign", "spike=smp"]))
        by = {r["chain"]: r["engine"] for r in rows}
        self.assertEqual(by, {"TailBone": "smp", "NPC EarL Bone": "cbpc", "SpikeBone": "smp"})

    def test_refusals_are_one_line(self):
        code, _, err = self.main(["physics", "memory.nif", "--engine", "smp", "--assign", "tail"])
        self.assertEqual(code, 2)
        self.assertIn("--assign", err)
        code, _, err = self.main(["physics", "memory.nif", "--engine", "smp", "--assign", "tail=havok"])
        self.assertEqual(code, 2)
        self.assertIn("havok", err)
        self.bench.rig = None
        code, _, err = self.main(["physics", "memory.nif", "--engine", "cbpc"])
        self.assertEqual(code, 2)
        self.assertIn("скелет", err)


if __name__ == "__main__":
    main()

class TestCheck(unittest.TestCase):
    """Проверка готового файла: движок молчит об ошибках, а мы находим опечатку."""

    BONES = ["NPC Head [Head]", "Ear01", "Ear02", "TailBone01", "TailBone02"]

    def test_smp_finds_unknown_bone_shape_and_constraint(self):
        from presenters import smp
        xml = """<?xml version="1.0"?><system>
        <bone name="NPC Head [Head]"/><bone name="Ear01"/><bone name="Ear0З"/>
        <generic-constraint bodyA="Ear01" bodyB="NPC Head [Head]"/>
        <generic-constraint bodyA="Ear02" bodyB="Ear01"/>
        <generic-constraint bodyA="Nowhere" bodyB="Ear01"/>
        <per-vertex-shape name="head"/><per-vertex-shape name="hed"/>
        <collision a="head" b="Ear01"/><collision a="ghost" b="Ear01"/>
        </system>"""
        rows = smp.check(xml, self.BONES, ["head", "body"])
        kinds = sorted((r["kind"], r["name"]) for r in rows)
        self.assertEqual(kinds, [("bone", "Ear0З"), ("collision", "ghost"),
                                 ("constraint", "Ear02"), ("constraint", "Nowhere"), ("shape", "hed")])
        by = {r["name"]: r for r in rows}
        self.assertIn("не объявленную", by["Ear02"]["problem"])      # есть в скелете, нет в файле
        self.assertIn("ни в файле, ни в скелете", by["Nowhere"]["problem"])
        self.assertEqual(smp.check(xml.replace('name="Ear0З"', 'name="Ear02"')
                                   .replace('name="hed"', 'name="body"')
                                   .replace('a="ghost"', 'a="body"')
                                   .replace('bodyA="Nowhere"', 'bodyA="Ear02"'), self.BONES, ["head", "body"]), [])

    def test_smp_without_shapes_checks_only_bones(self):
        from presenters import smp
        xml = '<system><bone name="Ear01"/><per-vertex-shape name="whatever"/></system>'
        self.assertEqual(smp.check(xml, self.BONES), [])

    def test_smp_broken_xml_is_one_finding(self):
        from presenters import smp
        rows = smp.check("<system><bone name='x'>", self.BONES)
        self.assertEqual([r["kind"] for r in rows], ["xml"])

    def test_cbpc_finds_unknown_nodes_and_bad_shapes(self):
        from presenters import cbpc
        text = """[ExtraOptions]
BellyBulge=3.0
[AffectedNodes]
TailBone01
TailBone09
[ColliderNodes]
NPC Head [Head]
[ConfigMap]
<
TailBone01=MBTail
TailBone02=MBTail
TailBone07=MBTail
>
MBTail.stiffness 0.03
[NPC Head [Head]]
0.0,3.0,2.0,7.0 | 0.0,3.0,2.0,7.0
1,2,3,4 & 5,6,7,8 | 1,2,3,4 & 5,6,7,8
1,2,3 | 1,2,3
[Nobody]
0,0,0,1
"""
        rows = cbpc.check(text, self.BONES)
        names = sorted((r["kind"], r["name"]) for r in rows)
        self.assertEqual(names, [("bone", "Nobody"), ("bone", "TailBone07"), ("bone", "TailBone09"),
                                 ("shape", "NPC Head [Head]")])
        self.assertIn("1,2,3 | 1,2,3", [r["problem"] for r in rows if r["kind"] == "shape"][0])
        clean = text.replace("TailBone09", "TailBone02").replace("TailBone07", "TailBone02") \
                    .replace("1,2,3 | 1,2,3\n", "").replace("[Nobody]\n0,0,0,1\n", "")
        self.assertEqual(cbpc.check(clean, self.BONES), [])

    def test_facade_skeleton_bones(self):
        import tempfile
        from common import bench, bone, grid, model
        with tempfile.TemporaryDirectory() as tmp:
            b = bench(tmp, model(grid("body", 2, 2, bones={"A": bone("A", range(4))})))
            self.assertEqual(b.skeleton_bones(), ["A"])
            b.rig = _rig() if "_rig" in globals() else b.rig
            if b.rig is not None:
                self.assertTrue(set(b.skeleton_bones()) >= set(b.rig.matrices))

