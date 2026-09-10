"""Собирает мод целиком по описанию пайплайна и пишет манифест сборки.

Зачем. Рецепты в репозитории лежали, а как их запустить — нигде: порядок сборщиков
и их доводы держались памятью. Пока это так, «мод пересобирается из исходников» —
обещание, а не факт. Здесь порядок стал данными (`recipes/build.json`), а сборка —
одной командой.

Три вещи, которых без этого не было.

**Вход закреплён.** Мод стоит на чужих ассетах. У каждого источника в описании записана
контрольная сумма; расходится — сборка говорит об этом вслух и, если не разрешили иначе,
останавливается. Иначе донор обновится, пересборка даст другой файл, и никто не заметит.

**Сверка выхода.** Собирается в отдельную папку и сравнивается с тем, что лежит в моде.
Совпало — пайплайн описан верно. Не совпало — мы это знаем, а не думаем, что знаем.

**Манифест.** Рядом с модом остаётся `claw-build.json`: из каких исходников, каким
коммитом рецептов, каким инструментом и когда собрано. Без него через полгода «версия
0.5.0.0» значит только число в meta.ini, и связать выпущенный архив с состоянием
репозитория будет нечем.

Запуск:

    python build-all.py [--out <папка>] [--only <имя шага>] [--dry]
                        [--install] [--allow-source-drift]

    --out       куда собирать; по умолчанию отдельная папка в work\\, НЕ в мод
    --install   положить собранное в мод (иначе мод не трогается)
    --dry       только показать, что было бы сделано
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT.parent.parent / "tools"))
from paths import P                                        # noqa: E402


def crc32(path: Path) -> str:
    return "%08X" % (zlib.crc32(Path(path).read_bytes()) & 0xFFFFFFFF)


def git(*args: str) -> str:
    """Ответ git из папки модуля; пусто, если git недоступен."""
    try:
        done = subprocess.run(["git", "-C", str(ROOT), *args],
                              capture_output=True, text=True, timeout=20)
        return done.stdout.strip() if done.returncode == 0 else ""
    except Exception:                                      # noqa: BLE001
        return ""


def _nifly():
    """Обвязка PyNifly. Своего читателя NIF заводить незачем, штатный есть."""
    root = Path(P.pynifly)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from pyn import pynifly                                # noqa: WPS433
    if getattr(pynifly.NifFile, "nifly", None) is None:
        pynifly.NifFile.Load(str(root / "NiflyDLL.dll"))
    return pynifly


def _diff_nif(a: Path, b: Path) -> dict:
    """Совпадают ли два меша по существу: части, вершины, координаты."""
    import numpy as np                                     # noqa: WPS433
    pynifly = _nifly()
    na, nb = pynifly.NifFile(str(a)), pynifly.NifFile(str(b))
    sa = {s.name: s for s in na.shapes}
    sb = {s.name: s for s in nb.shapes}
    if not sa and not sb:
        # Скелет: геометрии в нём нет вовсе, и сравнивать по частям бессмысленно -
        # такая сверка отвечала бы «совпал» на что угодно. Смысл скелета для нас
        # в капсулах столкновений, их и сравниваем.
        return _diff_collision(na, nb)
    if set(sa) != set(sb):
        return {"state": "РАЗОШЁЛСЯ", "why": "разный состав частей",
                "only": sorted(set(sa) ^ set(sb))}
    worst = 0.0
    for name in sa:
        va = np.asarray(sa[name].verts, np.float32).reshape(-1, 3)
        vb = np.asarray(sb[name].verts, np.float32).reshape(-1, 3)
        if va.shape != vb.shape:
            return {"state": "РАЗОШЁЛСЯ", "why": "у части %s разное число вершин" % name}
        worst = max(worst, float(np.abs(va - vb).max()))
    return {"state": "совпал" if worst < 1e-4 else "РАЗОШЁЛСЯ",
            "shapes": len(sa), "maxDelta": round(worst, 6)}


def _diff_collision(na, nb) -> dict:
    """Совпадают ли скелеты по капсулам столкновений: кости, число форм, размеры."""
    import numpy as np                                     # noqa: WPS433
    H = 69.99125

    def caps(nif):
        out = {}
        for name, node in nif.nodes.items():
            col = getattr(node, "collision_object", None)
            body = getattr(col, "body", None) if col is not None else None
            shape = getattr(body, "shape", None) if body is not None else None
            got = []
            stack = [shape] if shape is not None else []
            while stack:
                sh = stack.pop()
                kind = type(sh).__name__
                if kind == "bhkCapsuleShape":
                    pr = sh.properties
                    got.append(np.asarray(list(pr.point1) + list(pr.point2)
                                          + [pr.radius1], np.float32) * H)
                elif kind == "bhkListShape":
                    stack.extend(sh.children)
            if got:
                out[name] = got
        return out

    ca, cb = caps(na), caps(nb)
    if set(ca) != set(cb):
        return {"state": "РАЗОШЁЛСЯ", "why": "разный набор костей с телами",
                "only": sorted(set(ca) ^ set(cb))}
    worst, total = 0.0, 0
    for name, rows in ca.items():
        if len(rows) != len(cb[name]):
            return {"state": "РАЗОШЁЛСЯ",
                    "why": "у кости %s разное число капсул" % name.split("[")[0].strip()}
        total += len(rows)
        for x, y in zip(rows, cb[name]):
            worst = max(worst, float(np.abs(x - y).max()))
    return {"state": "совпал" if worst < 1e-3 else "РАЗОШЁЛСЯ",
            "shapes": "%d тел / %d капсул" % (len(ca), total),
            "maxDelta": round(worst, 4)}


def _diff_tri(a: Path, b: Path) -> dict:
    """Совпадают ли два файла морфов: имена ползунков и их сдвиги."""
    import importlib.util                                  # noqa: WPS433
    import numpy as np                                     # noqa: WPS433
    root = Path(P.pynifly)
    spec = importlib.util.spec_from_file_location("_tripfile", root / "tri" / "tripfile.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    def read(path):
        with open(path, "rb") as fh:
            return mod.TripFile.from_file(fh).shapes

    fa, fb = read(a), read(b)
    if set(fa) != set(fb):
        return {"state": "РАЗОШЁЛСЯ", "why": "разный состав частей в файле морфов"}
    names_a = {m for sh in fa.values() for m in sh}
    names_b = {m for sh in fb.values() for m in sh}
    if names_a != names_b:
        return {"state": "РАЗОШЁЛСЯ", "why": "разный набор ползунков",
                "only": sorted(names_a ^ names_b)}
    worst = 0.0
    for shape, morphs in fa.items():
        for name, offs in morphs.items():
            other = dict(fb[shape][name])
            for idx, d in offs:
                o = other.get(idx)
                if o is None:
                    return {"state": "РАЗОШЁЛСЯ",
                            "why": "у %s/%s разный набор вершин" % (shape, name)}
                worst = max(worst, float(np.abs(np.asarray(d) - np.asarray(o)).max()))
    return {"state": "совпал" if worst < 1e-4 else "РАЗОШЁЛСЯ",
            "morphs": len(names_a), "maxDelta": round(worst, 6)}


class Pipeline:
    """Описание сборки: источники, шаги и ожидаемые суммы."""

    def __init__(self, spec: dict, out: Path):
        self.spec = spec
        self.out = out
        self.mods = Path(P.mods)

    # ---- пути ----------------------------------------------------------------------
    def built(self, name: str) -> Path:
        """Файл в папке сборки — внутри дерева с папкой `meshes`.

        Плоской папкой обойтись нельзя: PyNifly пишет метку BODYTRI (ссылку тела на свой
        файл морфов) обрезкой пути экспорта по слову `meshes`. Без него в мод уезжает
        абсолютный путь со сборочной машины, и у игрока морфы не находятся.
        """
        tree = self.spec.get("outputUnder", "")
        variant, _, leaf = name.rpartition("/")
        root = self.out / variant if variant else self.out
        return (root / tree / leaf) if tree else (root / leaf)

    def source(self, key: str) -> Path:
        node = self.spec["sources"][key]
        return self.mods / node["mod"] / node["path"]

    def resolve(self, token: str) -> str:
        """`@elegantMale` - источник, `@out:имя` - файл в папке сборки,
        `@recipe:имя` - рецепт. Всё остальное идёт как есть."""
        if not token.startswith("@"):
            return token
        body = token[1:]
        if body.startswith("out:"):
            return str(self.built(body[4:]))
        if body.startswith("recipe:"):
            return str(ROOT / "recipes" / body[7:])
        return str(self.source(body))

    # ---- проверки ------------------------------------------------------------------
    def check_sources(self, allow_drift: bool) -> list[dict]:
        """Сходятся ли контрольные суммы входа с закреплёнными."""
        rows = []
        for key, node in self.spec["sources"].items():
            if key.startswith("_"):
                continue
            path = self.mods / node["mod"] / node["path"]
            if not path.is_file():
                rows.append({"source": key, "state": "НЕТ ФАЙЛА", "path": str(path)})
                continue
            got = crc32(path)
            rows.append({"source": key, "state": "совпал" if got == node["crc"] else "РАЗОШЁЛСЯ",
                         "expected": node["crc"], "actual": got})
        broken = [r for r in rows if r["state"] != "совпал"]
        if broken and not allow_drift:
            for r in broken:
                print("  вход %-14s %s %s" % (r["source"], r["state"],
                                              r.get("actual", r.get("path", ""))))
            raise SystemExit(
                "вход разошёлся с закреплённым. Донор обновился или подменён другим модом.\n"
                "Осознанно — перезапустите с --allow-source-drift и обновите crc в build.json.")
        return rows

    # ---- выполнение ----------------------------------------------------------------
    def run_step(self, step: dict, dry: bool) -> None:
        runner = step.get("runner", "python")
        if runner in ("copy", "move"):
            src, dst = Path(self.resolve(step["from"])), Path(self.resolve(step["to"]))
            print("   %s %s -> %s" % ("копия" if runner == "copy" else "переименование",
                                      src.name, dst.name))
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                if runner == "copy":
                    shutil.copyfile(src, dst)
                else:
                    dst.unlink(missing_ok=True)
                    shutil.move(str(src), str(dst))
            return
        args = [self.resolve(a) for a in step["args"]]
        # Папки под выход заводим сами: Blender при экспорте несуществующий каталог
        # не создаёт, а падает уже следующим шагом, на переименовании, и причина
        # выглядит совсем не там, где она есть.
        for tok, val in zip(step["args"], args):
            if isinstance(tok, str) and tok.startswith("@out:"):
                Path(val).parent.mkdir(parents=True, exist_ok=True)
        if runner == "blender":
            blender = str(P.blender) if getattr(P, "blender", "") else ""
            if not blender or not Path(blender).is_file():
                raise SystemExit("не найден Blender: заполните ключ blender в tools\\paths.json")
            cmd = [blender, "--background", "--python", str(HERE / step["script"]), "--", *args]
        else:
            cmd = [sys.executable, str(HERE / step["script"]), *args]
        print("   " + " ".join(('"%s"' % c) if " " in c else c for c in cmd[:4]) + " ...")
        if dry:
            return
        done = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        tail = (done.stdout or "").rstrip().splitlines()[-12:]
        for line in tail:
            print("      " + line)
        if done.returncode != 0:
            print((done.stderr or "")[-1500:])
            raise SystemExit("шаг отказал: %s" % step["name"])

    def verify(self) -> list[dict]:
        """Сверка собранного с тем, что лежит в модах — ПО СМЫСЛУ, а не по байтам.

        Проверено 10.09: пересборка даёт файл с другой контрольной суммой, но геометрия
        совпадает до последней вершины. Экспорт NIF не побайтово повторяем, поэтому вход
        закрепляется суммой, а выход сверяется содержимым.
        """
        rows = []
        for key, mod in self.spec.get("mods", {}).items():
            target = self.mods / mod["name"] / mod.get("under", "")
            for name, src in mod["files"].items():
                built, shipped = self.built(src), target / name
                row = {"mod": key, "file": name}
                if not built.is_file():
                    rows.append({**row, "state": "НЕ СОБРАН"})
                    continue
                if not shipped.is_file():
                    rows.append({**row, "state": "мода ещё нет", "new": True})
                    continue
                try:
                    rows.append({**row, **(_diff_tri(shipped, built) if name.endswith(".tri")
                                           else _diff_nif(shipped, built))})
                except Exception as e:                      # noqa: BLE001
                    rows.append({**row, "state": "сверить нечем: %s" % e})
        # Наборы обязаны стоять на ОДНОЙ геометрии: пропуск ползунков её не трогает.
        for a, b in self.spec.get("sameGeometry", []):
            pa, pb = self.built(a), self.built(b)
            row = {"mod": "наборы", "file": "%s = %s" % (a, b)}
            if not (pa.is_file() and pb.is_file()):
                rows.append({**row, "state": "НЕ СОБРАН"})
                continue
            try:
                rows.append({**row, **_diff_nif(pa, pb)})
            except Exception as e:                          # noqa: BLE001
                rows.append({**row, "state": "сверить нечем: %s" % e})
        return rows

    # ---- манифест ------------------------------------------------------------------
    def manifest(self, sources: list[dict], verified: list[dict]) -> dict:
        return {
            "_": ("Чем собран этот мод. По манифесту любой выпущенный архив возводится "
                  "к точному состоянию исходников."),
            "mod": self.spec["mod"],
            "version": self.spec["version"],
            "builtAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "recipes": {"commit": git("rev-parse", "HEAD"),
                        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                        "dirty": bool(git("status", "--porcelain"))},
            "sources": sources,
            "outputs": verified,
        }


def main(argv: list[str]) -> int:
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv \
        else ROOT / "work" / "build" / "claw"
    dry = "--dry" in argv
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    spec = json.loads((ROOT / "recipes" / "build.json").read_text(encoding="utf-8-sig"))
    pipe = Pipeline(spec, out)

    print("мод    : %s %s" % (spec["mod"], spec["version"]))
    print("сборка : %s" % out)
    out.mkdir(parents=True, exist_ok=True)

    print("\nвход:")
    sources = pipe.check_sources("--allow-source-drift" in argv)
    for r in sources:
        print("   %-14s %s" % (r["source"], r["state"]))

    print("\nшаги:")
    for step in spec["steps"]:
        if only and only.lower() not in step["name"].lower():
            continue
        print(" - %s" % step["name"])
        pipe.run_step(step, dry)

    if dry:
        return 0

    print("\nсверка с тем, что лежит в моде:")
    verified = pipe.verify()
    for r in verified:
        extra = ""
        if r.get("why"):
            extra = "  (%s)" % r["why"]
        elif r.get("maxDelta") is not None:
            extra = "  (частей %s, наибольшее расхождение %s)" % (
                r.get("shapes", r.get("morphs")), r["maxDelta"])
        print("   %-8s %-34s %s%s" % (r.get("mod", ""), r["file"], r["state"], extra))

    man = pipe.manifest(sources, verified)
    (out / "claw-build.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nманифест: %s" % (out / "claw-build.json"))

    if "--install" in argv:
        for mod in spec.get("mods", {}).values():
            target = Path(P.mods) / mod["name"] / mod.get("under", "")
            target.mkdir(parents=True, exist_ok=True)
            for name, src in mod["files"].items():
                built = pipe.built(src)
                if built.is_file():
                    shutil.copyfile(built, target / name)
            shutil.copyfile(out / "claw-build.json",
                            Path(P.mods) / mod["name"] / "claw-build.json")
            print("положено в мод: %s (%d файлов)" % (mod["name"], len(mod["files"])))
    return 0


if __name__ == "__main__":
    # Консоль Windows по умолчанию cp1251, и print() с русским текстом на ней падает.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
