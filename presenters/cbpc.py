"""Слой показа: настройки CBPC (Physics with Collisions) для цепочек костей.

CBPC качает кости по группам настроек, и своя кость у него называется прямо: строка
`Кость=Группа[=Условие]` в разделе `[ConfigMap]` файла `CBPCMasterConfig*.txt` приписывает
кость к группе, числа группы лежат в `CBPConfig*.txt` строками `Группа.параметр значение`,
а столкновения - в `CBPCollisionConfig*.txt`: кость перечисляется в `[AffectedNodes]`,
и под заголовком `[Кость]` идут её фигуры в системе кости, в единицах игры: сфера
`x,y,z,r | x,y,z,r`, капсула `x,y,z,r & x,y,z,r | x,y,z,r & x,y,z,r` - две половины
через `|` для веса 0 и 100. Звенья одной цепочки CBPC советует брать в `<` и `>`:
тогда они считаются по порядку, а не вразнобой.

Такой же клиент фасада, как `ppb`: берёт `chain_capsules(engine="cbpc")`, `chains()`
для шапки и числа из настроек - и только раскладывает их в строки. Цепочки, отданные
другому движку, сюда не попадают: SMP и CBPC - разные движки, одну кость обоим отдавать
нельзя; шапка перечисляет, кто кому отдан. Ядро о CBPC не знает.
"""
from __future__ import annotations

import re

from . import text as _text

#: Как CBPC пишет свои ручки: (имя в файле, ключ настроек). Порядок - как в живом файле.
_GROUP_SCALARS = (
    ("stiffness", "cbpcStiffness"),
    ("stiffness2", "cbpcStiffness2"),
    ("damping", "cbpcDamping"),
)
_COLLISION_SCALARS = (
    ("collisionFriction", "cbpcCollisionFriction"),
    ("collisionPenetration", "cbpcCollisionPenetration"),
    ("collisionMultipler", "cbpcCollisionMultiplier"),        # так пишет сам CBPC
    ("collisionMultiplerRot", "cbpcCollisionMultiplierRot"),
    ("collisionElastic", "cbpcCollisionElastic"),
)
_AXES = "XYZ"


def selected(rows: list[dict]) -> list[dict]:
    """Какие из отданных CBPC цепочек попадают в вывод: годные - с кожей и без обрыва."""
    return [r for r in rows if r["fit"]]


def alias(stem: str) -> str:
    """Имя группы настроек по стволу цепочки: «NPC EarL [EarL]Bone» -> «MBEarLBone».
    Метка в скобках у кости может стоять и посреди имени - выбрасывается вся."""
    core = re.sub(r"^\s*NPC\s+", "", re.sub(r"\[[^\]]*\]", "", stem))
    return "MB" + re.sub(r"[^A-Za-z0-9]", "", core)


def _num(value) -> str:
    return ("%.3f" % float(value)).rstrip("0").rstrip(".") or "0"


def capsule_line(cap: dict) -> str:
    """Строка капсулы: концы с радиусом через `&`, половины веса 0 и 100 через `|`.
    Половины одинаковы: капсула посажена по одному телу."""
    half = "%s & %s" % (",".join(_num(v) for v in (*cap["p1"], cap["radius"])),
                        ",".join(_num(v) for v in (*cap["p2"], cap["radius"])))
    return "%s | %s" % (half, half)


def group_lines(name: str, cfg) -> list[str]:
    """Строки `Группа.параметр значение` для CBPConfig - числа из настроек."""
    out = ["%s.%s %g" % (name, key, float(cfg[cfgkey])) for key, cfgkey in _GROUP_SCALARS]
    offset = float(cfg["cbpcMaxOffset"])
    for axis in _AXES:
        out.append("%s.%smaxoffset %g" % (name, axis, offset))
        out.append("%s.%sminoffset %g" % (name, axis, -offset))
    out.append("%s.timetick %g" % (name, float(cfg["cbpcTimeTick"])))
    for axis, v in zip(_AXES, cfg["cbpcLinear"]):
        out.append("%s.linear%s %g" % (name, axis, float(v)))
    spread = float(cfg["cbpcSpreadForce"])
    for axis in _AXES:
        for other in _AXES:
            if other != axis:
                out.append("%s.linear%sspreadforce%s %g" % (name, axis, other, spread))
    for axis, v in zip(_AXES, cfg["cbpcRotational"]):
        out.append("%s.rotational%s %g" % (name, axis, float(v)))
    for axis, row in zip(_AXES, cfg["cbpcLinearRotation"]):
        for other, v in zip(_AXES, row):
            out.append("%s.linear%srotation%s %g" % (name, axis, other, float(v)))
    out.append("%s.timeStep %g" % (name, float(cfg["cbpcTimeStep"])))
    for key, cfgkey in _COLLISION_SCALARS:
        out.append("%s.%s %g" % (name, key, float(cfg[cfgkey])))
    push = float(cfg["cbpcCollisionOffset"])
    for axis in _AXES:
        out.append("%s.collision%smaxOffset %g" % (name, axis, push))
        out.append("%s.collision%sminOffset %g" % (name, axis, -push))
    return out


