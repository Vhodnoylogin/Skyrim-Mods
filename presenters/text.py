"""Слой показа: таблицы для консоли.

Такой же клиент фасада, как растеризатор, — берёт готовые словари и раскладывает их
в столбцы. Никаких вычислений здесь нет намеренно: если что-то приходится досчитывать
в слое показа, значит этого не хватает в ядре.
"""
from __future__ import annotations


def table(rows: list[dict], columns: list[tuple[str, str]], empty: str = "пусто") -> str:
    """rows - словари, columns - пары (ключ, заголовок)."""
    if not rows:
        return empty
    keys = [k for k, _ in columns]
    heads = [h for _, h in columns]
    cells = [[_fmt(r.get(k)) for k in keys] for r in rows]
    widths = [max(len(h), *(len(c[i]) for c in cells)) for i, h in enumerate(heads)]
    out = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(heads)),
           "  ".join("-" * w for w in widths)]
    for c in cells:
        out.append("  ".join(v.ljust(widths[i]) for i, v in enumerate(c)))
    return "\n".join(out)


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, float):
        return "%.2f" % value
    if isinstance(value, dict) and "min" in value and "max" in value:
        return " ".join("%g..%g" % (a, b) for a, b in zip(value["min"], value["max"]))
    if isinstance(value, dict):
        # Набор ползунков {имя: величина} - «A=1, B=0.5».
        return ", ".join("%s=%s" % (k, "%g" % v if isinstance(v, (int, float)) else _fmt(v))
                         for k, v in value.items())
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def summary(data: dict) -> str:
    lines = [
        "меш:      %s" % data["nif"],
        "морфы:    %s%s" % (data["tri"] or "нет",
                            "  (%s)" % data["triKind"] if data["triKind"] else ""),
        "частей:   %d,  вершин: %d,  костей: %d,  ползунков: %d"
        % (data["shapes"], data["vertices"], data["bones"], data["morphs"]),
        "охват:    %s" % _fmt(data["bounds"]),
    ]
    return "\n".join(lines)


def chains(rows: list[dict]) -> str:
    """Цепочки для качающейся физики: по строке на звено, итог по цепочке."""
    if not rows:
        return "цепочек нет: ни у одной кости нет номера в конце имени"
    out = []
    for r in rows:
        if r["fit"]:
            notes = []
            if r.get("anchors"):
                notes.append("опора %s" % ", ".join(_bone_label(b) for b in r["anchors"]))
            if r.get("gaps"):
                notes.append("шарнир без кожи %s" % ", ".join(_bone_label(b) for b in r["gaps"]))
            if r.get("tail"):
                notes.append("хвост без кожи %s" % ", ".join(_bone_label(b) for b in r["tail"]))
            verdict = "годится" + ((" (" + "; ".join(notes) + ")") if notes else "")
        else:
            verdict = "кожи нет ни на одном звене" if r["break"] else "одно звено"
        out.append("%-24s %-6s %5d вершин   %s" % (
            r["chain"], (r["engine"] or "-"), r["vertices"], verdict))
        for l in r["links"]:
            parts = ", ".join("%s %d" % (k, v) for k, v in l["shapes"].items()) or "кожи нет"
            out.append("    %-28s %5d   %s" % (_bone_label(l["bone"]), l["vertices"], parts))
    return "\n".join(out)


def assignments(rows: list[dict], engine: str) -> list[str]:
    """Кому отдана каждая цепочка - строками для шапки настроек одного движка.

    С кожей - по строке на цепочку: здесь, другому движку или никому; цепочки без кожи
    складываются в одну строку, им всё равно, кому они отданы: писать по ним нечего.
    """
    engine = str(engine).lower()
    out, bare = [], []
    for r in rows:
        if not r["vertices"]:
            bare.append(r["chain"])
            continue
        if r["engine"] == engine:
            if r["fit"]:
                state = "%s: здесь, %d вершин" % (engine, r["vertices"])
            elif r["break"]:
                state = "%s: кожи нет ни на одном звене, не пишется" % engine
            else:
                state = "%s: одно звено, не пишется" % engine
        elif r["engine"]:
            state = "%s: другому движку, здесь нет" % r["engine"]
        else:
            state = "никому не отдана"
        out.append("%s -> %s" % (r["chain"], state))
    if bare:
        out.append("без кожи, не пишутся: %s" % ", ".join(bare))
    return out

