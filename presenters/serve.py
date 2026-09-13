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

Корень обзора необязателен: сервер поднимается и без него - с пустым списком и полем
для папки на странице, - а назвать корень можно потом, запросом `/api/root`. Так его
передаёт запуск из-под MO2: `ServerLink` с той стороны спрашивает, жив ли сервер,
и отдаёт ему Data игры.

Маршруты:

    GET /                                  страница с открытым телом (или пустым холстом)
    GET /?name=<путь от корня>&root=<папка>  открыть меш по имени и отдать страницу
    GET /?index=N&root=<папка>&all=1       ...по номеру в обзоре; all=1 - обзор и без морфов
    GET /?root=<папка>                     страница со списком другой папки
    GET /api/environment                   bench.environment()
    GET /api/catalog?root=&all=0|1&rescan=0|1   bench.catalog(...)
    GET /api/payload?index=|name=&root=    open_entry, затем WebPage(bench).payload()
    GET /api/root?root=<папка>             сделать папку корнем сервера; без root - какой сейчас
    GET /api/shutdown                      остановить сервер: ответ уходит, цикл завершается

Ошибки в /api/* - JSON {"error": ...} с кодом: 400 - запрос не разобран или корень
не задан, 404 - нет записи или папки, 403 - под MO2 папка вне Data игры. На странице
та же ошибка показывается текстом в разделе «Модель».
"""
from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from morphbench.environment import process_alive, wait_process
from morphbench.i18n import t
from morphbench.journal import Journal, from_config

from .web import WebPage

_TRUE = ("1", "true", "yes", "on", "да")
#: Подпись в заголовке Server: по ней `ServerLink` отличает свой сервер от чужой программы
#: на том же порту.
SERVER_NAME = "morphbench/1"
#: Адреса «слушать на всех интерфейсах»: набирать такой адрес нельзя - Windows отвечает
#: WSAEADDRNOTAVAIL, - поэтому к серверу на нём обращаются по loopback.
_WILDCARD = ("0.0.0.0", "", "::", "*")


def dial_host(host) -> str:
    """Адрес, по которому к серверу обращаются, если он слушает на `host`."""
    host = str(host or "").strip()
    return "127.0.0.1" if host in _WILDCARD else host


class RequestError(ValueError):
    """Запрос, который нельзя исполнить: код ответа и текст, понятный человеку.
    Это отказ, а не сбой, - потому ValueError: командная строка печатает его одной строкой."""

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
                raise RequestError(400, t("serve.indexNotANumber", value=index))
        return self.get("name")


class _Server(ThreadingHTTPServer):
    """Второй сервер на том же порту обязан упасть, а не молча сесть рядом: SO_REUSEADDR,
    который http.server включает по умолчанию, на Windows разрешает такой второй bind."""

    allow_reuse_address = False


class WebServer:
    """Сервер страницы поверх фасада.

    Корень обзора: явная папка, иначе умолчание окружения (под MO2 - Data игры), иначе
    никакого - сервер поднимается с пустым списком, и папку называют на странице или
    запросом `/api/root`. Явную папку проверяет фасад сразу: вне MO2 несуществующая
    откажет FileNotFoundError, под MO2 чужая - PermissionError, и их увидит тот, кто
    запустил. Порт занимается сразу, чтобы `url` был верен ещё до `run()` - в том числе
    для порта 0, который выбирает система.
    """

    def __init__(self, bench, root=None, host=None, port=None, with_morphs: bool = True,
                 journal: Journal | None = None):
        self.bench = bench
        self.cfg = bench.cfg
        # Журнал заводится по настройкам: труба к тому, кто запустил, и файл рядом.
        # Свой передают проверки и слои, которым журнал нужен в руках.
        self.journal = journal if journal is not None else from_config(self.cfg, "serve")
        self.with_morphs = bool(with_morphs)
        self.host = str(host or self.cfg["serveHost"])
        self.lock = threading.Lock()
        self.root: Path | None = None
        if root is None:
            root = bench.environment()["dataRoot"]
        if root is not None:
            self.set_root(root)
        self.httpd = _Server(
            (self.host, int(self.cfg["servePort"] if port is None else port)),
            partial(_Handler, self))
        self.httpd.daemon_threads = True
        self.port = int(self.httpd.server_address[1])
        self._thread: threading.Thread | None = None
        self._watcher: threading.Thread | None = None

    @property
    def url(self) -> str:
        return "http://%s:%d/" % (dial_host(self.host), self.port)

    def set_root(self, root) -> dict:
        """Сделать папку корнем сервера. Фасад проверяет её и делает первый обход -
        страница всё равно попросит список."""
        rows = self.bench.catalog(root, self.with_morphs)
        self.root = Path(root)
        return {"root": str(self.root), "meshes": len(rows)}

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

    def watch_parent(self, pid: int) -> None:
        """Уйти вместе с тем, кто поднял.

        Сервер живёт в отдельном процессе, и окно запуска, снятое мирно, останавливает его
        само. Снятое ЖЁСТКО (аварийное завершение, «Снять задачу», выход из системы) -
        не успевает, и остаётся невидимый процесс: он держит порт, продолжает читать файлы
        сквозь подмену MO2, которая для него уже устарела, а MO2 его больше не считает
        запущенной программой. Хуже того, точка входа идемпотентна, и следующий запуск
        молча подключится именно к нему. Поэтому сервер ждёт своего родителя сам.

        Сторож необязателен: без номера процесса его нет и поведение прежнее - сервер,
        поднятый из консоли, ничьей смерти не ждёт.
        """
        pid = int(pid)
        if pid <= 0:
            return
        if not process_alive(pid):
            self.journal.warn(t("serve.parentGone", pid=pid))
            return

        def watch() -> None:
            wait_process(pid)
            self.journal.warn(t("serve.leavingWithParent", pid=pid))
            self.httpd.shutdown()
            # Порт отпускается здесь же. Одной остановки цикла мало: слушающее гнездо
            # осталось бы открытым, и сервер стал бы чёрной дырой - соединение
            # принимается, ответа нет, а клиент ждёт до своего предела.
            self.close()

        self._watcher = threading.Thread(target=watch, daemon=True, name="parent-watch")
        self._watcher.start()

    def stop(self) -> None:
        if self._thread is not None:
            self.httpd.shutdown()
            self._thread.join()
            self._thread = None
        self.close()

    def close(self) -> None:
        self.httpd.server_close()
        self.journal.close()

    # ---- ответы: каждый - вызовы фасада под замком ------------------------------------
    def _root_of(self, query: Query) -> str | None:
        """Папка обзора для запроса: названная в нём либо корень сервера; None - ни той,
        ни другого. Фасаду None значил бы «умолчание окружения», а у сервера умолчание
        своё - его корень, - поэтому фасад отсюда None не получает."""
        return query.root if query.root is not None else (
            None if self.root is None else str(self.root))

    def _root_required(self, query: Query) -> str:
        root = self._root_of(query)
        if root is None:
            raise RequestError(400, t("serve.rootNotGiven"))
        return root

    def api_environment(self) -> dict:
        """Без замка: окружение читается из реестра, а не из фасада, и опознание сервера
        не должно ждать, пока под замком идёт обход большой папки."""
        return dict(self.bench.environment(),
                    root=None if self.root is None else str(self.root))

    def api_catalog(self, query: Query) -> list[dict]:
        with self.lock:
            return self.bench.catalog(self._root_required(query),
                                      with_morphs=not query.flag("all"),
                                      rescan=query.flag("rescan"))

    def api_payload(self, query: Query) -> dict:
        with self.lock:
            key = query.key
            if key is not None:
                self.bench.open_entry(key, self._root_required(query), not query.flag("all"))
            if not self.bench.is_open():
                raise RequestError(400, t("serve.meshNotOpen"))
            return WebPage(self.bench).payload()

    def api_root(self, query: Query) -> dict:
        """Корень сервера: назвать новый либо спросить нынешний."""
        with self.lock:
            if query.root is not None:
                return self.set_root(query.root)
            return {"root": None if self.root is None else str(self.root),
                    "meshes": None if self.root is None else len(
                        self.bench.catalog(str(self.root), self.with_morphs))}

    def api_shutdown(self) -> dict:
        """Остановить сервер по просьбе клиента - окна запуска или `serve --stop`.

        Ответ должен уйти раньше, чем цикл обслуживания остановится, а `shutdown()` ждёт
        этот цикл и из потока запроса зваться не может, - поэтому отдельный поток."""
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()
        return {"stopping": True, "url": self.url}

    def page(self, query: Query) -> tuple[str, int]:
        """Страница по запросу: список мешей под корнем, открытие названного тела, и всё,
        что не удалось, - текстом на панели, а не пустым ответом. Список при неудаче
        берётся по корню сервера, чтобы выбирать было из чего; без корня список пуст,
        и это не ошибка - папку называют на странице."""
        with_morphs = not query.flag("all")
        error, status = None, 200
        with self.lock:
            bench = self.bench
            root = self._root_of(query)
            shown_root = root
            catalog: list[dict] = []
            try:
                if root is not None:
                    catalog = bench.catalog(root, with_morphs)
                key = query.key
                if key is not None:
                    bench.open_entry(key, self._root_required(query), with_morphs)
            except Exception as e:  # noqa: BLE001 - любой отказ фасада показывается текстом
                error, status = _message(e), _status_of(e)
                catalog = []
                if self.root is not None:
                    try:
                        catalog = bench.catalog(str(self.root), with_morphs)
                    except Exception:  # noqa: BLE001
                        catalog = []
                shown_root = None if self.root is None else str(self.root)
            page = WebPage(bench, server=True, catalog=catalog, environment=bench.environment(),
                           root=shown_root, with_morphs=with_morphs, error=error)
            return page.html(), status

    def __repr__(self) -> str:
        return "WebServer(%s, корень=%s)" % (self.url, self.root or "не задан")


class ServerLink:
    """Сторона клиента: жив ли сервер на этом адресе и наш ли он.

    Нужна запуску: `mb.py serve` сначала спрашивает, не поднят ли сервер уже, и если да -
    не поднимает второго, а отдаёт ему корень и открывает страницу. Из-под MO2 это и есть
    передача пути: процесс, запущенный MO2, видит Data игры сквозь usvfs и называет её
    серверу.
    """

    def __init__(self, host: str, port: int, timeout: float = 2.0):
        self.host = dial_host(host)
        self.port = int(port)
        self.timeout = float(timeout)
        # Без прокси: адрес местный, а переменные окружения могут завернуть его наружу.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @property
    def url(self) -> str:
        return "http://%s:%d/" % (self.host, self.port)

    def _get(self, path: str) -> dict:
        with self._opener.open(self.url.rstrip("/") + path, timeout=self.timeout) as r:
            if not str(r.headers.get("Server", "")).startswith(SERVER_NAME):
                raise RequestError(502, t("serve.notMorphbench", url=self.url))
            return json.loads(r.read().decode("utf-8"))

    def probe(self) -> str:
        """`free` - порт свободен, `ours` - там наш сервер, `busy` - чужая программа,
        `slow` - соединение есть, а ответа за отведённое время нет: кто там, неизвестно."""
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout):
                pass
        except OSError:
            return "free"
        try:
            self._get("/api/environment")
        except urllib.error.URLError as e:
            return "slow" if isinstance(e.reason, (TimeoutError, socket.timeout)) else "busy"
        except (TimeoutError, socket.timeout):
            return "slow"
        except Exception:  # noqa: BLE001 - любой не наш ответ означает чужую программу
            return "busy"
        return "ours"

    def environment(self) -> dict:
        """Окружение работающего сервера: под MO2 ли он и какой у него корень."""
        return self._get("/api/environment")

    def _call(self, path: str) -> dict:
        """Запрос к серверу; его отказ - RequestError с кодом и текстом сервера."""
        try:
            return self._get(path)
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read().decode("utf-8")).get("error") or str(e)
            except Exception:  # noqa: BLE001
                message = str(e)
            raise RequestError(e.code, message) from None

    def set_root(self, root) -> dict:
        """Отдать серверу корень обзора. Отказ сервера - RequestError с его текстом."""
        return self._call("/api/root?" + urllib.parse.urlencode({"root": str(root)}))

    def root(self) -> dict:
        """Корень сервера и число мешей под ним."""
        return self._call("/api/root")

    def shutdown(self) -> dict:
        """Попросить сервер остановиться."""
        return self._call("/api/shutdown")

    def status(self) -> dict:
        """Одним словарём: свободен ли порт, наш ли сервер, что он знает о себе.
        `state` - free, ours или busy; остальное заполнено только для ours."""
        state = self.probe()
        out = {"state": state, "url": self.url, "insideMo2": None, "root": None, "meshes": None}
        if state == "ours":
            env = self.environment()
            out["insideMo2"] = env.get("insideMo2")
            out["dataRoot"] = env.get("dataRoot")
            try:
                out.update(self.root())
            except Exception:  # noqa: BLE001 - корень не обязателен для состояния
                out["root"] = env.get("root")
        return out

    def open_page(self) -> None:
        webbrowser.open(self.url)


class _Handler(BaseHTTPRequestHandler):
    """Разбор пути и отправка ответа; содержание - у WebServer."""

    server_version = SERVER_NAME

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
            elif url.path == "/api/root":
                self._send_json(owner.api_root(query))
            elif url.path == "/api/shutdown":
                self._send_json(owner.api_shutdown())
            elif url.path == "/favicon.ico":
                # Значок у страницы встроенный; браузеры всё равно спрашивают - молча пусто.
                self.send_response(204)
                self.end_headers()
            else:
                raise RequestError(404, t("serve.noSuchPath", path=url.path))
        except Exception as e:  # noqa: BLE001 - любой отказ уходит клиенту кодом и текстом
            self._send_json({"error": _message(e)}, _status_of(e))

    # ---- журнал -----------------------------------------------------------------------
    def _quiet(self) -> bool:
        """Опрос состояния: тот, кто сервер запустил, спрашивает его на каждое обновление,
        и в окне опрос заслонил бы собой всё остальное. Поэтому он пишется уровнем ниже,
        а не выбрасывается: в файле журнала он остаётся, там он и нужен. Передача корня
        (`/api/root?root=...`) - событие, а не опрос, и идёт обычным уровнем."""
        # Разбор мог не дойти до пути (кривая первая строка запроса) - тогда это не опрос.
        url = urlsplit(getattr(self, "path", "") or "")
        if url.path in ("/api/environment", "/favicon.ico"):
            return True
        return url.path == "/api/root" and "root=" not in url.query

    def _write(self, level, text: str) -> None:
        """Запись через журнал владельца. Журнал не бросает, но и путь до него не должен:
        обращение идёт из отправки ответа, до заголовков, и любой отказ здесь оборвал бы
        клиенту связь без единого слова - ровно тот дефект, ради которого журнал и завели."""
        try:
            self.owner.journal.log(level, "%s - %s" % (self.address_string(), text))
        except Exception:                    # noqa: BLE001 - журнал ответу не хозяин
            pass

    def log_request(self, code="-", size="-") -> None:
        self._write("debug" if self._quiet() else "info",
                    '"%s" %s %s' % (getattr(self, "requestline", "-"), code, size))

    def log_error(self, fmt, *args) -> None:
        self._write("error", fmt % args)

    def log_message(self, fmt, *args) -> None:
        self._write("info", fmt % args)
