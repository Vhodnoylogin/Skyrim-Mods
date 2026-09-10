"""Рисует значок верстака: отпечаток лапы на тёмной плашке.

Почему сценарием, а не готовым файлом. У модуля правило: продукт не версионируется,
версионируется то, из чего он получается. Значок — такой же продукт: два десятка чисел
дают его заново, а двоичный `.ico` в истории git показывал бы только «файл изменился».

Почему лапа. Значок опознают в панели задач размером шестнадцать точек, где от рисунка
остаются силуэт и контраст. Лапа при таком размере узнаётся по пятну с четырьмя точками
над ним; морда зверя в шестнадцать точек превращается в кляксу.

    python launcher/make-icon.py [--out launcher/morphbench.ico] [--show]

`--show` рядом с `.ico` кладёт ещё и `.png` в 256 точек — посмотреть глазами.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

#: Размеры, которые Windows берёт из значка: панель задач, рабочий стол, крупные плитки.
SIZES = (16, 24, 32, 48, 64, 128, 256)

#: Плашка тёмная, лапа светлая с тёплым отливом: на светлой и на тёмной панели задач
#: значок остаётся различим, потому что контраст даёт сама плашка, а не фон системы.
BACK = (32, 36, 44, 255)
PAW = (232, 214, 186, 255)
ACCENT = (96, 176, 208, 255)

#: Лапа в долях стороны: подушечка и четыре пальца. Числа подобраны так, чтобы
#: в шестнадцать точек пальцы не слипались с подушечкой в одно пятно.
PAD = (0.50, 0.66, 0.30, 0.24)                     # центр x, центр y, ширина, высота
TOES = (((0.28, 0.42), (0.115, 0.145)),
        ((0.435, 0.335), (0.105, 0.135)),
        ((0.585, 0.335), (0.105, 0.135)),
        ((0.735, 0.42), (0.115, 0.145)))


def ellipse(draw: ImageDraw.ImageDraw, side: int, cx: float, cy: float,
            w: float, h: float, fill) -> None:
    x, y = cx * side, cy * side
    rx, ry = w * side / 2.0, h * side / 2.0
    draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=fill)


def paw(side: int) -> Image.Image:
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
    ellipse(d, big, *PAD, fill=PAW)
    for (cx, cy), (w, h) in TOES:
        ellipse(d, big, cx, cy, w, h, fill=PAW)
    return img.resize((side, side), Image.LANCZOS)


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else here / "morphbench.ico"
    layers = [paw(s) for s in SIZES]
    out.parent.mkdir(parents=True, exist_ok=True)
    layers[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES])
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
