# -*- coding: utf-8 -*-
"""Разбор файлов морфов: настоящий файл, записанный штатным модулем PyNifly, читается
`MorphSet.from_file`.

Ловит расхождение между тем, что записал сборщик, и тем, что увидел верстак: потерянный
морф, потерянную часть, перепутанные номера вершин и ошибку в множителе, из-за которой все
сдвиги стали бы в тысячи раз больше или меньше. TRIP хранит смещения как int16 × множитель,
где множитель = max|offset| / 32767, поэтому сверка идёт с точностью одного кванта, а не
побитно. Набор пишет файл сам, а не читает готовый: так он не зависит от меша вервольфа.
"""
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench import MorphSet  # noqa: E402
from morphbench.analysis import Analyzer  # noqa: E402

# Кожа: шесть вершин, оболочка: четыре. Смещения заданы по номерам вершин, чтобы ожидаемые
# числа были видны глазом. Величины разного порядка нарочно: у каждого морфа свой множитель.
BODY_VERTS = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (2.0, 0.0, 0.0),
              (0.0, 1.0, 0.0), (1.0, 1.0, 0.0), (2.0, 1.0, 0.0)]
FUR_VERTS = [(0.0, 0.0, 1.0), (1.0, 0.0, 1.0), (0.0, 1.0, 1.0), (1.0, 1.0, 1.0)]
BODY_MORPHS = {
    "CLAWBelly": {1: (1.0, -2.0, 0.5), 3: (0.25, 0.0, 0.0), 4: (0.0, 0.0, 3.0)},
    "CLAWEars": {0: (0.0, 0.75, 0.0), 5: (-0.5, 0.0, 0.0)},
    "CLAWHuge": {2: (250.0, 0.0, -125.0)},
    "CLAWSmall": {5: (0.01, 0.0, 0.005)},
}
FUR_MORPHS = {"CLAWBelly": {2: (0.0, 0.0, 1.5)}}


def targets(verts, offsets):
    """TripFile.set_morphs принимает не смещения, а конечные координаты вершин: он сам
    вычитает базу и выбрасывает то, что не сдвинулось."""
    return [tuple(v[k] + offsets.get(i, (0.0, 0.0, 0.0))[k] for k in range(3))
            for i, v in enumerate(verts)]


def quantum(offsets: dict) -> float:
    """Один шаг int16 в этом морфе: наибольшая компонента смещения / 32767."""
    top = max(abs(c) for o in offsets.values() for c in o)
    return top / 32767.0


