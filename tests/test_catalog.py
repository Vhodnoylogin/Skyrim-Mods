# -*- coding: utf-8 -*-
"""Обзор мешей и окружение: какие тела есть в папке, к какому подобраны морфы и куда
разрешено смотреть.

Дерево строится во временной папке из пустых файлов: каталог не открывает мешей, ему
хватает имён и первых байтов файла морфов. Ловит: потерянный суффикс веса (_0/_1),
регистр расширения, меш без пары, мусорный заголовок, принятый за формат, подпапки
из настроек, не сузившие обход, кеш обзора, переживший rescan, и ограничение под MO2,
пропустившее папку вне Data. MO2 имитируется подменой Environment.inside_mo2, игры
из реестра — подменой Environment.game_roots: ни одной настоящей папки сборки.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench import Catalog, CatalogEntry, Environment, MorphBench  # noqa: E402

TREE = {
    "meshes/a/body_0.nif": b"",
    "meshes/a/body_1.nif": b"",
    "meshes/a/body.tri": b"PIRT" + bytes(12),
    "meshes/a/head.nif": b"",
    "meshes/a/head.tri": b"FRTRI003" + bytes(8),
    "meshes/b/lonely.nif": b"",
    "meshes/b/Weird.NIF": b"",
    "meshes/b/weird.tri": b"PIRT" + bytes(4),
    "meshes/b/junk.nif": b"",
    "meshes/b/junk.tri": b"GARBAGE!",
    "other/x.nif": b"",
    "other/x.tri": b"PIRT" + bytes(4),
}
# Порядок — по имени без учёта регистра.
WITH_MORPHS = ["meshes/a/body_0.nif", "meshes/a/body_1.nif", "meshes/a/head.nif",
               "meshes/b/junk.nif", "meshes/b/Weird.NIF"]
ALL_MESHES = ["meshes/a/body_0.nif", "meshes/a/body_1.nif", "meshes/a/head.nif",
              "meshes/b/junk.nif", "meshes/b/lonely.nif", "meshes/b/Weird.NIF"]
KINDS = {"meshes/a/body_0.nif": "TRIP", "meshes/a/body_1.nif": "TRIP",
         "meshes/a/head.nif": "FRTRI", "meshes/b/junk.nif": None, "meshes/b/Weird.NIF": "TRIP"}


def make_tree(root) -> Path:
    root = Path(root)
    for rel, data in TREE.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return root


def add_mesh(root, rel: str, tri: bool = True) -> Path:
    """Дописать в дерево ещё один меш (и файл морфов TRIP рядом)."""
    nif = Path(root) / rel
    nif.parent.mkdir(parents=True, exist_ok=True)
    nif.write_bytes(b"")
    if tri:
        nif.with_suffix(".tri").write_bytes(b"PIRT" + bytes(4))
    return nif


def mo2(inside: bool):
    """Имитация запуска под MO2 (или без него) — подмена опознания usvfs."""
    return mock.patch.object(Environment, "inside_mo2", staticmethod(lambda: inside))


def games(*roots):
    """Подмена игр из реестра: список папок вместо чтения HKLM."""
    fake = [{"game": "Game %d" % i, "root": str(r)} for i, r in enumerate(roots)]
    return mock.patch.object(Environment, "game_roots", staticmethod(lambda: list(fake)))


def names(rows) -> list[str]:
    return [r["name"] for r in rows]


class TestCatalog(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_tree(self.tmp.name)

    def test_with_morphs(self):
        """Только меши с файлом морфов: body_0 и body_1 берут body.tri (суффикс веса
        отброшен), Weird.NIF находит weird.tri (регистр), junk с мусорным заголовком
        остаётся, но без формата; lonely и всё вне meshes не попадают."""
        cat = Catalog(self.root, ["meshes"], with_morphs=True)
        self.assertEqual([e.name for e in cat.entries], WITH_MORPHS)
        self.assertEqual(len(cat), 5)
        by_name = {e.name: e for e in cat.entries}
        self.assertEqual({n: e.kind for n, e in by_name.items()}, KINDS)
        self.assertTrue(all(e.has_morphs for e in cat.entries))
        self.assertEqual(by_name["meshes/a/body_0.nif"].tri, self.root / "meshes" / "a" / "body.tri")
        self.assertEqual(by_name["meshes/a/body_1.nif"].tri, self.root / "meshes" / "a" / "body.tri")
        self.assertEqual(by_name["meshes/b/Weird.NIF"].tri.name, "weird.tri")
        self.assertEqual(by_name["meshes/a/head.nif"].tri.name, "head.tri")
        for e in cat.entries:
            self.assertIsInstance(e, CatalogEntry)
            self.assertEqual(e.root, self.root)
            self.assertTrue(e.nif.is_file(), e.nif)

    def test_all_meshes(self):
        """with_morphs=False добавляет lonely — без морфов и без формата."""
        cat = Catalog(self.root, ["meshes"], with_morphs=False)
        self.assertEqual([e.name for e in cat.entries], ALL_MESHES)
        lonely = cat.get("meshes/b/lonely.nif")
        self.assertIsNone(lonely.tri)
        self.assertIsNone(lonely.kind)
        self.assertFalse(lonely.has_morphs)

    def test_dicts(self):
        """as_dicts: номер по порядку, имя прямыми косыми, папка и файл, полные пути строками."""
        rows = Catalog(self.root, ["meshes"]).as_dicts()
        self.assertEqual([r["index"] for r in rows], list(range(5)))
        for r in rows:
            self.assertEqual(set(r), {"index", "name", "nif", "tri", "kind", "folder", "file"})
            self.assertNotIn("\\", r["name"])
            self.assertNotIn("\\", r["folder"])
            self.assertEqual(r["name"], r["folder"] + "/" + r["file"])
            self.assertIsInstance(r["nif"], str)
            self.assertTrue(Path(r["nif"]).is_file(), r["nif"])
            self.assertTrue(common.is_plain(r), r)
        first = rows[0]
        self.assertEqual((first["folder"], first["file"], first["kind"]), ("meshes/a", "body_0.nif", "TRIP"))
        self.assertTrue(first["tri"].endswith("body.tri"))

    def test_get(self):
        """По номеру, по имени любыми косыми, по уникальной подстроке; неоднозначная
        подстрока, чужое имя и номер за пределами — KeyError."""
        cat = Catalog(self.root, ["meshes"])
        self.assertEqual(cat.get(0).name, "meshes/a/body_0.nif")
        self.assertEqual(cat.get(4).name, "meshes/b/Weird.NIF")
        self.assertEqual(cat.get("meshes\\a\\head.nif").name, "meshes/a/head.nif")
        self.assertEqual(cat.get("MESHES/A/HEAD.NIF").name, "meshes/a/head.nif")
        self.assertEqual(cat.get("/meshes/a/head.nif").name, "meshes/a/head.nif")
        self.assertEqual(cat.get("head").name, "meshes/a/head.nif")
        self.assertEqual(cat.get("WEIRD").name, "meshes/b/Weird.NIF")
        self.assertEqual(cat.get("body_1").name, "meshes/a/body_1.nif")
        with self.assertRaises(KeyError):
            cat.get("body")                  # body_0 и body_1
        with self.assertRaises(KeyError):
            cat.get("lonely")                # без морфов - в этом обзоре его нет
        with self.assertRaises(KeyError):
            cat.get(5)
        with self.assertRaises(KeyError):
            cat.get(-1)

    def test_find(self):
        cat = Catalog(self.root, ["meshes"])
        self.assertEqual([e.name for e in cat.find("BODY")],
                         ["meshes/a/body_0.nif", "meshes/a/body_1.nif"])
        self.assertEqual(cat.find("nothing"), [])

    def test_missing_root(self):
        with self.assertRaises(FileNotFoundError):
            Catalog(self.root / "nowhere")
        with self.assertRaises(FileNotFoundError):
            Catalog(self.root / "meshes" / "a" / "head.nif")

    def test_subdirs(self):
        """Подпапки из настроек сужают обход, пока хоть одна из них есть; иначе обходится
        весь корень — и тогда в обзор попадает other/x.nif."""
        self.assertNotIn("other/x.nif", [e.name for e in Catalog(self.root, ["meshes"]).entries])
        whole = [e.name for e in Catalog(self.root, ["nothing", "nowhere"]).entries]
        self.assertIn("other/x.nif", whole)
        self.assertEqual(whole, WITH_MORPHS + ["other/x.nif"])
        self.assertEqual([e.name for e in Catalog(self.root).entries], whole)
        self.assertEqual([e.name for e in Catalog(self.root, ["other"]).entries], ["other/x.nif"])
        both = [e.name for e in Catalog(self.root, ["other", "meshes"]).entries]
        self.assertEqual(both, whole)

    def test_entries_cached_until_rescan(self):
        cat = Catalog(self.root, ["meshes"])
        self.assertEqual(len(cat), 5)
        add_mesh(self.root, "meshes/c/new.nif")
        self.assertEqual(len(cat), 5)
        self.assertEqual(len(cat.rescan()), 6)
        self.assertEqual(cat.get("new").name, "meshes/c/new.nif")

    def test_kind_by_header_only(self):
        """Формат — по первым байтам: PIRT и вариант с нулевым байтом дают TRIP, FRTRI —
        FRTRI, что угодно ещё — None; пустой файл морфов — тоже None."""
        root = Path(self.tmp.name) / "kinds"
        for stem, head in (("p", b"PIRT"), ("z", b"\0IRT"), ("f", b"FRTRI003"),
                           ("g", b"NIF\0\0\0\0\0"), ("e", b"")):
            add_mesh(root, "meshes/%s.nif" % stem, tri=False)
            (root / "meshes" / (stem + ".tri")).write_bytes(head)
        kinds = {e.name: e.kind for e in Catalog(root, ["meshes"]).entries}
        self.assertEqual(kinds, {"meshes/p.nif": "TRIP", "meshes/z.nif": "TRIP",
                                 "meshes/f.nif": "FRTRI", "meshes/g.nif": None,
                                 "meshes/e.nif": None})

    def test_root_level_entry(self):
        """Меш прямо в корне: папка «.», имя без косых."""
        root = Path(self.tmp.name) / "flat"
        add_mesh(root, "top.nif")
        row = Catalog(root).as_dicts()[0]
        self.assertEqual((row["name"], row["folder"], row["file"]), ("top.nif", ".", "top.nif"))


class TestEnvironment(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.here = Path(self.tmp.name)

    def env(self, **overrides) -> Environment:
        return Environment(common.config(self.tmp.name, **overrides))

    def test_inside_mo2_is_bool(self):
        self.assertIs(type(Environment.inside_mo2()), bool)
        self.assertIs(type(self.env().inside_mo2()), bool)

    def test_game_roots_shape(self):
        """Список словарей game/root; каждая названная папка существует. Список может
        быть пустым — на машине без игр это не сбой."""
        roots = Environment.game_roots()
        self.assertIsInstance(roots, list)
        for g in roots:
            self.assertEqual(set(g), {"game", "root"})
            self.assertIsInstance(g["game"], str)
            self.assertTrue(Path(g["root"]).is_dir(), g)
        self.assertTrue(common.is_plain(roots))

    def test_explicit_catalog_root_wins(self):
        """catalogRoot из настроек — корень обзора и вне MO2, и под ним."""
        env = self.env(catalogRoot=str(self.here))
        for inside in (False, True):
            with mo2(inside):
                self.assertEqual(env.data_root(), self.here)
                self.assertEqual(env.describe()["dataRoot"], str(self.here))
                self.assertEqual(env.describe()["catalogRoot"], str(self.here))

    def test_outside_mo2_everything_allowed(self):
        """Вне MO2 без catalogRoot корня по умолчанию нет, а смотреть можно куда угодно."""
        with mo2(False):
            env = self.env()
            self.assertIsNone(env.data_root())
            self.assertTrue(env.allows(self.here))
            self.assertTrue(env.allows(self.here.parent))
            self.assertTrue(env.allows(self.here / "nowhere"))
            d = env.describe()
            self.assertFalse(d["insideMo2"])
            self.assertIsNone(d["dataRoot"])
            self.assertEqual(d["catalogRoot"], "")

    def test_inside_mo2_limited_to_data(self):
        """Под MO2 с catalogRoot: внутрь корня можно, наружу — нет."""
        with mo2(True):
            env = self.env(catalogRoot=str(self.here))
            self.assertEqual(env.data_root(), self.here)
            self.assertTrue(env.allows(self.here))
            self.assertTrue(env.allows(self.here / "sub"))
            self.assertTrue(env.allows(str(self.here / "sub" / "deeper")))
            self.assertFalse(env.allows(self.here.parent))
            self.assertFalse(env.allows(Path(self.tmp.name).anchor))
            self.assertTrue(env.describe()["insideMo2"])

    def test_inside_mo2_data_from_games(self):
        """Под MO2 без catalogRoot корень — Data той игры, где видна папка meshes;
        если её нет ни у кого — Data первой; без игр — None и запрет на всё."""
        first, second = self.here / "GameA", self.here / "GameB"
        (first / "Data").mkdir(parents=True)
        (second / "Data" / "meshes").mkdir(parents=True)
        with mo2(True):
            with games(first, second):
                env = self.env()
                self.assertEqual(env.data_root(), second / "Data")
                self.assertTrue(env.allows(second / "Data" / "meshes" / "x"))
                self.assertFalse(env.allows(first / "Data"))
                self.assertEqual(len(env.describe()["games"]), 2)
            with games(first):
                self.assertEqual(self.env().data_root(), first / "Data")
            with games():
                env = self.env()
                self.assertIsNone(env.data_root())
                self.assertFalse(env.allows(self.here))
                self.assertIsNone(env.describe()["dataRoot"])

    def test_describe_keys_and_types(self):
        d = self.env().describe()
        self.assertEqual(set(d), {"insideMo2", "dataRoot", "games", "catalogRoot", "candidates"})
        self.assertIs(type(d["insideMo2"]), bool)
        self.assertTrue(common.is_plain(d), d)


class TestFacadeCatalog(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = make_tree(Path(self.tmp.name) / "tree")

    def bench(self, **overrides) -> MorphBench:
        return MorphBench(common.config(self.tmp.name, **overrides))

    def test_no_root_outside_mo2(self):
        """Вне MO2 без catalogRoot корень назвать обязаны: ValueError, а не пустой список."""
        with mo2(False):
            bench = self.bench()
            with self.assertRaises(ValueError):
                bench.catalog()
            with self.assertRaises(ValueError):
                bench.catalog(None, with_morphs=False)
            with self.assertRaises(ValueError):
                bench.open_entry(0)

    def test_catalog_root_from_config(self):
        with mo2(False):
            bench = self.bench(catalogRoot=str(self.root))
            self.assertEqual(names(bench.catalog()), WITH_MORPHS)
            self.assertEqual(names(bench.catalog(None, with_morphs=False)), ALL_MESHES)
            self.assertEqual(bench.environment()["dataRoot"], str(self.root))

    def test_explicit_root_and_cache(self):
        """Обзор сканируется один раз на корень: новый файл виден только после rescan;
        with_morphs — отдельный ключ кеша."""
        with mo2(False):
            bench = self.bench()
            rows = bench.catalog(self.root)
            self.assertEqual(names(rows), WITH_MORPHS)
            self.assertTrue(common.is_plain(rows))
            add_mesh(self.root, "meshes/c/new.nif")
            self.assertEqual(names(bench.catalog(self.root)), WITH_MORPHS)
            self.assertEqual(names(bench.catalog(str(self.root))), WITH_MORPHS)
            self.assertEqual(names(bench.catalog(self.root, rescan=True)),
                             WITH_MORPHS + ["meshes/c/new.nif"])
            self.assertEqual(names(bench.catalog(self.root, with_morphs=False)),
                             ALL_MESHES + ["meshes/c/new.nif"])
            with self.assertRaises(FileNotFoundError):
                bench.catalog(self.root / "nowhere")

    def test_mo2_forbids_outside_data(self):
        """Под MO2 обзор ограничен корнем Data: родитель — PermissionError, подпапка — можно."""
        data = self.root / "meshes"
        with mo2(True):
            bench = self.bench(catalogRoot=str(data))
            with self.assertRaises(PermissionError):
                bench.catalog(self.root)
            with self.assertRaises(PermissionError):
                bench.open_entry(0, self.root)
            with self.assertRaises(PermissionError):
                bench.catalog(self.root / "other")
            # Корень по умолчанию - сама Data; в ней нет подпапки «meshes», значит обходится
            # она целиком, а имена записей считаются от неё, а не от дерева.
            self.assertEqual(names(bench.catalog()),
                             [n[len("meshes/"):] for n in WITH_MORPHS])
            self.assertEqual(names(bench.catalog(data / "a")), ["body_0.nif", "body_1.nif", "head.nif"])

    def test_open_entry_opens_real_nif(self):
        """open_entry открывает меш из обзора по номеру, имени и подстроке; нужен настоящий
        NIF — его пишет PyNifly, морфы TRIP — TripFile."""
        cfg = common.config(self.tmp.name)
        pynifly = common.load_pynifly(cfg)
        TripFile = common.trip_file_class(cfg)
        verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
        folder = self.root / "meshes" / "real"
        folder.mkdir(parents=True)
        nif = common.write_nif(pynifly, folder / "tiny_0.nif", {"body": {
            "verts": verts, "tris": [(0, 1, 2), (1, 3, 2)],
            "uvs": [(0, 0), (1, 0), (0, 1), (1, 1)], "normals": [(0, 0, 1)] * 4}})
        trip = TripFile()
        moved = [(x, y, z + (1.0 if i == 3 else 0.0)) for i, (x, y, z) in enumerate(verts)]
        trip.set_morphs("body", {"Up": moved}, verts)
        tri = folder / "tiny.tri"
        trip.write(str(tri))

        with mo2(False):
            bench = MorphBench(cfg)
            rows = bench.catalog(self.root)
            index = names(rows).index("meshes/real/tiny_0.nif")
            self.assertEqual(rows[index]["kind"], "TRIP")
            summary = bench.open_entry(index, self.root)
            self.assertEqual(Path(summary["nif"]), nif)
            self.assertEqual(Path(summary["tri"]), tri)
            self.assertEqual((summary["triKind"], summary["shapes"], summary["morphs"]), ("TRIP", 1, 1))
            self.assertEqual(bench.morph_stats()[0]["vertices"], 1)
            self.assertTrue(bench.is_open())
            self.assertEqual(bench.open_entry("meshes\\real\\tiny_0.nif", self.root), summary)
            self.assertEqual(bench.open_entry("tiny", self.root), summary)
            with self.assertRaises(KeyError):
                bench.open_entry("nothing-like-this", self.root)
            with self.assertRaises(KeyError):
                bench.open_entry(999, self.root)


if __name__ == "__main__":
    common.main()
