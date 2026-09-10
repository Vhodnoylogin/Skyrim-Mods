"""Слой показа: настройки Faster HDT-SMP для цепочек костей - XML `hdtSkinnedMeshConfigs`.

SMP качает цепочку как связку тел: `<bone name>` с массой, инерцией и затуханием
на каждое звено и `<generic-constraint bodyA= bodyB=>` - шарнир от звена к родителю
с пределами и жёсткостью. Кость, объявленная без тела (`<bone name="X"/>`), неподвижна
и ведётся анимацией - это опора, от которой качается всё остальное; у 3BBB это
`Breast00`, у пушистых хвостов - первое звено. Сколько первых звеньев держать
неподвижными - `smpStaticLinks`; при нуле опорой служит родитель цепочки в скелете.

Столкновения у SMP идут ОТ МЕША, а не от капсул на костях: `<per-vertex-shape>`
и `<per-triangle-shape>` называют ЧАСТЬ МЕША, и форму он строит по её вершинам сам.
Поэтому севшие капсулы сюда не переносятся - переносятся только имена частей, на которых
лежит кожа цепочки, с зазором и глубиной из настроек. Файл подключается к части через
`defaultBBPs.xml` (`<map shape="часть" file="..."/>`) либо строкой `HDT Skinned Mesh
Physics Object` внутри NIF - это делается руками, верстак чужих файлов не правит.

Такой же клиент фасада, как `ppb` и `cbpc`: берёт `chain_capsules(engine="smp")`,
`chains()` для шапки и числа `smp*` из настроек. Цепочки, отданные другому движку,
сюда не попадают: SMP и CBPC - разные движки, одну кость обоим отдавать нельзя.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from . import text as _text

_TAB = "\t"


def selected(rows: list[dict]) -> list[dict]:
    """Какие из отданных SMP цепочек попадают в вывод: годные - с кожей и без обрыва."""
    return [r for r in rows if r["fit"]]


def _attr(value) -> str:
    return escape(str(value), {'"': "&quot;"})


def _xyz(tag: str, values, depth: int = 2) -> str:
    x, y, z = (float(v) for v in values)
    return '%s<%s x="%g" y="%g" z="%g"/>' % (_TAB * depth, tag, x, y, z)


def _static_bone(name: str) -> list[str]:
    return ['%s<bone name="%s"/>' % (_TAB, _attr(name))]


def bone_lines(name: str, mass: float, cfg) -> list[str]:
    """Тело звена: масса своя, остальное - из настроек."""
    d = _TAB * 2
    inertia = float(cfg["smpInertia"])
    return [
        '%s<bone name="%s">' % (_TAB, _attr(name)),
        "%s<mass>%g</mass>" % (d, mass),
        _xyz("inertia", (inertia, inertia, inertia)),
        "%s<centerOfMassTransform>" % d,
        '%s<basis x="0" y="0" z="0" w="1"/>' % (_TAB * 3),
        '%s<origin x="0" y="0" z="0"/>' % (_TAB * 3),
        "%s</centerOfMassTransform>" % d,
        "%s<linearDamping>%g</linearDamping>" % (d, float(cfg["smpLinearDamping"])),
        "%s<angularDamping>%g</angularDamping>" % (d, float(cfg["smpAngularDamping"])),
        "%s<gravity-factor>%g</gravity-factor>" % (d, float(cfg["smpGravityFactor"])),
        "%s<friction>%g</friction>" % (d, float(cfg["smpFriction"])),
        "%s<rollingFriction>%g</rollingFriction>" % (d, float(cfg["smpRollingFriction"])),
        "%s<restitution>%g</restitution>" % (d, float(cfg["smpRestitution"])),
        "%s<margin-multiplier>%g</margin-multiplier>" % (d, float(cfg["smpMarginMultiplier"])),
        "%s</bone>" % _TAB,
    ]


def constraint_lines(child: str, parent: str, cfg) -> list[str]:
    """Шарнир звена к родителю: пределы, жёсткости, затухания - из настроек."""
    d = _TAB * 2
    return [
        '%s<generic-constraint bodyA="%s" bodyB="%s">' % (_TAB, _attr(child), _attr(parent)),
        "%s<frameInB>" % d,
        '%s<basis x="0" y="0" z="0" w="1"/>' % (_TAB * 3),
        '%s<origin x="0" y="0" z="0"/>' % (_TAB * 3),
        "%s</frameInB>" % d,
        "%s<useLinearReferenceFrameA>false</useLinearReferenceFrameA>" % d,
        _xyz("linearLowerLimit", cfg["smpLinearLowerLimit"]),
        _xyz("linearUpperLimit", cfg["smpLinearUpperLimit"]),
        _xyz("angularLowerLimit", cfg["smpAngularLowerLimit"]),
        _xyz("angularUpperLimit", cfg["smpAngularUpperLimit"]),
        _xyz("linearStiffness", cfg["smpLinearStiffness"]),
        _xyz("angularStiffness", cfg["smpAngularStiffness"]),
        _xyz("linearDamping", cfg["smpConstraintLinearDamping"]),
        _xyz("angularDamping", cfg["smpConstraintAngularDamping"]),
        _xyz("linearEquilibrium", (0.0, 0.0, 0.0)),
        _xyz("angularEquilibrium", cfg["smpAngularEquilibrium"]),
        "%s</generic-constraint>" % _TAB,
    ]


def shape_lines(part: str, cfg) -> list[str]:
    """Форма столкновения по вершинам части меша; с собой не сталкивается."""
    d = _TAB * 2
    return [
        '%s<per-vertex-shape name="%s">' % (_TAB, _attr(part)),
        "%s<margin>%g</margin>" % (d, float(cfg["smpMargin"])),
        "%s<penetration>%g</penetration>" % (d, float(cfg["smpPenetration"])),
        "%s<tag>%s</tag>" % (d, escape(part)),
        "%s<no-collide-with-tag>%s</no-collide-with-tag>" % (d, escape(part)),
        "%s</per-vertex-shape>" % _TAB,
    ]


def chain_lines(row: dict, cfg) -> list[str]:
    """Одна цепочка: опора, звенья с телами, шарниры от звена к родителю."""
    links = [l["bone"] for l in row["links"]]
    static = max(0, int(cfg["smpStaticLinks"]))
    anchor = row.get("parent")
    if static == 0 and not anchor:
        static = 1                       # дерева костей нет - опора первое звено
    out = ["%s<!-- %s: опора %s, звеньев %d -->" % (
        _TAB, row["chain"], anchor if (static == 0) else ", ".join(links[:static]), len(links))]
    if static == 0:
        out += _static_bone(anchor)
    mass = float(cfg["smpMass"])
    taper = float(cfg["smpMassTaper"])
    for i, name in enumerate(links):
        if i < static:
            out += _static_bone(name)
            continue
        out += bone_lines(name, mass, cfg)
        mass *= taper
    for i, name in enumerate(links):
        if i < static:
            continue
        out += constraint_lines(name, links[i - 1] if i > 0 else anchor, cfg)
    return out


def text(rows: list[dict], chains: list[dict], cfg, title: str | None = None) -> str:
    """XML настроек SMP по цепочкам, отданным ему.

    `rows` - `MorphBench.chain_capsules("smp")` (капсулы в нём не используются: SMP
    их не читает; нужны опора и звенья), `chains` - `MorphBench.chains()` целиком ради
    шапки, `cfg` - настройки с числами `smp*`.
    """
    head = ['<?xml version="1.0" encoding="UTF-8"?>', "<!--",
            "morphbench: настройки Faster HDT-SMP%s" % ((" для " + title) if title else ""),
            "цепочки:"]
    head += ["  " + line.replace("--", "- -") for line in _text.assignments(chains, "smp")]
    head += ["Столкновения SMP считает по вершинам частей меша, капсул по костям он не читает:",
             "ниже только имена частей, на которых лежит кожа цепочек. Подключить файл к части:",
             'defaultBBPs.xml, <map shape="часть" file="SKSE\\Plugins\\hdtSkinnedMeshConfigs\\этот файл"/>.',
             "-->"]
    wanted = selected(rows)
    if not wanted:
        return "\n".join(head + ["<system>",
                                 "%s<!-- SMP не отдано ни одной годной цепочки: писать нечего -->" % _TAB,
                                 "</system>"]) + "\n"
    out = head + ["<system>"]
    for r in wanted:
        out += chain_lines(r, cfg)
        out.append("")
    parts: list[str] = []
    for r in wanted:
        for l in r["links"]:
            for part in l["shapes"]:
                if part not in parts:
                    parts.append(part)
    out.append("%s<!-- части меша с кожей цепочек: форма по их вершинам -->" % _TAB)
    for part in parts:
        out += shape_lines(part, cfg)
    out.append("</system>")
    return "\n".join(out) + "\n"

# ---- проверка готового файла ------------------------------------------------------------------
def check(xml_text: str, bones, shapes=None) -> list[dict]:
    """Ссылается ли XML SMP на то, что есть: кости - в скелете, части - в меше.

    SMP молча пропускает файл с ошибкой: ни строки в журнале, просто ничего не качается.
    Здесь ловится то, что окупается первой же опечаткой: неизвестная кость в `<bone>`,
    шарнир на необъявленную кость, часть меша, которой нет, `<collision>` между
    неназванными формами, и битый XML. По находке на строку: род, имя, где, в чём дело.
    """
    import xml.etree.ElementTree as ET
    known_bones = set(bones)
    known_shapes = None if shapes is None else set(shapes)
    out: list[dict] = []

    def hit(kind, name, where, problem):
        out.append({"kind": kind, "name": name, "where": where, "problem": problem})

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return [{"kind": "xml", "name": "", "where": "", "problem": "XML не разбирается: %s" % e}]
    declared = set()
    for el in root.iter("bone"):
        name = el.get("name") or ""
        declared.add(name)
        if name not in known_bones:
            hit("bone", name, "<bone>", "такой кости нет в скелете")
    declared_shapes = set()
    for tag in ("per-vertex-shape", "per-triangle-shape"):
        for el in root.iter(tag):
            name = el.get("name") or ""
            declared_shapes.add(name)
            if known_shapes is not None and name not in known_shapes:
                hit("shape", name, "<%s>" % tag, "такой части нет в меше")
    for el in root.iter("generic-constraint"):
        for attr in ("bodyA", "bodyB"):
            name = el.get(attr) or ""
            if name not in declared:
                hit("constraint", name, "<generic-constraint %s>" % attr,
                    "шарнир на кость, не объявленную <bone>" if name in known_bones
                    else "шарнир на кость, которой нет ни в файле, ни в скелете")
    names = declared | declared_shapes
    for el in root.iter("collision"):
        for attr in ("a", "b"):
            name = el.get(attr) or ""
            if name and name not in names:
                hit("collision", name, "<collision %s>" % attr, "столкновение с неназванной формой")
    return out
