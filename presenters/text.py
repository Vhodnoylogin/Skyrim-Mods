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