def strain_set(rows: list[dict]) -> str:
    """Растяжение при наборе ползунков: те же столбцы, что у strain, вместо морфа - набор."""
    return table(rows, [("shape", "часть"), ("sliders", "набор"), ("maxStrain", "макс"),
                        ("p99Strain", "99%"), ("overThreshold", "рёбер сверх"),
                        ("worstBounds", "где именно X / Y / Z")],
                 "набор не двигает ни одной части меша")


def strain_pairs(rows: list[dict]) -> str:
    """Перебор пар: вместе, каждый поодиночке, прибавка пары над худшим из них."""
    return table(rows, [("a", "ползунок"), ("b", "и ползунок"), ("maxStrain", "вместе"),
                        ("maxA", "первый один"), ("maxB", "второй один"), ("gain", "прибавка"),
                        ("overThreshold", "рёбер сверх"), ("shape", "где")],
                 "пар нет: непустых ползунков меньше двух")


def budget(rows: list[dict]) -> str:
    """Бюджет амплитуд: предел каждого ползунка; без предела - в пределах не рвёт."""
    if not rows:
        return "непустых ползунков нет"
    shown = [dict(r, limit="в пределах не рвёт" if r["limit"] is None else "%.3f" % r["limit"])
             for r in rows]
    return table(shown, [("morph", "ползунок"), ("limit", "предел"),
                         ("maxAt", "макс на %g" % rows[0]["high"]), ("shape", "где рвётся")])


def bounds(rows: list[dict]) -> str:
    """Шары охвата: по строке на часть - в файле, куда тянется, перебор, нужный."""
    if not rows:
        return "частей нет"
    out = ["%-16s %8s %8s %8s   %-22s %8s" % ("часть", "в файле", "тянется", "перебор", "чем", "нужен")]
    for r in rows:
        if r["file"] is None:
            out.append("%-16s %8s %8s %8s   %-22s %8.1f" % (r["shape"], "-", "-", "-", "-", r["needed"]["radius"]))
            continue
        out.append("%-16s %8.1f %8.1f %+7.0f%%   %-22s %8.1f%s" % (
            r["shape"], r["file"]["radius"], r["reach"], 100.0 * r["excess"],
            r["state"][:22], r["needed"]["radius"], "" if r["ok"] else "  <- расширить"))
    return "\n".join(out)


def _bone_label(name: str) -> str:
    """Короткое имя кости: «NPC L Thigh [LThg]» -> «L Thigh»."""
    core = name.split("[")[0].strip()
    return core[4:] if core.startswith("NPC ") else core


def colliders(rows: list[dict]) -> str:
    """Капсулы столкновений: по строке на тело, и посадка рядом, если её посчитали."""
    if not rows:
        return "у этого скелета нет тел столкновений"
    out = []
    for row in rows:
        caps = row["capsules"]
        ph = row.get("physics") or {}
        head = "%-18s %d %s   %s %s" % (
            _bone_label(row["bone"]), len(caps),
            "капсула" if len(caps) == 1 else "капсул",
            ph.get("layer", "?"), ph.get("response", "?"))
        fit = row.get("clearance")
        if fit:
            head += "   снаружи %.0f%% кожи, дальше всего %.1f" % (
                100.0 * fit["outside"], fit["worst"])
        out.append(head)
        for cap in caps:
            out.append("    #%d  центр %s  длина %.1f  радиус %.1f"
                       % (cap["index"],
                          " ".join("%7.1f" % c for c in
                                   [(a + b) / 2.0 for a, b in zip(cap["p1"], cap["p2"])]),
                          cap["length"], cap["radius"]))
    return "\n".join(out)


def fitted(rows: list[dict]) -> str:
    """Что дала посадка: было и стало, по строке на кость."""
    if not rows:
        return "нечего сажать: ни одна кость не дала точек кожи"
    lines = []
    for row in rows:
        if not row.get("fitted"):
            lines.append("%-18s точек %-6d не села" % (_bone_label(row["bone"]), row["points"]))
            continue
        was, now = row["was"], row["now"]
        count = int(row.get("count", 1))
        tail = ""
        if count > 1:
            caps = row.get("capsules") or []
            tail = "   связка из %d: радиусы %s" % (
                count, " ".join("%.1f" % c["radius"] for c in caps))
        lines.append("%-18s точек %-6d  длина %5.1f -> %5.1f   радиус %5.1f -> %5.1f%s"
                     % (_bone_label(row["bone"]), row["points"],
                        was["length"], now["length"], was["radius"], now["radius"], tail))
    return "\n".join(lines)
