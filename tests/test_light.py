# -*- coding: utf-8 -*-
"""Свет: за камерой или отдельно от неё, направление и силы — числами и поведением кадра.

ViewState держит два направления на источник: в осях камеры (свет едет с ракурсом) и
мировое (стоит на месте); действует то, что выбрано режимом. Ловит: режим, не взятый из
настроек; свет, застрявший в мировых осях при lightFollowCamera; направление, записанное
не в тот режим; нулевой вектор, принятый молча; отрицательную силу; типы numpy в
as_dict()['light']. Растеризатор проверяется на кубе: при свете за камерой перед и зад
одинаково ярки, при мировом свете — нет; встречная подсветка делает тень светлее;
оба способа затенения из настроек рисуют, и плоское действительно плоское.
"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402
import solids  # noqa: E402

from morphbench.view import ViewState  # noqa: E402

try:
    from presenters.raster import Raster
except ImportError as e:  # noqa: N816 - нет PIL либо самого слоя
    Raster = None
    RASTER_ERROR = e

WORLD = (-0.4, -0.7, 0.6)


def unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


class TestViewStateLight(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.view = ViewState(common.config(self.tmp.name))

    def test_mode_from_config(self):
        """Режим по умолчанию — lightFollowCamera из настроек: True в умолчаниях,
        False — если так записано в файле."""
        self.assertTrue(self.view.light_follow)
        self.assertTrue(self.view.light_state()["follow"])
        view = ViewState(common.config(self.tmp.name, lightFollowCamera=False))
        self.assertFalse(view.light_follow)
        self.assertFalse(view.light_state()["follow"])
        self.assertEqual(view.light_state()["direction"], list(WORLD))

    def test_directions_and_powers_from_config(self):
        """Оба направления и три силы приезжают из настроек, а не из чисел в коде."""
        view = ViewState(common.config(self.tmp.name, lightCameraDirection=[0, 0, 1],
                                       lightDirection=[1, 0, 0], ambient=0.1,
                                       diffuse=0.8, fill=0.05))
        self.assertEqual(view.light_camera_dir.tolist(), [0.0, 0.0, 1.0])
        self.assertEqual(view.light_world_dir.tolist(), [1.0, 0.0, 0.0])
        self.assertEqual((view.ambient, view.diffuse, view.fill), (0.1, 0.8, 0.05))

    def test_vector_rides_with_camera(self):
        """Свет за камерой, направление (0,0,1) — «к зрителю». При нулевом ракурсе взгляд
        идёт в -Y, значит источник стоит на +Y и вектор равен (0,1,0); после поворота
        на 180 — (0,-1,0), на 90 — (1,0,0). Вектор, не меняющийся с ракурсом, — свет,
        который не поехал."""
        self.view.light_direction(0.0, 0.0, 1.0)
        self.view.look(0.0, 0.0)
        self.assertTrue(np.allclose(self.view.light_vector(), [0.0, 1.0, 0.0], atol=1e-6))
        self.view.look(180.0, 0.0)
        self.assertTrue(np.allclose(self.view.light_vector(), [0.0, -1.0, 0.0], atol=1e-6))
        self.view.look(90.0, 0.0)
        self.assertTrue(np.allclose(self.view.light_vector(), [1.0, 0.0, 0.0], atol=1e-6))

    def test_camera_axes_right_and_up(self):
        """Направление (1,0,0) в осях камеры — справа от зрителя, (0,1,0) — сверху: ровно
        те оси, что отдаёт basis(). При нулевом ракурсе верх — это +Z."""
        self.view.look(0.0, 0.0)
        right, up, _ = self.view.basis()
        self.view.light_direction(1.0, 0.0, 0.0)
        self.assertTrue(np.allclose(self.view.light_vector(), right, atol=1e-6))
        self.view.light_direction(0.0, 1.0, 0.0)
        self.assertTrue(np.allclose(self.view.light_vector(), up, atol=1e-6))
        self.assertTrue(np.allclose(up, [0.0, 0.0, 1.0], atol=1e-6))

    def test_world_vector_ignores_camera(self):
        """Отдельный свет: вектор один и тот же с любого ракурса и равен нормированному
        мировому направлению."""
        self.view.light_follow_camera(False)
        self.view.light_direction(*WORLD)
        for yaw, pitch in ((0, 0), (180, 0), (90, 0), (40, 15), (0, -60)):
            self.view.look(yaw, pitch)
            v = self.view.light_vector().astype(np.float64)
            self.assertTrue(np.allclose(v, unit(WORLD), atol=1e-6), (yaw, pitch, v))
            self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=6)

    def test_direction_goes_to_current_mode_only(self):
        """light_direction меняет направление текущего режима и не трогает другое;
        переключение режима возвращает прежнее направление, а не подменяет его."""
        world_before = self.view.light_world_dir.tolist()
        self.view.light_direction(1.0, 2.0, 3.0)                 # режим: за камерой
        self.assertEqual(self.view.light_camera_dir.tolist(), [1.0, 2.0, 3.0])
        self.assertEqual(self.view.light_world_dir.tolist(), world_before)
        self.assertEqual(self.view.light_state()["direction"], [1.0, 2.0, 3.0])
        self.view.light_follow_camera(False)
        self.view.light_direction(4.0, 5.0, 6.0)                 # режим: отдельно
        self.assertEqual(self.view.light_world_dir.tolist(), [4.0, 5.0, 6.0])
        self.assertEqual(self.view.light_camera_dir.tolist(), [1.0, 2.0, 3.0])
        self.assertEqual(self.view.light_state()["direction"], [4.0, 5.0, 6.0])
        self.view.light_follow_camera(True)
        self.assertEqual(self.view.light_state()["direction"], [1.0, 2.0, 3.0])

    def test_zero_direction_rejected(self):
        """Нулевой (и почти нулевой) вектор — ValueError, состояние не тронуто."""
        before = self.view.light_camera_dir.tolist()
        with self.assertRaises(ValueError):
            self.view.light_direction(0.0, 0.0, 0.0)
        with self.assertRaises(ValueError):
            self.view.light_direction(1e-9, 0.0, 0.0)
        self.assertEqual(self.view.light_camera_dir.tolist(), before)

    def test_vector_is_unit_for_any_length(self):
        """Направление можно задать любой длины — рисующему отдаётся единичный вектор."""
        self.view.light_direction(0.0, 0.0, 5.0)
        self.assertAlmostEqual(float(np.linalg.norm(self.view.light_vector())), 1.0, places=6)
        self.view.light_follow_camera(False).light_direction(0.0, 300.0, 0.0)
        self.assertTrue(np.allclose(self.view.light_vector(), [0.0, 1.0, 0.0], atol=1e-6))

    def test_power_clamped_below_and_none_keeps(self):
        """Отрицательная сила становится нулём; None оставляет прежнее значение."""
        d, f = self.view.diffuse, self.view.fill
        self.view.light_power(ambient=-1.0)
        self.assertEqual(self.view.ambient, 0.0)
        self.assertEqual((self.view.diffuse, self.view.fill), (d, f))
        self.view.light_power(None, 2.0, None)
        self.assertEqual((self.view.ambient, self.view.diffuse, self.view.fill), (0.0, 2.0, f))
        self.view.light_power(fill=-0.5)
        self.assertEqual(self.view.fill, 0.0)
        self.view.light_power(0.5, 0.5, 0.5)
        self.assertEqual((self.view.ambient, self.view.diffuse, self.view.fill), (0.5, 0.5, 0.5))
        self.view.light_power()
        self.assertEqual((self.view.ambient, self.view.diffuse, self.view.fill), (0.5, 0.5, 0.5))

    def test_state_is_plain(self):
        """light_state() и as_dict()['light'] — только числа и bool; JSON их принимает."""
        self.view.light_direction(0.123456, 0.5, 0.25)
        for state in (self.view.light_state(), self.view.as_dict()["light"]):
            self.assertEqual(set(state), {"follow", "direction", "cameraDirection",
                                          "worldDirection", "ambient", "diffuse", "fill"})
            self.assertIs(type(state["follow"]), bool)
            self.assertEqual(state["direction"], [0.123, 0.5, 0.25])
            # Оба направления отдаются отдельно, чтобы слой показа не достраивал второе
            # из настроек; направление текущего режима повторяет одно из них.
            current = state["cameraDirection"] if state["follow"] else state["worldDirection"]
            self.assertEqual(state["direction"], current)
            for key in ("ambient", "diffuse", "fill"):
                self.assertIs(type(state[key]), float, key)
            self.assertTrue(common.is_plain(state), state)
        json.dumps(self.view.as_dict())


class TestFacadeLight(unittest.TestCase):
    """Методы фасада — те же, что у ViewState, и возвращают as_dict() состояния."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bench = common.bench(self.tmp.name, common.sample_model(), common.sample_morphs())

    def test_methods_return_view_state(self):
        state = self.bench.light_follow_camera(False)
        self.assertEqual(state, self.bench.view_state())
        self.assertFalse(state["light"]["follow"])
        state = self.bench.light_direction(*WORLD)
        self.assertEqual(state, self.bench.view_state())
        self.assertEqual(state["light"]["direction"], list(WORLD))
        state = self.bench.light_power(0.2, 0.7, 0.1)
        self.assertEqual(state, self.bench.view_state())
        self.assertEqual((state["light"]["ambient"], state["light"]["diffuse"],
                          state["light"]["fill"]), (0.2, 0.7, 0.1))
        self.assertTrue(common.is_plain(state), state)
        with self.assertRaises(ValueError):
            self.bench.light_direction(0.0, 0.0, 0.0)

    def test_light_vector_is_list_of_floats(self):
        """Фасад отдаёт обычный список из трёх float, совпадающий с вектором ViewState
        при том же ракурсе."""
        v = self.bench.light_vector()
        self.assertEqual(len(v), 3)
        self.assertTrue(all(type(x) is float for x in v), v)
        self.assertTrue(np.allclose(v, self.bench.view.light_vector(), atol=1e-7))
        self.bench.preset("back")
        self.assertTrue(np.allclose(self.bench.light_vector(), self.bench.view.light_vector(),
                                    atol=1e-7))
        json.dumps(v)


