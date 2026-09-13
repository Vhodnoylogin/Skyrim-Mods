# -*- coding: utf-8 -*-
"""Общее для проверок: где лежит пакет, настройки во временной папке, крошечные фигуры в памяти.

Ни одна проверка не читает файлов сборки. Тело собирается из нескольких десятков вершин
прямо здесь — сетка, оболочка над ней, кости с весами, морф с известным сдвигом — и
подключается к фасаду через `MorphBench.attach`. Ожидаемые числа при этом считаются
в уме, и сбой означает поломку ядра, а не изменившийся меш вервольфа.

Настройки создаются во временной папке: настоящий `morphbench.json` рядом с программой
проверки не трогают. PyNifly нужен только там, где пишется настоящий файл (.tri, .nif);
без него такие наборы пропускаются с внятной причиной, а не падают.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path

# Проверки сверяются с текстами сообщений дословно, поэтому язык у них задан,
# а не взят с машины: иначе набор проходил бы у одного и падал у другого.
os.environ.setdefault("MORPHBENCH_LANG", "en")

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from morphbench import Bone, BodyModel, Config, Morph, MorphBench, MorphSet, Shape  # noqa: E402


# ---- настройки и PyNifly -----------------------------------------------------------------
def config(tmpdir, **overrides) -> Config:
    """Настройки во временной папке: умолчания программы плюс переданные ключи.

    Файл пишется до создания Config, потому что Config читает существующий файл целиком
    и сливает его с умолчаниями — так проверяется именно путь «значение из файла».
    """
    path = Path(tmpdir) / "morphbench.json"
    if overrides:
        path.write_text(json.dumps(overrides), encoding="utf-8")
    return Config(path)


def pynifly_root(cfg: Config):
    """Папка PyNifly либо None, если аддон не найден."""
    try:
        return cfg.pynifly_root()
    except FileNotFoundError:
        return None


def require_pynifly(cfg: Config) -> Path:
    """Папка PyNifly либо пропуск набора: без него настоящий файл не записать."""
    root = pynifly_root(cfg)
    if root is None:
        raise unittest.SkipTest("PyNifly не найден: нет аддона io_scene_nifly в каталоге "
                                "аддонов Blender, а ключ pynifly в morphbench.json пуст")
    return root


def load_module(name: str, path: Path):
    """Модуль PyNifly по файлу — так же, как это делает morphs.py: пакет `tri` целиком
    импортировать нельзя, его __init__ тянет bpy, которого вне Blender нет."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def trip_file_class(cfg: Config):
    """TripFile из PyNifly — штатный писатель и читатель TRIP (морфы тела)."""
    root = require_pynifly(cfg)
    try:
        return load_module("_mbtest_tripfile", root / "tri" / "tripfile.py").TripFile
    except Exception as e:  # noqa: BLE001 - любая причина означает «проверить нечем»
        raise unittest.SkipTest("tri/tripfile.py из PyNifly не загрузился: %s" % e)


def tri_file_class(cfg: Config):
    """TriFile из PyNifly — писатель и читатель лицевого FRTRI."""
    root = require_pynifly(cfg)
    try:
        return load_module("_mbtest_trifile", root / "tri" / "trifile.py").TriFile
    except Exception as e:  # noqa: BLE001
        raise unittest.SkipTest("tri/trifile.py из PyNifly не загрузился: %s" % e)


def load_pynifly(cfg: Config):
    """Обвязка pyn.pynifly вместе с NiflyDLL — тем же путём, каким её берёт model.py."""
    root = require_pynifly(cfg)
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from pyn import pynifly  # noqa: WPS433 - библиотека внешняя, импорт по месту
        return pynifly
    except Exception as e:  # noqa: BLE001
        raise unittest.SkipTest("pyn.pynifly из PyNifly не загрузился: %s" % e)


