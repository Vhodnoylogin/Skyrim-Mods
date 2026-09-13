# -*- coding: utf-8 -*-
"""Локальная страница со списком мешей: сервер поверх фасада отвечает JSON и HTML.

Сервер поднимается фоновым потоком (`WebServer.start`) на порту 0 — систему просят дать
свободный — с корнем обзора во временной папке, где лежит настоящий крошечный NIF
с файлом морфов TRIP (их пишут PyNifly и TripFile). Ловит: окружение, обзор и payload,
не отданные как JSON; страницу без холста; url, не знающий выбранного системой порта;
несуществующий корень или запись, ответившие 200 или не-JSON; папку вне Data под MO2,
пропущенную без 403; сервер, который не останавливается. Без serve.py — пропуск.
"""
import contextlib
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from test_catalog import games, mo2  # noqa: E402

from morphbench import MorphBench  # noqa: E402

try:
    from presenters import serve
    from presenters.serve import WebServer
except ImportError as e:  # noqa: N816
    serve = None
    WebServer = None
    IMPORT_ERROR = e

# Без прокси: адрес местный, а переменные окружения могут завернуть его наружу.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url: str):
    """(код, тип содержимого, тело) — и для ошибочных кодов тоже."""
    try:
        with _OPENER.open(url, timeout=10) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def quiet():
    """Строки журнала запросов — не в вывод проверок. Глушится одна точка записи,
    через которую идут и запросы, и ошибки, и сообщения http.server."""
    handler = getattr(serve, "_Handler", None)
    if handler is None or not hasattr(handler, "_write"):
        return contextlib.nullcontext()
    return mock.patch.object(handler, "_write", lambda self, *a: None)


def write_body(cfg, folder: Path) -> tuple[Path, Path]:
    """tiny_0.nif и tiny.tri рядом: квадрат из двух треугольников и морф Up на одной вершине."""
    pynifly = common.load_pynifly(cfg)
    TripFile = common.trip_file_class(cfg)
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
    nif = common.write_nif(pynifly, folder / "tiny_0.nif", {"body": {
        "verts": verts, "tris": [(0, 1, 2), (1, 3, 2)],
        "uvs": [(0, 0), (1, 0), (0, 1), (1, 1)], "normals": [(0, 0, 1)] * 4}})
    trip = TripFile()
    moved = [(x, y, z + (1.0 if i == 3 else 0.0)) for i, (x, y, z) in enumerate(verts)]
    trip.set_morphs("body", {"Up": moved}, verts)
    tri = folder / "tiny.tri"
    trip.write(str(tri))
    return nif, tri


NAME = "meshes/tiny/tiny_0.nif"


@unittest.skipIf(WebServer is None, "presenters/serve.py ещё нет: %s" % (
    IMPORT_ERROR if WebServer is None else ""))
class TestWebServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cfg = common.config(cls.tmp.name, imageWidth=64, imageHeight=64)
        cls.root = Path(cls.tmp.name) / "root"
        folder = cls.root / "meshes" / "tiny"
        folder.mkdir(parents=True)
        try:
            cls.nif, cls.tri = write_body(cls.cfg, folder)
        except unittest.SkipTest:
            cls.tmp.cleanup()
            raise
        cls.quiet = quiet()
        cls.quiet.__enter__()
        cls.bench = MorphBench(cls.cfg)
        cls.server = WebServer(cls.bench, root=cls.root, host="127.0.0.1", port=0).start()
        cls.base = cls.server.url.rstrip("/")

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.quiet.__exit__(None, None, None)
        cls.tmp.cleanup()

    def json(self, path: str, expect: int = 200):
        code, ctype, body = get(self.base + path)
        self.assertEqual(code, expect, (path, body[:300]))
        self.assertIn("json", ctype.lower(), (path, ctype))
        return json.loads(body.decode("utf-8"))

    def html(self, path: str, expect: int = 200) -> str:
        code, ctype, body = get(self.base + path)
        self.assertEqual(code, expect, (path, body[:300]))
        self.assertIn("html", ctype.lower(), (path, ctype))
        return body.decode("utf-8")

    @staticmethod
    def q(**params) -> str:
        return "?" + urllib.parse.urlencode(params)

    def test_url_knows_the_port(self):
        """Порт 0 отдан системе: url и port показывают настоящий, а не ноль."""
        self.assertGreater(self.server.port, 0)
        self.assertTrue(self.base.endswith(":%d" % self.server.port), self.base)
        self.assertTrue(self.base.startswith("http://127.0.0.1:"), self.base)
        self.assertEqual(Path(self.server.root), self.root)
        self.assertIn(self.server.url, repr(self.server))

    def test_environment(self):
        data = self.json("/api/environment")
        self.assertEqual(set(data), {"insideMo2", "dataRoot", "games", "catalogRoot", "candidates", "root"})
        self.assertIs(type(data["insideMo2"]), bool)
        self.assertEqual(Path(data.pop("root")), self.root)     # корень сервера - отдельно
        self.assertEqual(data, self.bench.environment())

    def test_catalog(self):
        """Обзор по корню сервера — тот же список, что даёт фасад; root= в запросе
        меняет корень, all= и rescan= доезжают до фасада."""
        rows = self.json("/api/catalog")
        self.assertEqual([r["name"] for r in rows], [NAME])
        self.assertEqual((rows[0]["index"], rows[0]["kind"]), (0, "TRIP"))
        self.assertEqual(rows, self.bench.catalog(self.root))
        self.assertEqual([r["name"] for r in self.json("/api/catalog?all=1&rescan=1")], [NAME])
        rows = self.json("/api/catalog" + self.q(root=str(self.root / "meshes")))
        self.assertEqual([r["name"] for r in rows], ["tiny/tiny_0.nif"])

    def test_payload_opens_entry(self):
        """payload по номеру и по имени открывает меш в фасаде и отдаёт то же, что WebPage."""
        data = self.json("/api/payload?index=0")
        self.assertEqual([s["name"] for s in data["shapes"]], ["body"])
        # Страница строит кадр по этим числам, поэтому они уходят без округления.
        self.assertEqual(data["view"], self.bench.view_state(precise=True))
        self.assertIn("Up", data["deltas"])
        self.assertEqual(Path(self.bench.model.path), self.nif)
        self.assertEqual(Path(self.bench.morph_set.path), self.tri)
        by_name = self.json("/api/payload" + self.q(name=NAME))
        self.assertEqual([s["name"] for s in by_name["shapes"]], ["body"])
        # Меш открыт — payload без ключа отдаёт его же.
        self.assertEqual([s["name"] for s in self.json("/api/payload")["shapes"]], ["body"])

    def test_page(self):
        """Страница с холстом и без единой ссылки наружу; по index= открывает тело;
        ошибка показывается на той же странице с кодом ошибки, а не пустым ответом."""
        text = self.html("/")
        self.assertIn("<canvas", text)
        self.assertNotIn("https://", text)
        self.assertNotIn("http://", text.replace(self.base, ""))
        self.assertIn("<canvas", self.html("/?index=0"))
        self.assertIn("tiny_0.nif", self.html("/?index=0"))
        self.assertIn("<canvas", self.html("/?name=nothing-like-this", 404))
        self.assertIn("<canvas", self.html("/" + self.q(root=str(self.root / "nowhere")), 404))
        self.assertIn("<canvas", self.html("/?index=zzz", 400))

    def test_errors_are_json_with_codes(self):
        """Несуществующий корень и запись — 404, кривой номер — 400, чужой путь — 404;
        всё — JSON с ключом error."""
        for path, code in (("/api/catalog" + self.q(root=str(self.root / "nowhere")), 404),
                           ("/api/payload?index=99", 404),
                           ("/api/payload?name=nothing-like-this", 404),
                           ("/api/payload?index=zzz", 400),
                           ("/api/nothing", 404)):
            data = self.json(path, code)
            self.assertIn("error", data, path)
            self.assertIsInstance(data["error"], str)

    def test_mo2_forbids_outside_data(self):
        """Под MO2 (имитация) корень вне Data игры — 403 с JSON; окружение об этом знает."""
        game = Path(self.tmp.name) / "Game"
        (game / "Data" / "meshes").mkdir(parents=True)
        with mo2(True), games(game):
            self.assertTrue(self.json("/api/environment")["insideMo2"])
            self.assertEqual(self.json("/api/environment")["dataRoot"], str(game / "Data"))
            data = self.json("/api/catalog" + self.q(root=str(self.root)), 403)
            self.assertIn("error", data)
            self.assertEqual(self.json("/api/catalog" + self.q(root=str(game / "Data"))), [])
        self.assertFalse(self.json("/api/environment")["insideMo2"])

    def test_start_and_stop(self):
        """Второй сервер на порту 0: без открытого меша payload — 400, страница — 200;
        после stop() порт не отвечает, а поток завершён."""
        bench = MorphBench(self.cfg)
        server = WebServer(bench, root=self.root, host="127.0.0.1", port=0).start()
        try:
            base = server.url.rstrip("/")
            self.assertNotEqual(server.port, self.server.port)
            code, ctype, body = get(base + "/api/payload")
            self.assertEqual(code, 400, body[:300])
            self.assertIn("error", json.loads(body.decode("utf-8")))
            code, ctype, body = get(base + "/")
            self.assertEqual(code, 200)
            self.assertIn("<canvas", body.decode("utf-8"))
        finally:
            server.stop()
        with self.assertRaises(urllib.error.URLError):
            get(base + "/api/environment")
        # Первый сервер остановка второго не задела.
        self.json("/api/environment")


@unittest.skipIf(WebServer is None, "нет presenters/serve.py")
class TestDeadJournal(unittest.TestCase):
    """Труба к тому, кто запустил сервер, закрылась — обслуживание продолжается.

    Так выглядит снятое окно запуска: сервер пишет строку журнала в трубу, читателя
    у которой больше нет. Писалась она внутри отправки ответа, до заголовков, поэтому
    падение уносило с собой каждый обслуживаемый запрос: клиент получал обрыв связи
    без единого слова, а работа при этом делалась. Теперь выбывает один приёмник.
    """

    def test_serving_survives_and_the_other_sink_keeps_the_record(self):
        from morphbench.journal import Journal, ListSink, StreamSink
        from test_journal import DeadStream

        with tempfile.TemporaryDirectory() as tmp:
            bench = common.bench(tmp, common.sample_model(), None)
            dead = StreamSink(DeadStream(), "debug")
            kept = ListSink("debug")
            server = WebServer(bench, root=tmp, host="127.0.0.1", port=0,
                               journal=Journal([dead, kept], "serve")).start()
            try:
                base = server.url.rstrip("/")
                for _ in range(3):
                    code, ctype, body = get(base + "/api/catalog")
                    self.assertEqual(code, 200, body[:300])
                code, ctype, body = get(base + "/")
                self.assertEqual(code, 200)
                # Отказ отправки тоже не должен ронять сервер: 404 приходит как 404.
                self.assertEqual(get(base + "/api/no-such-path")[0], 404)
            finally:
                server.stop()
                server.close()
            self.assertFalse(dead.alive)
            lines = "\n".join(kept.lines)
            self.assertIn("/api/catalog", lines)
            self.assertIn("выбыл", lines)


if __name__ == "__main__":
    common.main()
