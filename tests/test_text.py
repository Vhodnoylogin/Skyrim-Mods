# -*- coding: utf-8 -*-
"""Слой показа для консоли: таблица из словарей фасада, ничего не считая сама.

Ловит перевод значений в текст: булево — «да/нет», None — прочерк, дробь — два знака,
охват — пары «от..до» по осям; и ровные столбцы, без которых таблицу не прочесть.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from presenters import text  # noqa: E402


class TestTable(unittest.TestCase):

    def test_empty(self):
        self.assertEqual(text.table([], [("a", "A")]), "пусто")
        self.assertEqual(text.table([], [("a", "A")], "нет строк"), "нет строк")

    def test_cells(self):
        rows = [{"name": "fur", "ok": True, "gap": None, "ratio": 1.5,
                 "bounds": {"min": [0.0, 0.0, 0.0], "max": [1.0, 2.5, 0.0]}, "list": ["a", "b"]}]
        cols = [("name", "часть"), ("ok", "да?"), ("gap", "нет"), ("ratio", "доля"),
                ("bounds", "охват"), ("list", "список")]
        lines = text.table(rows, cols).splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(len({len(line) for line in lines}), 1, lines)
        cells = lines[2].split("  ")
        cells = [c.strip() for c in cells if c.strip()]
        self.assertEqual(cells, ["fur", "да", "-", "1.50", "0..1 0..2.5 0..0", "a, b"])
        self.assertTrue(lines[0].startswith("часть"))
        self.assertTrue(set(lines[1]) <= {"-", " "})

    def test_false_and_missing_key(self):
        lines = text.table([{"ok": False}], [("ok", "ok"), ("absent", "нет такого")]).splitlines()
        self.assertEqual([c for c in lines[2].split(" ") if c], ["нет", "-"])


class TestSummary(unittest.TestCase):

    def test_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = common.bench(tmp, common.sample_model(), common.sample_morphs())
            out = text.summary(bench.summary())
        self.assertIn("memory.nif", out)
        self.assertIn("(TRIP)", out)
        self.assertIn("частей:   2,  вершин: 32,  костей: 3,  ползунков: 4", out)
        self.assertIn("0..3 0..3 0..1", out)

    def test_without_morphs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = text.summary(common.bench(tmp, common.sample_model(), None).summary())
        self.assertIn("морфы:    нет", out)
        self.assertNotIn("(", out.splitlines()[1])


if __name__ == "__main__":
    common.main()
