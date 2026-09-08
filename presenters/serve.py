"""Слой показа: та же страница, но с локального порта и с выбором модели.

Файл с диска держит одно тело, и чтобы посмотреть другое, страницу надо собрать заново.
Сервер снимает это ограничение: он держит фасад открытым, отдаёт страницу по запросу
и по запросу же открывает в фасаде другой меш из обзора. Всё, что он умеет, - вызовы
фасада: `catalog`, `open_entry`, `environment` и упаковка `WebPage`. Ни одного вычисления
здесь нет, как и в остальных слоях.

Стандартная библиотека и ничего сверх неё: `ThreadingHTTPServer` на порту из настроек.
Фасад один и не потокобезопасен, поэтому каждый запрос берёт замок на всё время работы
с ним. Страница, которую отдаёт сервер, обращается только к нему самому - переходом
на другой запрос `/?name=...`; запросов наружу у неё нет, как и у файла с диска.

Маршруты:

    GET /                                  страница с открытым телом (или пустым холстом)
    GET /?name=<путь от корня>&root=<папка>  открыть меш по имени и отдать страницу
    GET /?index=N&root=<папка>&all=1       ...по номеру в обзоре; all=1 - обзор и без морфов
    GET /?root=<папка>                     страница со списком другой папки
    GET /api/environment                   bench.environment()
    GET /api/catalog?root=&all=0|1&rescan=0|1   bench.catalog(...)
    GET /api/payload?index=|name=&root=    open_entry, затем WebPage(bench).payload()

Ошибки в /api/* - JSON {"error": ...} с кодом: 400 - запрос не разобран или корень
не задан, 404 - нет записи или папки, 403 - под MO2 папка вне Data игры. На странице
та же ошибка показывается текстом в разделе «Модель».
"""
from __future__ import annotations

import json
import sys
import threading
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .web import WebPage

_TRUE = ("1", "true", "yes", "on", "да")


