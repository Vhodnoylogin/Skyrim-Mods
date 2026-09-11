"""Рисует значок верстака: узлы сетки, связанные рёбрами.

Почему сценарием, а не готовым файлом. У модуля правило: продукт не версионируется,
версионируется то, из чего он получается. Значок — такой же продукт: два десятка чисел
дают его заново, а двоичный `.ico` в истории git показывал бы только «файл изменился».

Почему сетка, а не зверь. Верстак работает с ЛЮБЫМИ морфами — человеческим телом,
бронёй, чем угодно, где есть вершины и файл `.tri`. Волк здесь частный случай, и значок
со зверем обещал бы инструмент, которого нет. Узлы и рёбра — это ровно то, что верстак
и показывает: точки и связи между ними.

Почему один узел сдвинут и выкрашен. Морф — это смещение вершины; неподвижная решётка
рисовала бы просмотрщик, а не верстак. Сдвинутый угол и делает из геометрии действие.

    python launcher/make-icon.py [--out launcher/morphbench.ico] [--show]

`--show` рядом с `.ico` кладёт ещё и `.png` в 256 точек — посмотреть глазами.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

#: Размеры, которые Windows берёт из значка: панель задач, рабочий стол, крупные плитки.
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: Плашка тёмная, узлы светлые: на светлой и на тёмной панели задач значок остаётся
#: различим, потому что контраст даёт сама плашка, а не фон системы.
BACK = (32, 36, 44, 255)
NODE = (232, 214, 186, 255)
EDGE = (150, 142, 128, 255)
ACCENT = (96, 176, 208, 255)

#: Узлы в долях стороны: x, y, радиус, цвет. Правый верхний вытянут наружу и выкрашен —
#: это и есть морф. Радиусы крупные намеренно: в шестнадцать точек узел вырождается
#: в три пикселя, и всё, что тоньше, пропадает совсем.
NODES = (
    (0.27, 0.35, 0.100, NODE),
    (0.73, 0.20, 0.120, ACCENT),
    (0.79, 0.71, 0.100, NODE),
    (0.30, 0.76, 0.100, NODE),
)

#: Рёбра: четырёхугольник плюс диагональ. Диагональ важна — без неё рисунок читается
#: как рамка, а с ней как две грани, то есть как сетка.
EDGES = ((0, 1), (1, 2), (2, 3), (3, 0), (0, 2))

#: В шестнадцать и двадцать четыре точки рисуется УПРОЩЁННЫЙ вариант: диагональ там
#: короче ширины линии и сливается с рёбрами в пятно. Значок с разной прорисовкой по
#: размерам — обычное дело: в маленьком слое важна опознаваемость, а не полнота.
SMALL_UPTO = 24
EDGES_SMALL = ((0, 1), (1, 2), (2, 3), (3, 0))
SMALL_NODE = 1.18
SMALL_EDGE = 1.30


def graph(side: int) -> Image.Image:
    """Один слой значка. Рисуется вчетверо крупнее и уменьшается — иначе края рваные."""
    k = 4
    big = side * k
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = big * 0.22
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=r, fill=BACK)
    # Тонкая рамка цветом отлива: на тёмном фоне рабочего стола плашка иначе сливается.
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=r, outline=ACCENT,
                        width=max(1, int(big * 0.02)))

    small = side <= SMALL_UPTO
    edges = EDGES_SMALL if small else EDGES
    width = max(1, int(big * 0.055 * (SMALL_EDGE if small else 1.0)))
    for a, b in edges:
        xa, ya = NODES[a][0] * big, NODES[a][1] * big
        xb, yb = NODES[b][0] * big, NODES[b][1] * big
        d.line((xa, ya, xb, yb), fill=EDGE, width=width)

    for cx, cy, rad, colour in NODES:
        x, y = cx * big, cy * big
        rr = rad * big * (SMALL_NODE if small else 1.0)
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=colour)
    return img.resize((side, side), Image.LANCZOS)


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else here / "morphbench.ico"
    layers = [graph(s) for s in SIZES]
    out.parent.mkdir(parents=True, exist_ok=True)
    # append_images обязателен: без него Pillow берёт ОДНУ картинку и сам ужимает её
    # под каждый размер, а нарисованные по отдельности слои молча выбрасывает —
    # упрощённый мелкий вариант тогда просто не доезжает до файла.
    layers[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES],
                    append_images=layers[:-1])
    print("значок: %s (%d слоёв: %s)" % (out, len(SIZES),
                                         ", ".join(str(s) for s in SIZES)))
    if "--show" in argv:
        png = out.with_suffix(".png")
        layers[-1].save(png)
        print("на посмотреть: %s" % png)
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