def write_nif(pynifly, path, shapes: dict, game: str = "SKYRIM") -> Path:
    """Крошечный NIF штатным PyNifly.

    `shapes` — имя части -> словарь с verts, tris, uvs, normals и bones
    ({кость: [(вершина, вес), ...]}). Любой отказ API PyNifly — пропуск набора, а не сбой:
    здесь проверяется чтение верстака, а не сам PyNifly.
    """
    path = Path(path)
    try:
        nif = pynifly.NifFile()
        nif.initialize(game, str(path))          # SKYRIM - NiTriShape, SKYRIMSE - BSTriShape
        for name, spec in shapes.items():
            sh = nif.createShapeFromData(
                name,
                [tuple(float(x) for x in v) for v in spec["verts"]],
                [tuple(int(x) for x in t) for t in spec["tris"]],
                [tuple(float(x) for x in u) for u in spec["uvs"]],
                [tuple(float(x) for x in n) for n in spec["normals"]])
            bones = spec.get("bones") or {}
            # Сначала все кости, потом веса: add_bone сбрасывает привязки части.
            for bone_name in bones:
                sh.add_bone(bone_name)
            for bone_name, weights in bones.items():
                sh.setShapeWeights(bone_name, [(int(v), float(w)) for v, w in weights])
        nif.save()
        del nif
    except Exception as e:  # noqa: BLE001
        raise unittest.SkipTest("PyNifly не смог создать NIF (%s: %s)" % (type(e).__name__, e))
    if not path.is_file():
        raise unittest.SkipTest("PyNifly отработал без ошибки, но файла %s нет" % path)
    return path


def write_skeleton(pynifly, path, bones: dict) -> Path:
    """Крошечный скелет штатным PyNifly: узел на кость, у каждого тело с одной капсулой.

    `bones` - имя кости -> (сдвиг узла по z, (p1, p2, радиус) капсулы в единицах Havok).
    Так проверяется запись связок: PyNifly создаёт скелет, верстак его правит и пишет,
    PyNifly читает обратно. Любой отказ API - пропуск набора, а не сбой.
    """
    path = Path(path)
    try:
        from pyn.nifdefs import TransformBuf, bhkCapsuleShapeProps, bhkRigidBodyProps  # noqa: WPS433
        nif = pynifly.NifFile()
        nif.initialize("SKYRIMSE", str(path))
        for name, (dz, (p1, p2, r)) in bones.items():
            xf = TransformBuf()
            xf.set_identity()
            xf.translation = (0.0, 0.0, float(dz))
            node = nif.add_node(name, xf, parent=nif.rootNode)
            col = node.add_collision(None)
            rb = bhkRigidBodyProps()
            rb.collisionFilter_layer, rb.collisionResponse = 8, 1
            body = pynifly.bhkRigidBody.New(file=nif, properties=rb, parent=col)
            props = bhkCapsuleShapeProps()
            props.bhkMaterial = 591247106                     # SKIN
            props.bhkRadius = props.radius1 = props.radius2 = float(r)
            props.point1, props.point2 = tuple(map(float, p1)), tuple(map(float, p2))
            body.add_shape(props)
        nif.save()
        del nif
    except Exception as e:  # noqa: BLE001
        raise unittest.SkipTest("PyNifly не смог создать скелет (%s: %s)" % (type(e).__name__, e))
    if not path.is_file():
        raise unittest.SkipTest("PyNifly отработал без ошибки, но файла %s нет" % path)
    return path


# ---- фигуры в памяти ---------------------------------------------------------------------
def grid(name: str, nx: int, ny: int, spacing: float = 1.0, z: float = 0.0,
         x0: float = 0.0, y0: float = 0.0, bones: dict | None = None) -> Shape:
    """Плоская сетка nx×ny вершин на высоте z, по два треугольника на клетку.

    Вершина столбца ix и ряда iy получает номер iy*nx + ix — так ожидаемые номера
    считаются в уме, а сосед сверху и сосед справа известны заранее.
    """
    ix, iy = np.meshgrid(np.arange(nx), np.arange(ny))            # оба формы (ny, nx)
    verts = np.stack([x0 + ix.ravel() * spacing, y0 + iy.ravel() * spacing,
                      np.full(nx * ny, z)], axis=1).astype(np.float32)
    tris = []
    for row in range(ny - 1):
        for col in range(nx - 1):
            a = row * nx + col
            tris.append((a, a + 1, a + nx))
            tris.append((a + 1, a + nx + 1, a + nx))
    tris = np.array(tris, dtype=np.int32).reshape(-1, 3)
    return Shape(name, verts, tris, None, None, dict(bones or {}))


