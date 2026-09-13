# -*- coding: utf-8 -*-
"""Сервер без корня и передача корня уже поднятому серверу.

`serve` без ключей обязан подняться и без папки: вне MO2 умолчания у корня нет, и страница
выходит с пустым списком. Корень называют потом - запросом `/api/root`, которым пользуется
второй `serve` (из-под MO2 - точка входа). `ServerLink` с той стороны различает свободный
порт, наш сервер и чужую программу. Ловит: сервер, требующий корень при старте; список
без корня, отданный не 400; `/api/root`, не проверивший папку; ServerLink, принявший чужой
HTTP-сервер за свой.
"""
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
from test_serve import get, quiet, write_body  # noqa: E402

from morphbench import MorphBench  # noqa: E402

try:
    from presenters.serve import RequestError, ServerLink, WebServer
except ImportError as e:  # noqa: N816
    WebServer = ServerLink = RequestError = None
    IMPORT_ERROR = e


@unittest.skipIf(WebServer is None, "presenters/serve.py не загрузился: %s" % (
    IMPORT_ERROR if WebServer is None else ""))
class TestRootlessServer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cfg = common.config(cls.tmp.name, imageWidth=64, imageHeight=64)
        cls.root = Path(cls.tmp.name) / "root"
        folder = cls.root / "meshes" / "tiny"
        folder.mkdir(parents=True)
        try:
            write_body(cls.cfg, folder)
        except unittest.SkipTest:
            cls.tmp.cleanup()
            raise
        cls.quiet = quiet()
        cls.quiet.__enter__()
        cls.bench = MorphBench(cls.cfg)
        cls.server = WebServer(cls.bench, host="127.0.0.1", port=0).start()
        cls.base = cls.server.url.rstrip("/")
        cls.link = ServerLink("127.0.0.1", cls.server.port)

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

    def test_01_starts_without_a_root(self):
        """Вне MO2 и без catalogRoot корня нет - и это не отказ, а пустой список."""
        if self.bench.environment()["insideMo2"]:
            self.skipTest("под MO2 у корня есть умолчание - Data игры")
        self.assertIsNone(self.server.root)
        self.assertIn("не задан", repr(self.server))
        self.assertEqual(self.json("/api/root"), {"root": None, "meshes": None})
        self.assertIsNone(self.json("/api/environment")["root"])
        self.assertIn("no browse root", self.json("/api/catalog", 400)["error"])
        self.assertIn("no browse root", self.json("/api/payload?index=0", 400)["error"])
        code, ctype, body = get(self.base + "/")
        self.assertEqual(code, 200)
        self.assertIn(b"<canvas", body)

    def test_02_link_recognises_its_own_server(self):
        self.assertEqual(self.link.probe(), "ours")
        env = self.link.environment()
        self.assertEqual(env["insideMo2"], self.bench.environment()["insideMo2"])
        self.assertEqual(self.link.url, self.server.url)

    def test_03_root_is_checked_before_it_is_taken(self):
        with self.assertRaises(RequestError) as ctx:
            self.link.set_root(str(self.root / "nowhere"))
        self.assertEqual(ctx.exception.status, 404)
        self.assertIn("no folder to browse", ctx.exception.message)
        self.assertEqual(self.json("/api/root")["root"], self.server.root and str(self.server.root))

    def test_03b_probe_does_not_wait_for_the_facade_lock(self):
        """Пока сервер держит замок на обходе большой папки, опознание отвечает сразу:
        окружение читается без замка. Корень за это время не узнать - и это не «чужой»."""
        with self.server.lock:
            self.assertEqual(self.link.probe(), "ours")
            status = self.link.status()
        self.assertEqual(status["state"], "ours")
        self.assertIn("insideMo2", status)

    def test_03c_second_server_on_the_same_port_fails_loudly(self):
        """SO_REUSEADDR на Windows пустил бы второй сервер на тот же порт молча."""
        with self.assertRaises(OSError):
            WebServer(self.bench, host="127.0.0.1", port=self.server.port)

    def test_04_handing_over_the_root_fills_the_list(self):
        got = self.link.set_root(str(self.root))
        self.assertEqual((Path(got["root"]), got["meshes"]), (self.root, 1))
        self.assertEqual(Path(self.server.root), self.root)
        rows = self.json("/api/catalog")
        self.assertEqual([r["name"] for r in rows], ["meshes/tiny/tiny_0.nif"])
        self.assertEqual(Path(self.link.environment()["root"]), self.root)
        code, ctype, body = get(self.base + "/?index=0")
        self.assertEqual(code, 200)
        self.assertIn(b"tiny_0.nif", body)


@unittest.skipIf(WebServer is None, "presenters/serve.py не загрузился")
class TestShutdown(unittest.TestCase):
    """Остановка по запросу: ответ уходит, цикл завершается, порт освобождается."""

    def test_shutdown_stops_the_loop_and_answers_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            bench = MorphBench(common.config(tmp))
            with quiet():
                server = WebServer(bench, host="127.0.0.1", port=0).start()
                link = ServerLink("127.0.0.1", server.port, timeout=2.0)
                try:
                    status = link.status()
                    self.assertEqual((status["state"], status["url"]), ("ours", server.url))
                    self.assertIsNone(status["root"])
                    got = link.shutdown()
                    self.assertEqual(got, {"stopping": True, "url": server.url})
                    # Цикл обслуживания остановился сам: поток выходит без stop().
                    server._thread.join(5.0)
                    self.assertFalse(server._thread.is_alive())
                finally:
                    server.stop()
            self.assertEqual(link.probe(), "free")
            self.assertEqual(link.status()["state"], "free")


@unittest.skipIf(ServerLink is None, "presenters/serve.py не загрузился")
class TestLinkProbe(unittest.TestCase):
    def test_free_port(self):
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.assertEqual(ServerLink("127.0.0.1", port, timeout=1.0).probe(), "free")

    def test_wildcard_host_is_dialled_on_loopback(self):
        """Слушать на 0.0.0.0 можно, набирать этот адрес нельзя: url и опрос идут на loopback."""
        with tempfile.TemporaryDirectory() as tmp:
            bench = MorphBench(common.config(tmp))
            with quiet():
                server = WebServer(bench, host="0.0.0.0", port=0).start()
                try:
                    self.assertTrue(server.url.startswith("http://127.0.0.1:"), server.url)
                    link = ServerLink("0.0.0.0", server.port, timeout=2.0)
                    self.assertEqual(link.url, server.url)
                    self.assertEqual(link.probe(), "ours")
                finally:
                    server.stop()

    def test_silent_server_is_slow_not_busy(self):
        """Соединение есть, ответа нет: это «медленно», а не «чужая программа»."""
        import socket
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)         # очередь на несколько неотвеченных соединений подряд
        try:
            link = ServerLink("127.0.0.1", listener.getsockname()[1], timeout=0.5)
            self.assertEqual(link.probe(), "slow")
            self.assertEqual(link.status()["state"], "slow")
        finally:
            listener.close()

    def test_stranger_on_the_port(self):
        """Чужой HTTP-сервер отвечает, но не подписывается morphbench - это «занято»."""
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Quiet)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            link = ServerLink("127.0.0.1", httpd.server_address[1], timeout=2.0)
            self.assertEqual(link.probe(), "busy")
            with self.assertRaises(Exception):
                link.environment()
        finally:
            httpd.shutdown()
            thread.join()
            httpd.server_close()


if __name__ == "__main__":
    common.main()