@unittest.skipIf(Raster is None, "presenters.raster недоступен: %s" % (
    RASTER_ERROR if Raster is None else ""))
class TestRasterLight(unittest.TestCase):
    """Поведение света на кадре: куб в кадре 64×64, яркость — среднее серое по пикселям
    тела (всё, что отличается от фона из настроек)."""

    SIZE = 64

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def build(self, **overrides):
        return common.bench(self.tmp.name, common.model(solids.cube("cube")), None,
                            imageWidth=self.SIZE, imageHeight=self.SIZE, **overrides)

    @staticmethod
    def body_pixels(bench) -> np.ndarray:
        img = np.asarray(Raster(bench).image(), dtype=np.float32)
        bg = np.asarray(bench.cfg["background"], dtype=np.float32)
        body = np.any(img != bg, axis=2)
        assert body.any(), "тело не попало в кадр"
        return img[body]

    def brightness(self, bench) -> float:
        return float(self.body_pixels(bench).mean())

    def front_back(self, bench) -> tuple[float, float]:
        bench.preset("front")
        front = self.brightness(bench)
        bench.preset("back")
        back = self.brightness(bench)
        return front, back

    def test_light_behind_camera_lights_what_is_seen(self):
        """Свет за камерой: перед и зад куба освещены одинаково — средняя яркость
        отличается меньше чем на 10 %. Иначе свет остался в мировых осях."""
        bench = self.build()
        self.assertTrue(bench.view.light_follow)
        front, back = self.front_back(bench)
        self.assertLess(abs(front - back) / max(front, back), 0.10, (front, back))

    def test_world_light_stays_put(self):
        """Мировой свет (-0.4,-0.7,0.6) стоит со стороны -Y: грань, видимая с ракурса back
        (y = -1), заметно светлее видимой спереди — кадры отличаются больше чем на 10 %."""
        bench = self.build(lightFollowCamera=False, lightDirection=list(WORLD))
        self.assertFalse(bench.view.light_follow)
        front, back = self.front_back(bench)
        self.assertGreater(abs(front - back) / max(front, back), 0.10, (front, back))
        self.assertGreater(back, front)

    def test_shading_modes_render(self):
        """Оба способа затенения из настроек рисуют кадр нужного размера с телом в нём.
        Плоское красит каждую грань одним цветом: с ракурса quarter видны три грани —
        не больше трёх цветов тела; мягкое даёт переход — цветов заметно больше."""
        counts = {}
        for shading in ("flat", "smooth"):
            with tempfile.TemporaryDirectory() as tmp:
                bench = common.bench(tmp, common.model(solids.cube()), None,
                                     imageWidth=48, imageHeight=40, shading=shading)
                bench.preset("quarter")
                img = Raster(bench).image()
                self.assertEqual(img.size, (48, 40), shading)
                pixels = self.body_pixels(bench)
                counts[shading] = len({tuple(int(c) for c in p) for p in pixels})
        self.assertLessEqual(counts["flat"], 3, counts)
        self.assertGreater(counts["smooth"], 3, counts)

    def test_fill_lights_the_shadow_side(self):
        """Мировой свет из-за куба (источник на -Y, камера на +Y): видна теневая грань.
        С fill = 0 она освещена только рассеянным светом (ровно ambient × 0.72),
        с fill = 0.4 — заметно светлее."""
        dark = self.build(lightFollowCamera=False, lightDirection=[0, -1, 0], fill=0.0)
        dark.preset("front")
        dark_mean = self.brightness(dark)
        lit = self.build(lightFollowCamera=False, lightDirection=[0, -1, 0], fill=0.4)
        lit.preset("front")
        lit_mean = self.brightness(lit)
        self.assertGreater(lit_mean, dark_mean * 1.2, (dark_mean, lit_mean))
        self.assertAlmostEqual(dark_mean, 0.72 * dark.view.ambient * 255.0, delta=2.0)

    def test_diffuse_zero_leaves_only_ambient(self):
        """Без направленного и встречного света всё тело — один цвет ambient × 0.72:
        так видно, что силы из ViewState доезжают до пикселей."""
        bench = self.build(diffuse=0.0, fill=0.0, ambient=0.5)
        bench.preset("quarter")
        pixels = self.body_pixels(bench)
        self.assertEqual(len({tuple(int(c) for c in p) for p in pixels}), 1)
        self.assertAlmostEqual(float(pixels.mean()), 0.72 * 0.5 * 255.0, delta=1.0)


if __name__ == "__main__":
    common.main()
