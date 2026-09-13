# -*- coding: utf-8 -*-
"""Установка: манифест зависимостей и скрипт, который ищет их за человека.

Ловит: зависимость, опознанную по одному имени папки без нужных файлов внутри; найденный
путь, не вписанный в настройки; вписанный поверх значения, которое человек поставил сам;
необязательную зависимость, посчитанную обязательной; код выхода, не отличающий «всё есть»
от «не хватает». Отдельно — что установщик работает на голом Python: он не должен
импортировать ни верстак, ни numpy, иначе не запустится ровно тогда, когда нужен.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

import install  # noqa: E402

HOME = Path(install.__file__).resolve().parent


def manifest(*deps) -> dict:
    return {"dependencies": list(deps)}


def folder_dep(**kw) -> dict:
    dep = {"name": "Штука", "kind": "folder", "why": "чтобы было", "required": True,
           "setting": "штука", "proof": ["inside.txt"], "search": []}
    dep.update(kw)
    return dep


class TestChecks(unittest.TestCase):

    def test_runtime_compares_versions(self):
        ok = install.check({"name": "Python", "kind": "runtime", "minimum": "3.0"}, HOME, [])
        self.assertTrue(ok.found)
        high = install.check({"name": "Python", "kind": "runtime", "minimum": "99.0"}, HOME, [])
        self.assertFalse(high.found)
        self.assertIn("нужно не ниже 99.0", high.detail)

    def test_package_found_by_import_name(self):
        # У pillow имя пакета и имя модуля разные - проверяется именно import.
        self.assertTrue(install.check({"name": "json", "kind": "python-package"}, HOME, []).found)
        miss = install.check({"name": "нетуТакого", "kind": "python-package",
                              "import": "netu_takogo_modulya"}, HOME, [])
        self.assertFalse(miss.found)

    def test_folder_needs_its_proof_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "io_scene_nifly"
            wrong.mkdir()
            dep = folder_dep(search=[str(Path(tmp) / "*")])
            # Имя совпало, содержимого нет - не она.
            c = install.check(dep, HOME, [])
            self.assertFalse(c.found)
            self.assertIn("без нужных файлов", c.detail)
            (wrong / "inside.txt").write_text("x", encoding="utf-8")
            c = install.check(dep, HOME, [])
            self.assertTrue(c.found)
            self.assertEqual(Path(c.where), wrong)

    def test_extra_search_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "своё место"
            folder.mkdir()
            (folder / "inside.txt").write_text("x", encoding="utf-8")
            c = install.check(folder_dep(), HOME, [str(Path(tmp) / "*")])
            self.assertTrue(c.found)

    def test_bundled_is_not_searched(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / "vendor").mkdir()
            dep = folder_dep(bundled="vendor", search=["не-ищи-здесь/*"])
            c = install.check(dep, home, [])
            self.assertTrue(c.found)
            self.assertIn("внутрь пакета", c.detail)

    def test_optional_does_not_block(self):
        miss = install.check({"name": "рисовалка", "kind": "python-package",
                              "import": "netu_takogo", "required": False}, HOME, [])
        self.assertFalse(miss.found)
        self.assertFalse(miss.blocking)


class TestApply(unittest.TestCase):

    def test_writes_found_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "нашлось"
            folder.mkdir()
            (folder / "inside.txt").write_text("x", encoding="utf-8")
            config = Path(tmp) / "morphbench.json"
            c = install.check(folder_dep(search=[str(Path(tmp) / "нашлось")]), HOME, [])
            written = install.apply_settings([c], config)
            self.assertEqual(len(written), 1)
            self.assertEqual(json.loads(config.read_text(encoding="utf-8"))["штука"], str(folder))

    def test_keeps_what_the_human_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "нашлось"
            folder.mkdir()
            (folder / "inside.txt").write_text("x", encoding="utf-8")
            mine = Path(tmp) / "моё"
            mine.mkdir()
            config = Path(tmp) / "morphbench.json"
            config.write_text(json.dumps({"штука": str(mine), "другое": 1}), encoding="utf-8")
            c = install.check(folder_dep(search=[str(Path(tmp) / "нашлось")]), HOME, [])
            self.assertEqual(install.apply_settings([c], config), [])
            values = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(values["штука"], str(mine))
            self.assertEqual(values["другое"], 1)   # чужие ключи не потеряны

    def test_replaces_a_path_that_no_longer_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "нашлось"
            folder.mkdir()
            (folder / "inside.txt").write_text("x", encoding="utf-8")
            config = Path(tmp) / "morphbench.json"
            config.write_text(json.dumps({"штука": str(Path(tmp) / "уехало")}), encoding="utf-8")
            c = install.check(folder_dep(search=[str(Path(tmp) / "нашлось")]), HOME, [])
            self.assertEqual(len(install.apply_settings([c], config)), 1)


class TestManifestAndRun(unittest.TestCase):

    def test_shipped_manifest_is_readable_and_complete(self):
        data = json.loads((HOME / "dependencies.json").read_text(encoding="utf-8-sig"))
        deps = data["dependencies"]
        self.assertTrue(deps)
        for dep in deps:
            self.assertTrue(dep.get("name"), dep)
            self.assertTrue(dep.get("why"), "у %s нет поля why" % dep.get("name"))
            self.assertIn(install.dep_kind(dep), ("runtime", "python-package", "folder"), dep)
            self.assertTrue(dep.get("license"), "у %s не назван род лицензии" % dep["name"])
        self.assertIn("PyNifly", [d["name"] for d in deps])

    def test_runs_on_bare_python(self):
        """Установщик не должен тянуть за собой ни верстак, ни numpy: он нужен именно
        тогда, когда их ещё нет. Запуск с -I: без пользовательских путей и переменных."""
        out = subprocess.run([sys.executable, "-I", str(HOME / "install.py"), "--json"],
                             capture_output=True, text=True, encoding="utf-8", errors="replace",
                             cwd=str(HOME))
        self.assertIn(out.returncode, (0, 1), out.stderr[:400])
        data = json.loads(out.stdout)
        self.assertIn("dependencies", data)
        names = [d["name"] for d in data["dependencies"]]
        self.assertIn("PyNifly", names)

    def test_exit_code_tells_ready_from_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "deps.json"
            bad.write_text(json.dumps(manifest(
                {"name": "нетуТакого", "kind": "python-package", "import": "netu_takogo",
                 "why": "проверка", "required": True, "license": "нет"})), encoding="utf-8")
            code = install.main(["--manifest", str(bad), "--config", str(Path(tmp) / "cfg.json")])
            self.assertEqual(code, 1)
            good = Path(tmp) / "ok.json"
            good.write_text(json.dumps(manifest(
                {"name": "json", "kind": "python-package", "why": "проверка",
                 "required": True, "license": "нет"})), encoding="utf-8")
            self.assertEqual(install.main(["--manifest", str(good),
                                           "--config", str(Path(tmp) / "cfg.json")]), 0)


if __name__ == "__main__":
    common.main()
