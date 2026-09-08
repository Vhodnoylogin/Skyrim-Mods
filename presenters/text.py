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
        lines.append("%-18s точек %-6d  длина %5.1f -> %5.1f   радиус %5.1f -> %5.1f"
                     % (_bone_label(row["bone"]), row["points"],
                        was["length"], now["length"], was["radius"], now["radius"]))
    return "\n".join(lines)
