"""Командная строка верстака — такой же клиент фасада, как и всё остальное.

Здесь нет ни одного вычисления: разбор доводов, вызов метода `MorphBench` и передача
результата слою показа. Именно поэтому всё, что умеет будущее окно, умеет и она.

    python mb.py summary <меш.nif>
    python mb.py shapes  <меш.nif>
    python mb.py bones   <меш.nif> [--shape body] [--find Hand]
    python mb.py morphs  <меш.nif> [--morph Paw] [--shape body]
    python mb.py empty   <меш.nif>
    python mb.py missing <меш.nif> CLAWNeck CLAWEars ...
    python mb.py strain  <меш.nif> [--morph Paw] [--threshold 0.25] [--amount 1.0]
    python mb.py layers  <меш.nif> --morph CLAWBelly [--base body] [--adjacent]
    python mb.py binding <меш.nif> --shape body --morph CLAWPawSize
    python mb.py focus   <меш.nif> [--bone Finger | --morph CLAWPawSize | --shape head]
    python mb.py render  <меш.nif> --out кадр.png [--view front | --look 40,15] [--colour bone]
                         [--slider CLAWEars=1] [--only body,head] [--morph CLAWPawSize]
                         [--focus-bone Finger | --focus-morph CLAWPawSize | --focus-shape head]
                         [--zoom 2 | --zoom-at=2,0.4,-0.3] [--pan=5,-3] [--size 900x900]
                         [--light camera|world] [--light-dir=x,y,z] [--light-power=a,d,f]
    python mb.py colliders [меш.nif] --skeleton <skeleton.nif> [--find Thigh] [--clearance]
    python mb.py fit       <меш.nif> --skeleton <skeleton.nif> [--find Thigh] [--slider X=1]
                           [--only body] [--save новый.nif] [--ppb]
    python mb.py sheet   <меш.nif> --out папка [--views front,side,below] [--prefix view]
    python mb.py web     <меш.nif> --out страница.html  (те же ключи, что у render)
    python mb.py env                                   под MO2 ли мы и какой корень обзора
    python mb.py catalog [папка] [--all] [--find X]    обзор мешей с подобранными морфами
    python mb.py serve   [--root папка] [--port N] [--nif X]   страница со списком мешей

`serve` без ключей просто поднимает сервер: корень обзора - Data игры под MO2, иначе его
называют на странице. Если сервер на этом адресе уже поднят, второй не поднимается:
ему отдаётся корень (из-под MO2 - Data игры, которую видит этот процесс) и открывается
страница. Так работает точка входа для MO2 - `morphbench.exe` рядом, он лишь зовёт
`serve` из-под usvfs.

У render, sheet и web меш можно взять из обзора вместо пути: `--entry <номер|имя> [--root папка]`.
Скелет (`skeleton.nif` в папке меша) подбирается сам, иначе - ключ `--skeleton` у любой
команды; render, sheet и web умеют `--colliders` - слой капсул поверх тела.
Ко всякой команде подходит `--json`: тот же ответ машинно, без таблиц.
Файл морфов подбирается рядом с мешем сам; можно задать явно ключом `--tri`.
Пары чисел с минусом впереди пишутся через знак равенства: `--pan=-5,3`, `--look=-10,5`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from morphbench import MorphBench            # noqa: E402
from presenters import ppb, text             # noqa: E402

# Отказы фасада, которые командная строка показывает одной строкой, а не трассировкой.
_REFUSALS = (ValueError, PermissionError, FileNotFoundError, KeyError)


def _bench(args) -> MorphBench:
    """Открыть меш: по пути либо по записи обзора (`--entry`, `--root`)."""
    bench = MorphBench()
    entry = getattr(args, "entry", None)
    if entry is not None:
        key = int(entry) if str(entry).strip().isdigit() else entry
        bench.open_entry(key, getattr(args, "root", None))
    elif args.nif:
        bench.open(args.nif, args.tri)
    elif not getattr(args, "skeleton", None):
        # Скелет самодостаточен: капсулы можно смотреть и без тела. Тело нужно только
        # посадке и подгонке, и они скажут об этом сами.
        raise ValueError("назовите меш: путь к .nif либо --entry <номер|имя> [--root папка]")
    if getattr(args, "skeleton", None):
        bench.open_skeleton(args.skeleton)
    return bench


def _numbers(text: str, key: str, low: int, high: int) -> list[float]:
    """Числа через запятую из значения ключа; их должно быть от low до high."""
    try:
        values = [float(p) for p in str(text).split(",")]
    except ValueError:
        raise ValueError("%s: ожидались числа через запятую, а не %r" % (key, text))
    if not low <= len(values) <= high:
        raise ValueError("%s: нужно %s чисел, а не %d" % (
            key, str(low) if low == high else "от %d до %d" % (low, high), len(values)))
    return values


def _out(args, data, columns=None, empty="пусто") -> None:
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif columns is not None:
        print(text.table(data, columns, empty))
    else:
        print(data)


def cmd_summary(args) -> int:
    data = _bench(args).summary()
    _out(args, data if args.json else text.summary(data))
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
    _out(args, _bench(args).layers(args.morph, args.base, args.adjacent),
         [("follower", "оболочка"), ("followerMax", "её макс"),
          ("baseMax", "у кожи"), ("ratio", "доля"), ("missing", "не следует"),
          ("contact", "над сдвигом"), ("adjacent", "смежна"), ("expectedMax", "должна на")],
         "смежных оболочек нет" if args.adjacent else "пусто")
    return 0


def cmd_binding(args) -> int:
    bench = _bench(args)
    shape = args.shape or bench.base_shape()
    if args.json:
        print(json.dumps({"touched": bench.morph_bones(shape, args.morph),
                          "leftBehind": bench.bones_left_behind(shape, args.morph)},
                         ensure_ascii=False, indent=2))
        return 0
    print("кости, чьи вершины морф двигает:")
    print(text.table(bench.morph_bones(shape, args.morph),
                     [("bone", "кость"), ("share", "доля морфа")], "ни одной"))
    print()
    print("кости, сдвинутые лишь частично — здесь поверхность растягивается:")
    print(text.table(bench.bones_left_behind(shape, args.morph),
                     [("bone", "кость"), ("leftBehind", "осталось на месте")],
                     "таких нет"))
    return 0


def cmd_focus(args) -> int:
    """Наведение камеры числами: куда она смотрит и что могла бы взять в кадр."""
    bench = _bench(args)
    if args.bone or args.morph or args.shape:
        if args.bone:
            state = bench.focus_bone(args.bone)
        elif args.morph:
            state = bench.focus_morph(args.morph)
        else:
            state = bench.focus_shape(args.shape)
        focus = state["focus"]
        _out(args, focus if args.json else "смотрим на %s: центр %s, радиус %.2f" % (
            focus["name"], " ".join("%g" % x for x in focus["centre"]), focus["radius"]))
        return 0
    targets = bench.focus_targets()
    if args.json:
        print(json.dumps(targets, ensure_ascii=False, indent=2))
        return 0
    cols = [("name", "цель"), ("centre", "центр X Y Z"), ("radius", "радиус")]
    for kind, title in (("shapes", "части меша"), ("bones", "кости"), ("morphs", "морфы")):
        print("%s:" % title)
        print(text.table(targets[kind], cols, "нет"))
        print()
    return 0


def _apply_view(bench: MorphBench, args) -> None:
    """Ключи показа - в вызовы фасада, в том порядке, в каком они друг от друга зависят.
    Ключа может не быть у команды вовсе (у `fit` нет ракурса): тогда он не задан."""
    opt = lambda name, default=None: getattr(args, name, default)  # noqa: E731
    for pair in opt("slider") or []:
        name, _, value = pair.partition("=")
        bench.set_slider(name.strip(), float(value))
    if opt("only"):
        bench.only([s.strip() for s in args.only.split(",") if s.strip()])
    if opt("colour", "shade") != "shade" or opt("morph"):
        bench.colour_by(opt("colour", "shade"), opt("morph"))
    if opt("zoom") is not None:
        bench.zoom(args.zoom)
    if opt("size"):
        w, _, h = args.size.partition("x")
        if not (w.strip().isdigit() and h.strip().isdigit()):
            raise ValueError("--size: ожидалось ШИРИНАxВЫСОТА, например 900x900, а не %r" % args.size)
        bench.resize(int(w), int(h))
    if opt("focus_bone"):
        bench.focus_bone(args.focus_bone)
    elif opt("focus_morph"):
        bench.focus_morph(args.focus_morph)
    elif opt("focus_shape"):
        bench.focus_shape(args.focus_shape)
    if opt("view"):
        bench.preset(args.view)
    if opt("look"):
        bench.look(*_numbers(args.look, "--look", 2, 2))
    if opt("pan"):
        bench.pan(*_numbers(args.pan, "--pan", 2, 2))
    if opt("zoom_at"):
        bench.zoom_at(*_numbers(args.zoom_at, "--zoom-at", 3, 3))
    if opt("light"):
        bench.light_follow_camera(args.light == "camera")
    if opt("light_dir"):
        bench.light_direction(*_numbers(args.light_dir, "--light-dir", 3, 3))
    if opt("light_power"):
        bench.light_power(*_numbers(args.light_power, "--light-power", 1, 3))
    if opt("colliders"):
        if not bench.has_skeleton():
            raise ValueError("--colliders без скелета: рядом с мешем нет %s, добавьте "
                             "--skeleton <skeleton.nif>" % bench.cfg["skeletonFile"])
        bench.show_colliders(True, bool(opt("bumper")))


def cmd_colliders(args) -> int:
    """Капсулы скелета числами: где стоят, какие и как сидят по коже."""
    bench = _bench(args)
    if not bench.has_skeleton():
        raise ValueError("назовите скелет: --skeleton <skeleton.nif>")
    rows = bench.colliders(args.find)
    if args.clearance:
        if not bench.is_open():
            raise ValueError("--clearance меряет капсулы по коже: назовите ещё и меш")
        fit = {r["bone"]: r for r in bench.collider_clearance(args.find)}
        for row in rows:
            row["clearance"] = fit.get(row["bone"])
    _out(args, rows if args.json else text.colliders(rows))
    return 0


def cmd_fit(args) -> int:
    """Посадить капсулы по коже при нынешних ползунках."""
    bench = _bench(args)
    if not bench.has_skeleton():
        raise ValueError("назовите скелет: --skeleton <skeleton.nif>")
    _apply_view(bench, args)
    rows = bench.collider_fit(args.find, args.percentile)
    result = {"fitted": rows}
    if args.save:
        result["saved"] = bench.collider_save(args.save)
    if args.ppb:
        result["ppb"] = ppb.lines(bench.collider_local(args.find))
    if args.json:
        _out(args, result)
        return 0
    lines = [text.fitted(rows)]
    if args.save:
        lines.append("скелет: %s" % result["saved"])
    if args.ppb:
        lines.append("\n".join(result["ppb"]))
    _out(args, "\n".join(lines))
    return 0


def cmd_render(args) -> int:
    from presenters.raster import Raster
    bench = _bench(args)
    _apply_view(bench, args)
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


def cmd_web(args) -> int:
    from presenters.web import WebPage
    bench = _bench(args)
    _apply_view(bench, args)
    path = WebPage(bench).save(args.out)
    _out(args, {"saved": str(path), "view": bench.view_state(),
                "sliders": bench.sliders()} if args.json else "страница: %s" % path)
    return 0


def cmd_env(args) -> int:
    """Где запущены: под MO2 или нет, какие игры видны, какой корень обзора по умолчанию."""
    env = MorphBench().environment()
    if args.json:
        print(json.dumps(env, ensure_ascii=False, indent=2))
        return 0
    print("под MO2:        %s" % ("да" if env["insideMo2"] else "нет"))
    print("корень обзора:  %s" % (env["dataRoot"] or "не задан - назовите папку"))
    print("игры в реестре: %s" % (", ".join("%s (%s)" % (g["game"], g["root"])
                                             for g in env["games"]) or "нет"))
    return 0


def cmd_catalog(args) -> int:
    """Обзор мешей под корнем: номер, путь от корня, формат морфов."""
    bench = MorphBench()
    rows = bench.catalog(args.root, with_morphs=not args.all)
    if args.find:
        low = args.find.lower()
        rows = [r for r in rows if low in r["name"].lower()]
    _out(args, rows, [("index", "№"), ("name", "меш"), ("kind", "морфы")],
         "мешей не найдено" if not args.all else "мешей нет")
    return 0


def cmd_serve(args) -> int:
    """Страница со списком мешей на локальном порту: выбор тела без перезапуска.

    Без ключей просто поднимает сервер. Если на этом адресе сервер уже поднят, второй
    не поднимается: ему отдаётся корень обзора и открывается страница. Из-под MO2 это
    и есть передача пути - Data игры, которую видит этот процесс сквозь usvfs.
    """
    from presenters.serve import ServerLink, WebServer
    bench = MorphBench()
    cfg = bench.cfg
    link = ServerLink(args.host or cfg["serveHost"],
                      cfg["servePort"] if args.port is None else args.port)
    state = link.probe()
    if state == "busy":
        raise ValueError("порт %d занят другой программой; назовите другой ключом --port"
                         % link.port)
    if state == "ours":
        return _hand_over(bench, link, args)
    server = WebServer(bench, root=args.root, host=args.host, port=args.port,
                       with_morphs=not args.all)
    if args.nif:
        bench.open(args.nif, args.tri, getattr(args, "skeleton", None))
    _out(args, {"started": True, "url": server.url,
                "root": None if server.root is None else str(server.root),
                "insideMo2": bench.environment()["insideMo2"]} if args.json else
         "обзор: %s\nстраница: %s" % (server.root or "не задан - назовите папку на странице",
                                        server.url))
    sys.stdout.flush()                      # адрес виден сразу, даже если вывод в трубу
    server.run(open_browser=not args.no_browser)
    return 0


def _hand_over(bench: MorphBench, link, args) -> int:
    """Сервер уже поднят: отдать ему корень и открыть страницу, а не поднимать второй."""
    here = bench.environment()
    there = link.environment()
    if here["insideMo2"] and not there["insideMo2"]:
        raise ValueError("сервер на %s поднят вне MO2 и не видит мешей сборки; закройте его "
                         "и запустите снова из-под MO2" % link.url)
    root = args.root if args.root is not None else here["dataRoot"]
    handed = link.set_root(root) if root is not None else None
    if args.nif:
        raise ValueError("сервер уже поднят на %s: выберите меш на странице, --nif здесь "
                         "не действует" % link.url)
    if not args.no_browser:
        link.open_page()
    _out(args, {"started": False, "url": link.url, "root": there.get("root") if handed is None
                else handed["root"], "handed": handed, "insideMo2": there["insideMo2"]}
         if args.json else
         "уже поднят: %s%s" % (link.url, "" if handed is None else
                                "\nобзор: %s (%d мешей)" % (handed["root"], handed["meshes"])))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="машинный вывод вместо таблиц")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, nif_required=True, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("nif", nargs=None if nif_required else "?", default=None)
        p.add_argument("--tri", default=None)
        p.add_argument("--skeleton", default=None,
                       help="файл скелета: из него читаются капсулы столкновений")
        # Без умолчания: иначе --json, поставленный ПЕРЕД именем команды, затирался бы.
        p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
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
    p.add_argument("--threshold", type=float, default=None,
                   help="порог растяжения; по умолчанию strainThreshold из настроек")
    p = add("layers", cmd_layers, help="следуют ли оболочки за кожей")
    p.add_argument("--morph", required=True)
    p.add_argument("--base", default=None, help="базовая часть; по умолчанию baseShape из настроек")
    p.add_argument("--adjacent", action="store_true",
                   help="только оболочки над сдвигаемой кожей - те, что обязаны следовать")
    p = add("binding", cmd_binding, help="к каким костям привязано то, что двигает морф")
    p.add_argument("--shape", default=None, help="часть меша; по умолчанию baseShape из настроек")
    p.add_argument("--morph", required=True)
    p = add("colliders", cmd_colliders, nif_required=False,
            help="капсулы столкновений скелета")
    p.add_argument("--find", default=None, help="подстрока имени кости")
    p.add_argument("--clearance", action="store_true",
                   help="и посадка по коже при нынешних ползунках")
    p = add("focus", cmd_focus, help="наведение камеры: на кость, морф или часть")
    p.add_argument("--bone", default=None, help="имя кости или его часть")
    p.add_argument("--morph", default=None)
    p.add_argument("--shape", default=None)

    p = add("fit", cmd_fit, nif_required=False,
            help="посадить капсулы по коже при нынешних ползунках")
    p.add_argument("--entry", default=None)
    p.add_argument("--root", default=None)
    p.add_argument("--find", default=None, help="подстрока имени кости")
    p.add_argument("--percentile", type=float, default=None,
                   help="доля точек внутри радиуса; по умолчанию из настроек")
    p.add_argument("--save", default=None, help="записать новый файл скелета")
    p.add_argument("--ppb", action="store_true",
                   help="выдать строки настроек Precision Physic Bodies")
    p.add_argument("--slider", action="append", default=[])
    p.add_argument("--only", default=None)

    for name, fn, hlp in (("render", cmd_render, "кадр в PNG"),
                          ("sheet", cmd_sheet, "несколько ракурсов подряд"),
                          ("web", cmd_web, "самодостаточная страница со смотрелкой")):
        p = add(name, fn, nif_required=False, help=hlp)
        p.add_argument("--entry", default=None,
                       help="меш из обзора по номеру или имени вместо пути к .nif")
        p.add_argument("--root", default=None, help="корень обзора для --entry")
        p.add_argument("--out", required=True)
        p.add_argument("--view", default=None)
        p.add_argument("--colour", "--color", dest="colour", default="shade",
                       choices=["shade", "bone", "morph", "strain"])
        p.add_argument("--morph", default=None)
        p.add_argument("--slider", action="append", default=[])
        p.add_argument("--only", default=None)
        p.add_argument("--zoom", type=float, default=None)
        p.add_argument("--look", default=None,
                       help="произвольный ракурс: поворот,подъём в градусах (с минусом: --look=-10,5)")
        p.add_argument("--pan", default=None,
                       help="сдвиг кадра вправо,вверх в единицах модели (с минусом: --pan=-5,3)")
        p.add_argument("--size", default=None)
        p.add_argument("--zoom-at", dest="zoom_at", default=None,
                       help="масштаб к точке: новый масштаб,x,y - точка в долях половины "
                            "меньшей стороны кадра от центра, вправо и вверх (--zoom-at=2,0.4,-0.3)")
        p.add_argument("--light", choices=["camera", "world"], default=None,
                       help="свет за камерой (camera) или отдельно от неё (world)")
        p.add_argument("--light-dir", dest="light_dir", default=None,
                       help="направление на источник x,y,z: в осях камеры при --light camera, "
                            "иначе мировое (--light-dir=0.3,0.5,0.8)")
        p.add_argument("--light-power", dest="light_power", default=None,
                       help="силы света: рассеянная,направленная[,встречная] (--light-power=0.3,0.7,0.15)")
        p.add_argument("--focus-bone", dest="focus_bone", default=None)
        p.add_argument("--focus-morph", dest="focus_morph", default=None)
        p.add_argument("--focus-shape", dest="focus_shape", default=None)
        p.add_argument("--colliders", action="store_true",
                       help="слой капсул поверх тела; нужен --skeleton")
        p.add_argument("--bumper", action="store_true",
                       help="и цилиндр перемещения: он вчетверо больше тела")
        if name == "sheet":
            p.add_argument("--views", default=None)
            p.add_argument("--prefix", default="view")

    # Команды без меша: окружение, обзор и страница со списком.
    p = sub.add_parser("env", help="под MO2 ли запущены и какой корень обзора")
    p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    p.set_defaults(func=cmd_env)
    p = sub.add_parser("catalog", help="обзор мешей под папкой")
    p.add_argument("root", nargs="?", default=None,
                   help="корень обзора; без него - Data игры под MO2 либо catalogRoot из настроек")
    p.add_argument("--all", action="store_true", help="и меши без файла морфов")
    p.add_argument("--find", default=None, help="подстрока пути")
    p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    p.set_defaults(func=cmd_catalog)
    p = sub.add_parser("serve", help="страница со списком мешей на локальном порту")
    p.add_argument("--root", default=None, help="корень обзора; умолчание как у catalog")
    p.add_argument("--nif", default=None, help="меш, открытый сразу")
    p.add_argument("--tri", default=None)
    p.add_argument("--host", default=None, help="адрес; по умолчанию serveHost из настроек")
    p.add_argument("--port", type=int, default=None, help="порт; по умолчанию servePort из настроек")
    p.add_argument("--all", action="store_true", help="и меши без файла морфов")
    p.add_argument("--no-browser", dest="no_browser", action="store_true",
                   help="не открывать браузер самому")
    p.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    p.set_defaults(func=cmd_serve)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except _REFUSALS as e:
        # Отказ фасада - не сбой программы: одна строка и код 2, как у argparse.
        message = e.args[0] if e.args and isinstance(e.args[0], str) else str(e)
        print("%s: %s" % (args.cmd, message), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