class TestTripRoundTrip(unittest.TestCase):
    """TRIP, записанный TripFile из PyNifly, читается MorphSet без потерь сверх кванта."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = common.config(self.tmp.name)
        self.TripFile = common.trip_file_class(self.cfg)

        trip = self.TripFile()
        body = {name: targets(BODY_VERTS, offs) for name, offs in BODY_MORPHS.items()}
        # Морф без единого сдвига: set_morphs его выбросит, и в файл он не попадёт.
        body["Nothing"] = list(BODY_VERTS)
        trip.set_morphs("body", body, BODY_VERTS)
        trip.set_morphs("fur", {name: targets(FUR_VERTS, offs)
                                for name, offs in FUR_MORPHS.items()}, FUR_VERTS)
        # Морф, чьё единственное смещение ниже порога 0.0001: в файл он записывается,
        # но читатель формата отбрасывает такие сдвиги — получается пустой морф в файле.
        trip.shapes["body"]["Tiny"] = [[0, (0.00005, 0.0, 0.0)]]
        self.path = Path(self.tmp.name) / "claws.tri"
        trip.write(str(self.path))
        self.ms = MorphSet.from_file(self.path, self.cfg)

    def test_kind_shapes_and_names(self):
        """Вид файла, имена частей и ползунков. Nothing отсутствует по вине писателя
        (set_morphs выбрасывает морфы без смещений), и верстак не должен его выдумывать."""
        self.assertEqual(self.ms.kind, "TRIP")
        self.assertEqual(self.ms.shape_names(), ["body", "fur"])
        self.assertEqual(self.ms.names(), sorted(list(BODY_MORPHS) + ["Tiny"]))
        self.assertNotIn("Nothing", self.ms.names())
        self.assertEqual(sorted(self.ms.for_morph("CLAWBelly")), ["body", "fur"])

    def test_indices_and_counts(self):
        """Номера сдвинутых вершин и их число — ровно те, что записаны."""
        for name, offs in BODY_MORPHS.items():
            m = self.ms.get("body", name)
            self.assertIsNotNone(m, name)
            self.assertEqual(m.vertex_count, len(offs), name)
            self.assertEqual(sorted(m.indices.tolist()), sorted(offs), name)
        fur = self.ms.get("fur", "CLAWBelly")
        self.assertEqual(fur.indices.tolist(), [2])

    def test_offsets_within_one_quantum(self):
        """Каждая компонента смещения отличается от записанной не больше чем на квант
        своего морфа. Ошибка в множителе дала бы расхождение в тысячи раз."""
        for shape, table, morphs in (("body", BODY_VERTS, BODY_MORPHS),
                                     ("fur", FUR_VERTS, FUR_MORPHS)):
            for name, offs in morphs.items():
                m = self.ms.get(shape, name)
                tol = quantum(offs) * 1.001 + 1e-7
                for idx, vec in zip(m.indices.tolist(), m.offsets):
                    got = np.asarray(vec, dtype=np.float64)
                    want = np.asarray(offs[idx], dtype=np.float64)
                    self.assertTrue(np.all(np.abs(got - want) <= tol),
                                    "%s/%s вершина %d: прочитано %s, записано %s, квант %g"
                                    % (shape, name, idx, got, want, tol))

    def test_max_and_mean_shift(self):
        """Наибольший и средний сдвиг совпадают с посчитанными вручную с точностью
        кванта по трём осям (√3 × квант)."""
        for name, offs in BODY_MORPHS.items():
            m = self.ms.get("body", name)
            lengths = [math.sqrt(sum(c * c for c in o)) for o in offs.values()]
            tol = math.sqrt(3.0) * quantum(offs) + 1e-6
            self.assertAlmostEqual(m.max_shift, max(lengths), delta=tol, msg=name)
            self.assertAlmostEqual(m.mean_shift, sum(lengths) / len(lengths), delta=tol, msg=name)

    def test_matches_raw_tripfile(self):
        """То же, что видит сам TripFile.from_filepath: верстак не добавляет своего
        прочтения формата, он только раскладывает пары в массивы."""
        raw = self.TripFile.from_filepath(str(self.path)).shapes
        self.assertEqual(sorted(raw), self.ms.shape_names())
        for shape, morphs in raw.items():
            self.assertEqual(sorted(morphs), sorted(self.ms.by_shape[shape]))
            for name, pairs in morphs.items():
                m = self.ms.get(shape, name)
                self.assertEqual(m.indices.tolist(), [p[0] for p in pairs], "%s/%s" % (shape, name))
                want = np.array([p[1] for p in pairs], dtype=np.float64).reshape(-1, 3)
                self.assertTrue(np.allclose(m.offsets, want, atol=1e-5), "%s/%s" % (shape, name))

    def test_empty_morph_from_file(self):
        """Морф, который в файле есть, а вершин не двигает, читается как пустой и попадает
        в перечень пустых — это та самая тихая поломка, ради которой разбор и нужен."""
        tiny = self.ms.get("body", "Tiny")
        self.assertIsNotNone(tiny)
        self.assertTrue(tiny.is_empty)
        self.assertEqual([m.name for m in self.ms.empty()], ["Tiny"])
        listed = [(s.shape, s.morph) for s in Analyzer(common.model(), self.ms).empty_morphs()]
        self.assertEqual(listed, [("body", "Tiny")])

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            MorphSet.from_file(Path(self.tmp.name) / "no-such.tri", self.cfg)


class TestFrtriRoundTrip(unittest.TestCase):
    """Лицевой FRTRI, записанный TriFile из PyNifly, читается как смещения относительно базы.

    TriFile отдаёт морфы как АБСОЛЮТНЫЕ координаты вершин и кладёт саму базу под именем
    Basis. Верстак обязан вычесть базу и не считать Basis ползунком — иначе каждый морф
    лица «двигает» все вершины на величину их координат.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cfg = common.config(self.tmp.name)
        TriFile = common.tri_file_class(self.cfg)
        self.verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (1.0, 1.0, 0.0)]
        self.shift = (0.0, 0.0, 0.5)
        moved = [tuple(v[k] + (self.shift[k] if i in (1, 3) else 0.0) for k in range(3))
                 for i, v in enumerate(self.verts)]
        t = TriFile()
        t.vertices = list(self.verts)
        t.faces = [(0, 1, 2), (1, 3, 2)]
        t.uv_pos = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]
        t.morphs = {"Smile": moved}
        self.path = Path(self.tmp.name) / "face.tri"
        try:
            t.write(str(self.path))
        except Exception as e:  # noqa: BLE001
            raise unittest.SkipTest("TriFile.write из PyNifly не записал файл: %s" % e)
        # Убедиться, что сам PyNifly свой файл читает; иначе проверять нечем.
        back = TriFile.from_filepath(str(self.path))
        if back is None or "Smile" not in back.morphs:
            raise unittest.SkipTest("TriFile.from_filepath не прочитал свой же файл")
        self.ms = MorphSet.from_file(self.path, self.cfg)

    def test_kind_and_shape_name(self):
        """Вид FRTRI, часть названа по имени файла."""
        self.assertEqual(self.ms.kind, "FRTRI")
        self.assertEqual(self.ms.shape_names(), ["face"])

    def test_basis_is_not_a_morph(self):
        """База лица — не ползунок. Если она попала в перечень, разбор принял абсолютные
        координаты TriFile за смещения."""
        self.assertEqual(self.ms.names(), ["Smile"])

    def test_offsets_relative_to_base(self):
        """Smile двигает вершины 1 и 3 на (0, 0, 0.5) с точностью кванта; остальные не
        трогает. Абсолютные координаты вместо смещений сдвинули бы и вершину 3 на (1, 1, 0.5)."""
        m = self.ms.get("face", "Smile")
        self.assertIsNotNone(m)
        self.assertEqual(sorted(m.indices.tolist()), [1, 3])
        tol = 0.5 / 32767.0 * 1.001 + 1e-6
        for vec in m.offsets:
            self.assertTrue(np.all(np.abs(np.asarray(vec, np.float64) - self.shift) <= tol),
                            "прочитано %s, ожидалось %s" % (vec, self.shift))


if __name__ == "__main__":
    common.main()