def columns(nx: int, ny: int, cols) -> np.ndarray:
    """Номера вершин сетки, чей столбец ix входит в cols; по возрастанию."""
    wanted = set(int(c) for c in cols)
    return np.array([iy * nx + ix for iy in range(ny) for ix in range(nx) if ix in wanted],
                    dtype=np.int32)


def bone(name: str, indices, weight: float = 1.0) -> Bone:
    return Bone(name, {int(i): float(weight) for i in indices})


def model(*shapes: Shape, name: str = "memory.nif") -> BodyModel:
    return BodyModel(Path(name), {s.name: s for s in shapes})


def morph(name: str, shape_name: str, indices, offsets) -> Morph:
    """Морф из номеров вершин и смещений; один вектор смещения растягивается на все."""
    idx = np.asarray(indices, dtype=np.int32).reshape(-1)
    off = np.asarray(offsets, dtype=np.float32).reshape(-1, 3)
    if off.shape[0] == 1 and idx.shape[0] != 1:
        off = np.repeat(off, idx.shape[0], axis=0)
    return Morph(name, shape_name, idx, off)


def empty_morph(name: str, shape_name: str) -> Morph:
    return Morph(name, shape_name, np.zeros(0, dtype=np.int32), np.zeros((0, 3), dtype=np.float32))


def morph_set(*morphs: Morph, name: str = "memory.tri", kind: str = "TRIP") -> MorphSet:
    by_shape: dict[str, dict[str, Morph]] = {}
    for m in morphs:
        by_shape.setdefault(m.shape_name, {})[m.name] = m
    return MorphSet(Path(name), kind, by_shape)


def bench(tmpdir, body: BodyModel, morphs: MorphSet | None = None, **overrides) -> MorphBench:
    """Фасад с настройками во временной папке и подключённым телом."""
    b = MorphBench(config(tmpdir, **overrides))
    b.attach(body, morphs)
    return b


# ---- образцовое тело: кожа с двумя костями, оболочка над ней, четыре ползунка ------------
SAMPLE_NX = SAMPLE_NY = 4


def sample_model() -> BodyModel:
    """Кожа 4×4 на z=0: столбцы 0-1 держит кость Hand, столбцы 2-3 — Finger.
    Оболочка fur 4×4 в одной единице над кожей, целиком на кости Fur."""
    nx, ny = SAMPLE_NX, SAMPLE_NY
    body = grid("body", nx, ny, bones={
        "Hand": bone("Hand", columns(nx, ny, (0, 1))),
        "Finger": bone("Finger", columns(nx, ny, (2, 3)))})
    fur = grid("fur", nx, ny, z=1.0, bones={"Fur": bone("Fur", range(nx * ny))})
    return model(body, fur)


def sample_morphs() -> MorphSet:
    """Up — поднимает пальцы (столбцы 2-3) на 1 у кожи и на 0.5 у оболочки;
    Wide — сдвигает всю кожу целиком; Tip — только крайний столбец; Empty — ничего."""
    nx, ny = SAMPLE_NX, SAMPLE_NY
    fingers = columns(nx, ny, (2, 3))
    return morph_set(
        morph("Up", "body", fingers, [(0.0, 0.0, 1.0)]),
        morph("Up", "fur", fingers, [(0.0, 0.0, 0.5)]),
        morph("Wide", "body", range(nx * ny), [(1.0, 0.0, 0.0)]),
        morph("Tip", "body", columns(nx, ny, (3,)), [(0.0, 0.0, 2.0)]),
        empty_morph("Empty", "body"))


# ---- разное ------------------------------------------------------------------------------
def is_plain(value) -> bool:
    """Только то, что JSON понимает без подсказок: числа, строки, булевы, None, списки
    и словари со строковыми ключами. Типы numpy сюда не входят намеренно."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return True
    if isinstance(value, list):
        return all(is_plain(v) for v in value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and is_plain(v) for k, v in value.items())
    return False


def by_key(rows: list[dict], key: str) -> dict:
    """Список словарей -> словарь по значению ключа; удобно спрашивать строку по имени."""
    return {r[key]: r for r in rows}


def main() -> None:
    """Запуск одного файла напрямую: python tests/test_x.py."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    unittest.main(verbosity=2)