def text(rows: list[dict], chains: list[dict], cfg, title: str | None = None) -> str:
    """Текст настроек CBPC по цепочкам, отданным ему.

    `rows` - `MorphBench.chain_capsules("cbpc")`, `chains` - `MorphBench.chains()` целиком
    (ради шапки: кто кому отдан), `cfg` - настройки с числами `cbpc*`. Три раздела -
    три файла CBPC; каждый вписывается в свой.
    """
    head = ["# morphbench: настройки CBPC%s" % ((" для " + title) if title else ""),
            "# цепочки:"]
    head += ["#   " + line for line in _text.assignments(chains, "cbpc")]
    head += ["# Капсулы посажены по коже каждого звена при нынешних ползунках, в системе своей",
             "# кости, в единицах игры; обе половины строки (вес 0 | вес 100) одинаковы.",
             "# Три раздела ниже - три файла CBPC в SKSE\\Plugins\\: каждый раздел вписать в свой.",
             "# Условие группы (например, IsRaceName(...)) в [ConfigMap] дописывается самому."]
    wanted = selected(rows)
    if not wanted:
        return "\n".join(head + ["# CBPC не отдано ни одной годной цепочки: писать нечего."]) + "\n"

    out = list(head)
    out += ["", "# ---- CBPCMasterConfig_*.txt, раздел [ConfigMap]: кость = группа ----",
            "[ConfigMap]"]
    for r in wanted:
        out.append("<")
        out += ["%s=%s" % (l["bone"], alias(r["chain"])) for l in r["links"]]
        out.append(">")

    out += ["", "# ---- CBPConfig_*.txt: качание группы ----"]
    for r in wanted:
        out.append("# %s" % r["chain"])
        out += group_lines(alias(r["chain"]), cfg)
        out.append("")

    out += ["# ---- CBPCollisionConfig_*.txt: столкновения ----", "[AffectedNodes]"]
    bare = []
    for r in wanted:
        for l in r["links"]:
            if l["capsule"] is None:
                bare.append("# %s: кожи на капсулу не хватило (%d точек)" % (l["bone"], l["points"]))
            else:
                out.append(l["bone"])
    out += bare
    for r in wanted:
        for l in r["links"]:
            if l["capsule"] is not None:
                out += ["", "[%s]" % l["bone"], capsule_line(l["capsule"])]
    return "\n".join(out) + "\n"

# ---- проверка готового файла ------------------------------------------------------------------
_KNOWN_SECTIONS = {"extraoptions", "playernodes", "affectednodes", "collidernodes", "configmap"}


def _numbers(chunk: str) -> bool:
    try:
        [float(x) for x in chunk.split(",")]
        return True
    except ValueError:
        return False


def check(text_in: str, bones) -> list[dict]:
    """Ссылается ли файл CBPC на кости, которые есть в скелете, и разбираются ли фигуры.

    Смотрятся все три файла одним разбором: узлы в `[AffectedNodes]` и `[ColliderNodes]`,
    заголовки `[Кость]` со сферами и капсулами, строки `Кость=Группа` в `[ConfigMap]`
    (скобки `<` `>` пропускаются). Сфера - четыре числа на половину, капсула - два раза
    по четыре через `&`, половины через `|`. По находке на строку: род, имя, где, в чём дело.
    """
    known = set(bones)
    out: list[dict] = []
    section = None
    for no, raw in enumerate(text_in.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line or line in ("<", ">"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            if section.lower() not in _KNOWN_SECTIONS and section not in known:
                out.append({"kind": "bone", "name": section, "where": "строка %d, [%s]" % (no, section),
                            "problem": "такой кости нет в скелете"})
            continue
        low = (section or "").lower()
        if low in ("affectednodes", "collidernodes"):
            if line not in known:
                out.append({"kind": "bone", "name": line, "where": "строка %d, [%s]" % (no, section),
                            "problem": "такой кости нет в скелете"})
        elif low == "configmap":
            if "=" not in line:
                continue                    # строки групп CBPConfig в общем тексте
            bone = line.split("=", 1)[0].strip()
            if bone not in known:
                out.append({"kind": "bone", "name": bone, "where": "строка %d, [ConfigMap]" % no,
                            "problem": "такой кости нет в скелете"})
        elif section and low not in _KNOWN_SECTIONS:
            halves = [h.strip() for h in line.split("|")]
            for half in halves:
                pieces = [p.strip() for p in half.split("&")]
                if len(pieces) not in (1, 2) or not all(_numbers(p) and p.count(",") == 3 for p in pieces):
                    out.append({"kind": "shape", "name": section, "where": "строка %d" % no,
                                "problem": "не сфера (x,y,z,r) и не капсула (x,y,z,r & x,y,z,r): %r" % line})
                    break
    return out
