# -*- coding: utf-8 -*-
"""Замкнутые тела в памяти: куб из двенадцати треугольников с обходом наружу.

Плоская сетка из common годится для морфов и слоёв, но у неё нет «той стороны»: свет,
нормали и кадр проверяются на теле, у которого есть перед, зад и объём. Куба для этого
достаточно, и он считается в уме: нормаль каждой грани известна, каждая вершина держит
три грани, а поворот на 180° переводит переднюю грань в заднюю — отсюда ожидание
одинаковой яркости с обоих ракурсов при свете за камерой.
"""
from __future__ import annotations

import numpy as np

from common import Shape

# Углы куба с полуребром 1; треугольники обходят каждую грань против часовой стрелки,
# если смотреть снаружи, так что (b - a) × (c - a) смотрит от центра.
CUBE_CORNERS = np.array([
    (-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
    (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)], dtype=np.float32)
CUBE_TRIS = np.array([
    (0, 2, 1), (0, 3, 2),      # низ,    z = -1
    (4, 5, 6), (4, 6, 7),      # верх,   z = +1
    (0, 1, 5), (0, 5, 4),      # перед,  y = -1
    (2, 3, 7), (2, 7, 6),      # зад,    y = +1
    (0, 4, 7), (0, 7, 3),      # левая,  x = -1
    (1, 2, 6), (1, 6, 5)],     # правая, x = +1
    dtype=np.int32)


def cube(name: str = "cube", half: float = 1.0, centre=(0.0, 0.0, 0.0),
         bones: dict | None = None) -> Shape:
    """Куб с полуребром `half` вокруг `centre`: 8 вершин, 12 треугольников наружу."""
    verts = (CUBE_CORNERS * float(half)
             + np.asarray(centre, dtype=np.float32)).astype(np.float32)
    return Shape(name, verts, CUBE_TRIS.copy(), None, None, dict(bones or {}))


def face_normal(verts, tri) -> np.ndarray:
    """Единичная нормаль треугольника по его обходу: (b - a) × (c - a)."""
    a, b, c = (np.asarray(verts[int(i)], dtype=np.float64) for i in tri)
    n = np.cross(b - a, c - a)
    return n / np.linalg.norm(n)
