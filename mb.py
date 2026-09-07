"""Командная строка верстака — такой же клиент фасада, как и всё остальное.

Здесь нет ни одного вычисления: разбор доводов, вызов метода `MorphBench` и передача
результата слою показа. Именно поэтому всё, что умеет будущее окно, умеет и она.

    python mb.py summary <меш.nif>
    python mb.py shapes  <меш.nif>
    python mb.py bones   <меш.nif> [--shape body] [--find Hand]
    python mb.py morphs  <меш.nif> [--morph Paw] [--shape body]
    python mb.py empty   <меш.nif>
    python mb.py missing <меш.nif> CLAWNeck CLAWEars ...
    python mb.py strain  <меш.nif> [--morph Paw] [--threshold 0.25]
    python mb.py layers  <меш.nif> --morph CLAWBelly [--base body]
    python mb.py binding <меш.nif> --shape body --morph CLAWPawSize
    python mb.py render  <меш.nif> --out кадр.png [--view front] [--colour bone]
                         [--slider CLAWEars=1] [--only body,head] [--morph CLAWPawSize]
    python mb.py sheet   <меш.nif> --out папка [--views front,side,below]

Ко всякой команде подходит `--json`: тот же ответ машинно, без таблиц.
Файл морфов подбирается рядом с мешем сам; можно задать явно ключом `--tri`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from morphbench import MorphBench            # noqa: E402
from presenters import text                  # noqa: E402


def _bench(args) -> MorphBench:
    bench = MorphBench()
    bench.open(args.nif, args.tri)
    return bench


def _out(args, data, columns=None, empty="пусто") -> None:
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif columns is not None:
        print(text.table(data, columns, empty))
    else:
        print(data)


def cmd_summary(args) -> int:
    print(text.summary(_bench(args).summary()))
    return 0


def cmd_shapes(args) -> int:
    _out(args, _bench(args).shapes(),
         [("name", "часть"), ("vertices", "вершин"), ("triangles", "треуг."),
          ("bones", "костей"), ("morphs", "морфов"), ("bounds", "охват X / Y / Z")])
    return 0


def cmd_bones(args) -> int:
    _out(args, _bench(args).bones(args.shape, args.find),
         [("bone", "кость"), ("vertices", "вершин")])
    return 0


def cmd_morphs(args) -> int:
    _out(args, _bench(args).morph_stats(args.morph, args.shape),
         [("shape", "часть"), ("morph", "морф"), ("vertices", "вершин"),
          ("maxShift", "макс"), ("meanShift", "средн"), ("bounds", "охват X / Y / Z")])
    return 0


def cmd_empty(args) -> int:
    rows = _bench(args).empty_morphs()
    _out(args, rows, [("shape", "часть"), ("morph", "морф")], "пустых морфов нет")
    return 0


def cmd_missing(args) -> int:
    rows = _bench(args).missing_morphs(args.names)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
    elif rows:
        print("в файле нет: %s" % ", ".join(rows))
    else:
        print("все названные ползунки на месте")
    return 0


def cmd_strain(args) -> int:
    _out(args, _bench(args).strain(args.amount, args.threshold, args.morph),
         [("shape", "часть"), ("morph", "морф"), ("maxStrain", "макс"),
          ("p99Strain", "99%"), ("overThreshold", "рёбер сверх"),
          ("worstBounds", "где именно X / Y / Z")])
    return 0


def cmd_layers(args) -> int:
    _out(args, _bench(args).layers(args.morph, args.base),
         [("follower", "оболочка"), ("followerMax", "её макс"),
          ("baseMax", "у кожи"), ("ratio", "доля"), ("missing", "не следует")])
    return 0


def cmd_binding(args) -> int:
    bench = _bench(args)
    if args.json:
        print(json.dumps({"touched": bench.morph_bones(args.shape, args.morph),
                          "leftBehind": bench.bones_left_behind(args.shape, args.morph)},
                         ensure_ascii=False, indent=2))
        return 0
    print("кости, чьи вершины морф двигает:")
    print(text.table(bench.morph_bones(args.shape, args.morph),
                     [("bone", "кость"), ("share", "доля морфа")], "ни одной"))
    print()
    print("кости, сдвинутые лишь частично — здесь поверхность растягивается:")
    print(text.table(bench.bones_left_behind(args.shape, args.morph),
                     [("bone", "кость"), ("leftBehind", "осталось на месте")],
                     "таких нет"))
    return 0


def _apply_view(bench: MorphBench, args) -> None:
    for pair in args.slider or []:
        name, _, value = pair.partition("=")
        bench.set_slider(name.strip(), float(value))
    if args.only:
        bench.only([s.strip() for s in args.only.split(",") if s.strip()])
    if args.colour != "shade" or args.morph:
        bench.colour_by(args.colour, args.morph)
    if args.zoom:
        bench.zoom(args.zoom)
    if args.size:
        w, _, h = args.size.partition("x")
        bench.view.resize(int(w), int(h))


def cmd_render(args) -> int:
    from presenters.raster import Raster
    bench = _bench(args)
    _apply_view(bench, args)
    bench.preset(args.view) if args.view else None
    path = Raster(bench).save(args.out)
    _out(args, {"saved": str(path), "view": bench.view_state(),
                "sliders": bench.sliders()} if args.json else "кадр: %s" % path)
    return 0


def cmd_sheet(args) -> int:
    from presenters.raster import Raster
    bench = _bench(args)
    _apply_view(bench, args)
    views = [v.strip() for v in args.views.split(",")] if args.views else None
    saved = Raster(bench).contact_sheet(args.out, views, args.prefix)
    _out(args, {"saved": [str(p) for p in saved]} if args.json
         else "\n".join(str(p) for p in saved))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="машинный вывод вместо таблиц")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("nif")
        p.add_argument("--tri", default=None)
        p.add_argument("--json", action="store_true")
        p.set_defaults(func=fn)
        return p

    add("summary", cmd_summary, help="что за меш открыт")
    add("shapes", cmd_shapes, help="части меша")
    p = add("bones", cmd_bones, help="кости и сколько вершин они держат")
    p.add_argument("--shape", default=None)
    p.add_argument("--find", default=None)
    p = add("morphs", cmd_morphs, help="что делает каждый ползунок")
    p.add_argument("--morph", default=None)
    p.add_argument("--shape", default=None)
    add("empty", cmd_empty, help="ползунки, которые не двигают ничего")
    p = add("missing", cmd_missing, help="каких ожидаемых ползунков нет в файле")
    p.add_argument("names", nargs="+")
    p = add("strain", cmd_strain, help="где морф рвёт поверхность")
    p.add_argument("--morph", default=None)
    p.add_argument("--amount", type=float, default=1.0)
    p.add_argument("--threshold", type=float, default=0.25)
    p = add("layers", cmd_layers, help="следуют ли оболочки за кожей")
    p.add_argument("--morph", required=True)
    p.add_argument("--base", default="body")
    p = add("binding", cmd_binding, help="к каким костям привязано то, что двигает морф")
    p.add_argument("--shape", default="body")
    p.add_argument("--morph", required=True)

    for name, fn, hlp in (("render", cmd_render, "кадр в PNG"),
                          ("sheet", cmd_sheet, "несколько ракурсов подряд")):
        p = add(name, fn, help=hlp)
        p.add_argument("--out", required=True)
        p.add_argument("--view", default=None)
        p.add_argument("--colour", "--color", dest="colour", default="shade",
                       choices=["shade", "bone", "morph", "strain"])
        p.add_argument("--morph", default=None)
        p.add_argument("--slider", action="append", default=[])
        p.add_argument("--only", default=None)
        p.add_argument("--zoom", type=float, default=None)
        p.add_argument("--size", default=None)
        if name == "sheet":
            p.add_argument("--views", default=None)
            p.add_argument("--prefix", default="view")

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