class RequestError(Exception):
    """Запрос, который нельзя исполнить: код ответа и текст, понятный человеку."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = int(status)
        self.message = message


def _status_of(exc: BaseException) -> int:
    """Код ответа по исключению фасада: чем именно не угодил запрос, знает фасад,
    а какой это код - слой."""
    if isinstance(exc, RequestError):
        return exc.status
    if isinstance(exc, PermissionError):
        return 403
    if isinstance(exc, (KeyError, FileNotFoundError)):
        return 404
    if isinstance(exc, (ValueError, TypeError, RuntimeError)):
        return 400
    return 500


def _message(exc: BaseException) -> str:
    """Текст исключения без обёртки KeyError, которая заключает его в кавычки."""
    if exc.args and isinstance(exc.args[0], str):
        return exc.args[0]
    return str(exc) or exc.__class__.__name__


class Query:
    """Разобранная строка запроса: корень, ключ записи, флаги. Каждое значение - последнее
    из повторённых, пустое - как отсутствующее."""

    def __init__(self, raw: str):
        self.values = {k: v[-1] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def get(self, key: str, default=None):
        value = self.values.get(key)
        return default if value is None or value == "" else value

    def flag(self, key: str) -> bool:
        return str(self.get(key, "0")).strip().lower() in _TRUE

    @property
    def root(self) -> str | None:
        """Папка обзора из запроса либо None - корень сервера."""
        return self.get("root")

    @property
    def key(self):
        """Что открыть: номер записи (`index`) или имя (`name`); None - ничего."""
        index = self.get("index")
        if index is not None:
            try:
                return int(index)
            except ValueError:
                raise RequestError(400, "index должен быть целым числом, а не %r" % index)
        return self.get("name")


class WebServer:
    """Сервер страницы поверх фасада.

    Корень обзора задаётся при старте: явной папкой либо умолчанием окружения (под MO2 -
    Data игры). Проверяет его сам фасад, и вне MO2 без папки он откажет ValueError -
    её и увидит тот, кто запустил. Порт занимается сразу, чтобы `url` был верен ещё до
    `run()` - в том числе для порта 0, который выбирает система.
    """

    def __init__(self, bench, root=None, host=None, port=None, with_morphs: bool = True):
        self.bench = bench
        self.cfg = bench.cfg
        self.with_morphs = bool(with_morphs)
        self.host = str(host or self.cfg["serveHost"])
        self.lock = threading.Lock()
        # Корень: фасад проверяет его и делает первый обход - страница всё равно попросит список.
        bench.catalog(root, self.with_morphs)
        self.root = Path(root) if root is not None else Path(bench.environment()["dataRoot"])
        self.httpd = ThreadingHTTPServer(
            (self.host, int(self.cfg["servePort"] if port is None else port)),
            partial(_Handler, self))
        self.httpd.daemon_threads = True
        self.port = int(self.httpd.server_address[1])
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return "http://%s:%d/" % (self.host, self.port)

    # ---- жизнь сервера ----------------------------------------------------------------
    def run(self, open_browser: bool = True) -> None:
        """Обслуживать до Ctrl+C; по желанию сразу открыть страницу в браузере."""
        if open_browser:
            webbrowser.open(self.url)
        try:
            self.httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def start(self) -> "WebServer":
        """Обслуживать в фоновом потоке - для проверок и для клиентов, которым нужен
        и сервер, и своя работа рядом."""
        if self._thread is None:
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        if self._thread is not None:
            self.httpd.shutdown()
            self._thread.join()
            self._thread = None
        self.close()

    def close(self) -> None:
        self.httpd.server_close()

    # ---- ответы: каждый - вызовы фасада под замком ------------------------------------
    def _root_of(self, query: Query) -> str:
        """Папка обзора для запроса: названная в нём либо корень сервера. Фасаду None
        значит «умолчание окружения», а у сервера умолчание своё - его корень."""
        return query.root if query.root is not None else str(self.root)

    def api_environment(self) -> dict:
        with self.lock:
            return self.bench.environment()

    def api_catalog(self, query: Query) -> list[dict]:
        with self.lock:
            return self.bench.catalog(self._root_of(query), with_morphs=not query.flag("all"),
                                      rescan=query.flag("rescan"))

    def api_payload(self, query: Query) -> dict:
        with self.lock:
            key = query.key
            if key is not None:
                self.bench.open_entry(key, self._root_of(query), not query.flag("all"))
            if not self.bench.is_open():
                raise RequestError(400, "меш не открыт: назовите его ключом name= или index=")
            return WebPage(self.bench).payload()

    def page(self, query: Query) -> tuple[str, int]:
        """Страница по запросу: список мешей под корнем, открытие названного тела, и всё,
        что не удалось, - текстом на панели, а не пустым ответом. Список при неудаче
        берётся по корню сервера, чтобы выбирать было из чего."""
        with_morphs = not query.flag("all")
        error, status = None, 200
        with self.lock:
            bench = self.bench
            root = self._root_of(query)
            shown_root = Path(root)
            try:
                catalog = bench.catalog(root, with_morphs)
                key = query.key
                if key is not None:
                    bench.open_entry(key, root, with_morphs)
            except Exception as e:  # noqa: BLE001 - любой отказ фасада показывается текстом
                error, status = _message(e), _status_of(e)
                try:
                    catalog = bench.catalog(str(self.root), with_morphs)
                except Exception:  # noqa: BLE001
                    catalog = []
                shown_root = self.root
            page = WebPage(bench, server=True, catalog=catalog, environment=bench.environment(),
                           root=str(shown_root), with_morphs=with_morphs, error=error)
            return page.html(), status

    def __repr__(self) -> str:
        return "WebServer(%s, корень=%s)" % (self.url, self.root)


class _Handler(BaseHTTPRequestHandler):
    """Разбор пути и отправка ответа; содержание - у WebServer."""

    server_version = "morphbench/1"

    def __init__(self, owner: WebServer, *args, **kwargs):
        self.owner = owner
        super().__init__(*args, **kwargs)

    # ---- отправка ---------------------------------------------------------------------
    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, data, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send(body, "application/json; charset=utf-8", status)

    def _send_html(self, html: str, status: int = 200) -> None:
        self._send(html.encode("utf-8"), "text/html; charset=utf-8", status)

    # ---- маршруты ---------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - имя задаёт http.server
        url = urlsplit(self.path)
        query = Query(url.query)
        owner = self.owner
        try:
            if url.path == "/":
                html, status = owner.page(query)
                self._send_html(html, status)
            elif url.path == "/api/environment":
                self._send_json(owner.api_environment())
            elif url.path == "/api/catalog":
                self._send_json(owner.api_catalog(query))
            elif url.path == "/api/payload":
                self._send_json(owner.api_payload(query))
            elif url.path == "/favicon.ico":
                # Значок у страницы встроенный; браузеры всё равно спрашивают - молча пусто.
                self.send_response(204)
                self.end_headers()
            else:
                raise RequestError(404, "нет такого пути: %s" % url.path)
        except Exception as e:  # noqa: BLE001 - любой отказ уходит клиенту кодом и текстом
            self._send_json({"error": _message(e)}, _status_of(e))

    def log_message(self, fmt, *args) -> None:
        """Строка журнала без падения на консоли, которой чужд UTF-8."""
        line = "%s - %s\n" % (self.address_string(), fmt % args)
        try:
            sys.stderr.write(line)
        except UnicodeEncodeError:
            sys.stderr.write(line.encode("ascii", "replace").decode("ascii"))
