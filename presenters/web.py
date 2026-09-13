"""Слой показа: самодостаточная страница со смотрелкой в браузере.

Один HTML-файл и ничего снаружи: ни библиотек, ни шрифтов, ни картинок, ни запросов. Всё, что
нужно, чтобы покрутить тело и потянуть ползунки, вложено внутрь - геометрия, морфы, признаки
раскраски, цели наведения, ракурсы и настройки. Открывается с диска, по file://, и живёт
столько, сколько живёт файл: страницу можно положить рядом с отчётом о прогоне.

Ничего не вычисляет сам - в том же смысле, что и растеризатор. Вершины, треугольники, номера
костей, смещения морфов и растяжение берутся у фасада и упаковываются в один блок JSON;
двоичные массивы - типизированные массивы в base64. Смещения морфов сжаты в двухбайтные числа
с одним множителем на пару «часть - морф», как в формате TRIP, растяжение - разреженно, только
ненулевые вершины. Скрипт страницы повторяет объекты ядра зеркально: у каждой кнопки есть
метод `MorphBench` с тем же именем, а внизу панели видно текущее состояние в том виде, в каком
его отдаёт `view_state()`, и командную строку `mb.py render`, которая даст тот же кадр без окна.

Палитры перенесены из растеризатора один в один, камера повторяет `ViewState.basis()`
и `framing()`, свет - `light_vector()` и силы из того же состояния, нормали вершин считаются
по `vertex_normals` из model.py - поэтому кадр страницы совпадает с PNG.

Капсулы столкновений - если к мешу открыт скелет - вкладываются готовыми треугольниками,
как их отдаёт `collider_mesh()` и `bumper_mesh()`; страница кладёт их поверх тела так же,
как растеризатор: полупрозрачно, цветом и прозрачностью из настроек, со своей глубиной
и не заслоняя тело. Включение слоя - `show_colliders`, тот же метод, что у фасада.

Та же страница умеет приходить и с локального сервера (`mb.py serve`): тогда в блок JSON
вкладываются ещё список мешей под корнем обзора и окружение, и на панели появляется выбор
модели. Геометрия в обоих случаях упаковывается одинаково, а страница с сервера обращается
только к своему серверу - переходом на другой запрос, без единого запроса наружу.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np

from morphbench.i18n import language, section, t

from .assets import PageAssets


class WebPage:
    """Страница поверх фасада: числа ядра, упакованные в один файл.

    Без сервера страница самодостаточна и открывается с диска. С сервера (`server=True`)
    она получает ещё список мешей `catalog` (как его отдаёт `bench.catalog`), окружение
    `environment`, корень обзора `root`, признак «и без морфов» и текст ошибки последнего
    запроса: этого хватает панели, чтобы предложить выбор модели ссылкой на тот же сервер.
    Меш при этом может быть и не открыт - тогда страница показывает пустой холст и список.
    """

    def __init__(self, bench, server: bool = False, catalog=None, environment=None,
                 root=None, with_morphs: bool = True, error: str | None = None):
        self.bench = bench
        self.cfg = bench.cfg
        self.server = bool(server)
        self.catalog = list(catalog or [])
        self.environment = dict(environment or {})
        self.root = None if root is None else str(root)
        self.with_morphs = bool(with_morphs)
        self.error = None if error is None else str(error)
        self.assets = PageAssets()

    # ---- упаковка массивов ------------------------------------------------------------
    @staticmethod
    def _b64(arr, dtype) -> str:
        """Байты массива в base64; порядок байтов - little-endian, как читает JS."""
        return base64.b64encode(np.ascontiguousarray(arr, dtype=dtype).tobytes()).decode("ascii")

    @staticmethod
    def _index_type(vertex_count: int) -> str:
        """Номера вершин: два байта, пока вершин меньше 65536, иначе четыре."""
        return "u16" if vertex_count < 65536 else "u32"

    @classmethod
    def _indices(cls, idx, vertex_count: int) -> str:
        return cls._b64(idx, "<u2" if cls._index_type(vertex_count) == "u16" else "<u4")

    # ---- части меша -------------------------------------------------------------------
    def _shape(self, name: str) -> dict:
        """Одна часть: вершины, треугольники, признак главной кости и имена костей."""
        shape = self.bench.model.shape(name)
        count = shape.vertex_count
        return {
            "name": name,
            "vertexCount": count,
            "vertices": self._b64(shape.verts, "<f4"),
            "indexType": self._index_type(count),
            "triangles": self._indices(shape.tris, count),
            "boneKey": self._b64(self.bench.bone_key(name), "<i2"),
            "boneNames": self.bench.shape_bone_names(name),
            # Кости с непустыми весами - по ним ядро решает, чья капсула видна вместе
            # с частью (visible_collider_bones); boneNames может нести и пустые.
            "heldBones": self.bench.held_bones(name),
        }

    # ---- капсулы столкновений ---------------------------------------------------------
    @classmethod
    def _chunk(cls, verts, tris) -> dict | None:
        """Кусок геометрии без костей и морфов - в том же виде, что часть меша: вершины
        `<f4`, тип номера и треугольники. Пустой кусок - None: рисовать нечего."""
        tris = np.asarray(tris)
        if tris.shape[0] == 0:
            return None
        verts = np.asarray(verts, dtype=np.float32).reshape(-1, 3)
        count = int(verts.shape[0])
        return {"vertexCount": count,
                "vertices": cls._b64(verts, "<f4"),
                "indexType": cls._index_type(count),
                "triangles": cls._indices(tris, count)}

    def _colliders(self) -> dict | None:
        """Капсулы тел кусками по костям (`collider_meshes` фасада) и бампер отдельно,
        в мировых координатах. По костям - чтобы страница прятала капсулу вместе с частью
        меша, не спрашивая ядро. Без скелета - None: раздел на панели не строится."""
        bench = self.bench
        if not bench.has_skeleton():
            return None
        bodies = []
        for piece in bench.collider_meshes():
            chunk = self._chunk(piece["verts"], piece["tris"])
            if chunk is not None:
                bodies.append({"bone": piece["bone"], **chunk})
        return {"bodies": bodies, "bumper": self._chunk(*bench.bumper_mesh())}

    # ---- морфы ------------------------------------------------------------------------
    def _deltas(self, shape_name: str, morph: str, vertex_count: int) -> dict | None:
        """Смещения морфа на части, сжатые в int16 с одним множителем: max|сдвиг|/32767."""
        raw = self.bench.morph_deltas(shape_name, morph)
        if raw is None:
            return None
        keep = raw["indices"] < vertex_count
        idx = raw["indices"][keep]
        off = np.asarray(raw["offsets"][keep], dtype=np.float32).reshape(-1, 3)
        if idx.size == 0:
            return None
        top = float(np.abs(off).max())
        if top <= 0.0:
            return None
        scale = top / 32767.0
        q = np.clip(np.rint(off / scale), -32767, 32767).astype(np.int16)
        return {"count": int(idx.size), "scale": scale,
                "indexType": self._index_type(vertex_count),
                "indices": self._indices(idx, vertex_count),
                "offsets": self._b64(q, "<i2")}

    def _strain(self, shape_name: str, morph: str, vertex_count: int) -> dict | None:
        """Растяжение у вершин - разреженно: ненулевые вершины, uint8 от максимума и сам максимум."""
        key = np.asarray(self.bench.strain_key(shape_name, morph), dtype=np.float32)
        top = float(key.max()) if key.size else 0.0
        if top <= 1e-6:
            return None
        idx = np.nonzero(key > 0.0)[0]
        values = np.clip(np.rint(255.0 * key[idx] / top), 0, 255).astype(np.uint8)
        return {"count": int(idx.size), "max": top,
                "indexType": self._index_type(vertex_count),
                "indices": self._indices(idx, vertex_count),
                "values": self._b64(values, "u1")}

    # ---- настройки, которые нужны показу ----------------------------------------------
    def _settings(self) -> dict:
        """Единственный источник чисел для страницы: ни одно из них в скрипте не зашито."""
        cfg = self.cfg
        return {
            "background": [float(x) for x in cfg["background"]],
            "lightFollowCamera": bool(cfg["lightFollowCamera"]),
            "lightCameraDirection": [float(x) for x in cfg["lightCameraDirection"]],
            "lightDirection": [float(x) for x in cfg["lightDirection"]],
            "ambient": float(cfg["ambient"]),
            "diffuse": float(cfg["diffuse"]),
            "fill": float(cfg["fill"]),
            "shading": str(cfg["shading"]),
            "imageWidth": int(cfg["imageWidth"]),
            "imageHeight": int(cfg["imageHeight"]),
            "frameFill": float(cfg["frameFill"]),
            "focusPadding": float(cfg["focusPadding"]),
            "baseShape": str(cfg["baseShape"]),
            "sliderRange": [float(x) for x in cfg["sliderRange"]],
            "sliderStep": float(cfg["sliderStep"]),
            "orbitSensitivity": float(cfg["orbitSensitivity"]),
            "wheelZoomRate": float(cfg["wheelZoomRate"]),
            # Слой капсул: цвет 0..255 и прозрачность 0..1 - те же ключи, что у растеризатора.
            "colliderColour": [float(x) for x in cfg["colliderColour"]],
            "colliderOpacity": float(cfg["colliderOpacity"]),
            "collidersFollowParts": bool(cfg["collidersFollowParts"]),
        }

    # ---- сервер: то, что страница знает о нём -----------------------------------------
    def _server(self) -> dict | None:
        """Список мешей, окружение и корень - только когда страницу отдаёт сервер.
        В файле с диска здесь None, и панель не предлагает того, чего сделать не может."""
        if not self.server:
            return None
        return {"root": self.root, "withMorphs": self.with_morphs,
                "catalog": self.catalog, "environment": self.environment,
                "error": self.error}

    # ---- тело: геометрия, морфы, цели -------------------------------------------------
    def _body(self) -> dict:
        """Всё про открытый меш. Здесь нет ни одного вычисления - только вопросы
        к фасаду и упаковка ответов."""
        bench = self.bench
        summary = bench.summary()
        names = bench.model.shape_names()
        shapes = [self._shape(n) for n in names]
        counts = {s["name"]: s["vertexCount"] for s in shapes}
        morphs = bench.morphs() if summary["tri"] else []

        deltas: dict[str, dict] = {}
        strain: dict[str, dict] = {}
        for morph in morphs:
            for n in names:
                d = self._deltas(n, morph, counts[n])
                if d is not None:
                    deltas.setdefault(morph, {})[n] = d
                s = self._strain(n, morph, counts[n])
                if s is not None:
                    strain.setdefault(morph, {})[n] = s

        # Цели наведения - без округления, чтобы кадр страницы сошёлся с PNG. Наведение,
        # заданное из командной строки подстрокой («Finger»), среди целей отсутствует -
        # ядро уже сосчитало его сферу, и она добавляется к целям под своим именем.
        targets = bench.focus_targets(precise=True)
        view = bench.view
        if view.has_focus and view.focus_name and ":" in view.focus_name:
            kind, _, name = view.focus_name.partition(":")
            group = targets.get(kind + "s")
            if group is not None and not any(t["name"] == name for t in group):
                group.append({"name": name, "centre": [float(x) for x in view.focus_centre],
                              "radius": float(view.focus_radius)})

        return {
            "summary": summary,
            "names": {"nif": Path(summary["nif"]).name,
                      "tri": Path(summary["tri"]).name if summary["tri"] else None,
                      "skeleton": Path(summary["skeleton"]).name if summary["skeleton"] else None},
            "shapes": shapes,
            "morphs": morphs,
            "deltas": deltas,
            "strain": strain,
            "targets": targets,
            "colliders": self._colliders(),
        }

    @staticmethod
    def _no_body() -> dict:
        """Меш не открыт: пустой холст, но та же форма данных, чтобы скрипт не ветвился."""
        return {"summary": None, "names": {"nif": None, "tri": None, "skeleton": None},
                "shapes": [], "morphs": [], "deltas": {}, "strain": {},
                "targets": {"bones": [], "morphs": [], "shapes": []},
                "colliders": None}

    # ---- всё вместе -------------------------------------------------------------------
    def payload(self) -> dict:
        """Всё, что страница знает о меше, настройках и - если есть - сервере, одним словарём."""
        bench = self.bench
        data = self._body() if bench.is_open() else self._no_body()
        data.update({
            "settings": self._settings(),
            "presets": bench.presets(),
            "view": bench.view_state(precise=True),
            "sliders": bench.sliders(),
            "server": self._server(),
            # Надписи страницы едут готовыми: скрипт в браузере словаря языка не видит.
            "texts": section("page."),
        })
        return data

    def html(self, linked: bool = False) -> str:
        """Готовая страница строкой.

        `linked` решает, откуда страница берёт свои файлы: сервер раздаёт их по одному,
        а файлу на диске их надо нести внутри. Всё остальное в обоих случаях одинаково.

        Данные лежат в блоке <script type="application/json">; последовательность `</`
        внутри строк экранируется, чтобы имя части не закрыло блок.
        """
        data = json.dumps(self.payload(), ensure_ascii=False, separators=(",", ":"))
        data = data.replace("</", "<\\/")
        name = (Path(self.bench.summary()["nif"]).name if self.bench.is_open()
                else t("page.noMesh"))
        return self.assets.page({
            "__MB_LANG__": _escape(language()),
            "__MB_TITLE__": _escape("morphbench — %s" % name),
            # Две надписи стоят прямо в разметке, до запуска скрипта: подсказка о мыши
            # и слово для браузера без WebGL2 - его читают именно тогда, когда скрипт
            # не пошёл.
            "__MB_HINT__": _escape(t("page.hint")),
            "__MB_NOGL__": _escape(t("page.noWebGL")),
            "__MB_DATA__": data,
        }, linked=linked)

    def save(self, path) -> Path:
        """Страница одним файлом: всё внутри, открывается с диска и живёт без сервера."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.html(), encoding="utf-8")
        return path


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))



