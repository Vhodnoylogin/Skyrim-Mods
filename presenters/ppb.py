"""Слой показа: капсулы строками настроек Precision Physic Bodies.

PPB перечитывает свой `PPB_tuning.txt` примерно раз в секунду прямо во время игры, поэтому
такими строками посадку примеряют живьём, не перезапуская ничего. Имена ручек он задаёт
по слоту - по одному на часть тела, - и складывает как `cap<Слот>[C<номер>]<поле>`.

Такой же клиент фасада, как таблицы и растеризатор: берёт `collider_local` - капсулы
в системе своей кости, как они лежат в файле, - и только раскладывает числа в строки.
Ядро о PPB не знает: какой мод какие строки ждёт - дело слоя показа.
"""
from __future__ import annotations

#: Слоты PPB по части тела. У него нет слота под хвост и пальцы: такие кости
#: пропускаются, а не получают выдуманное имя ручки.
SLOTS = {
    "com": "Com", "spine": "Spine0", "spine1": "Spine1", "spine2": "Spine2",
    "neck": "Neck", "head": "Head", "thigh": "Thigh", "calf": "Calf", "foot": "Foot",
    "upperarm": "Upper", "forearm": "Fore", "hand": "Hand",
}


def slot_key(bone: str) -> str:
    """Опознаёт часть тела по имени кости: «NPC L Thigh [LThg]» -> «thigh»."""
    core = bone.split("[")[0].strip().lower()
    for prefix in ("npc ", "l ", "r "):
        while core.startswith(prefix):
            core = core[len(prefix):]
    return core.replace(" ", "")


def lines(rows: list[dict]) -> list[str]:
    """Строки настроек по тем словарям, что отдаёт `MorphBench.collider_local`."""
    out = []
    for row in rows:
        slot = SLOTS.get(slot_key(row["bone"]))
        if slot is None:
            continue
        for cap in row["capsules"]:
            tag = "" if cap["index"] == 0 else "C%d" % cap["index"]
            out.append("cap%s%sEnable 1" % (slot, tag))
            for axis, name in enumerate("XYZ"):
                out.append("cap%s%sA%s %.4f" % (slot, tag, name, cap["p1"][axis]))
            for axis, name in enumerate("XYZ"):
                out.append("cap%s%sB%s %.4f" % (slot, tag, name, cap["p2"][axis]))
            out.append("cap%s%sR %.4f" % (slot, tag, cap["radius"]))
    return out
