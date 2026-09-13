"""Собирает скелет мода: копию донорского с посаженными по телу капсулами столкновений.

Зачем отдельный сборщик. Мод возит `skeleton.nif` — побайтовую копию донорского файла,
в которой изменены только числа капсул: тех невидимых тел, по которым игра считает падение
трупа и попадание стрелы. Ванильные стояли не на местах — капсула головы была смещена
на 11 единиц вбок и не накрывала морду, на шее висел шар на кости, у которой у вервольфа
нет ни одной вершины кожи, стопы не доставали до пальцев.

Правило модуля: **меш — не исходник, а продукт**, и в репозитории лежит то, из чего он
собирается. Скелет ему подчиняется так же. Без этого сценария файл в моде был бы
единственным экземпляром, который заново не получить, — а это ровно то, чего мы избегаем.

Считает не сам: посадку выполняет верстак `dev\\morphbench` через свою командную строку.
Зовём его именно командой, а не как библиотеку: командная строка — объявленный договор
модуля, она меняется медленно, а внутренности верстака живут своей жизнью.

Запуск:

    python build-skeleton.py [--recipe skeleton.json] [--out <путь.nif>] [--dry]

Все пути и числа — в рецепте `recipes/skeleton.json`; здесь только порядок действий.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def load(recipe: Path) -> dict:
    if not recipe.is_file():
        raise SystemExit("нет рецепта: %s" % recipe)
    return json.loads(recipe.read_text(encoding="utf-8-sig"))


def resolve(spec: dict, key: str) -> Path:
    """Путь из рецепта. Мод указывается именем, а не абсолютным путём: у другой машины
    инстанс MO2 лежит иначе, и корень выводится модулем tools\\paths."""
    sys.path.insert(0, str(HERE))
    from locate import project_tools                # noqa: WPS433
    sys.path.insert(0, str(project_tools(HERE)))
    from paths import P                                  # noqa: WPS433
    node = spec[key]
    return Path(P.mods) / node["mod"] / node["path"]


def _supports(bench: Path, flag: str) -> bool:
    """Понимает ли верстак этот ключ. Спрашиваем его самого, а не гадаем по версии."""
    try:
        done = subprocess.run([sys.executable, str(bench), "fit", "--help"],
                              capture_output=True, text=True, timeout=60,
                              encoding="utf-8", errors="replace")
        return flag in (done.stdout or "")
    except Exception:                                      # noqa: BLE001
        return False


def run(cmd: list[str], dry: bool) -> None:
    print("  " + " ".join('"%s"' % c if " " in c else c for c in cmd))
    if dry:
        return
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if done.stdout:
        print("\n".join("    " + s for s in done.stdout.rstrip().splitlines()[-30:]))
    if done.returncode != 0:
        raise SystemExit("верстак отказал:\n" + (done.stderr or "")[-2000:])


def main(argv: list[str]) -> int:
    recipe = Path(argv[argv.index("--recipe") + 1]) if "--recipe" in argv \
        else ROOT / "recipes" / "skeleton.json"
    dry = "--dry" in argv
    spec = load(recipe)

    donor = resolve(spec, "donor")
    body = resolve(spec, "body")
    out = Path(argv[argv.index("--out") + 1]) if "--out" in argv else resolve(spec, "output")
    sys.path.insert(0, str(HERE))
    from locate import morphbench                   # noqa: WPS433
    bench = morphbench(HERE)

    print("донор : %s" % donor)
    print("тело  : %s" % body)
    print("выход : %s" % out)
    if not donor.is_file():
        raise SystemExit("донорский скелет не найден — установлен ли мод %r?"
                         % spec["donor"]["mod"])

    # Посадка: капсулы садятся по ВИДИМОМУ силуэту, вместе с шерстью. По одной коже
    # туловище вырождается в шары - на спине и брюхе кожи мало, она вся под оболочками.
    tmp = out.with_suffix(".fit.nif")
    print("\nпосадка капсул по телу")
    cmd = [sys.executable, str(bench), "fit", str(body), "--skeleton", str(donor),
           "--percentile", str(spec.get("percentile", 90.0)), "--save", str(tmp)]
    empty = spec.get("collapseEmpty")
    if empty and _supports(bench, "--collapse-empty"):
        cmd += ["--collapse-empty", str(empty)]
    elif empty:
        # Не роняем сборку из-за необязательного уточнения: тело без кожи останется
        # ванильным, и это видно в кадре как лишний шар за головой. Ключ заказан
        # разделом 5а наряда history/REPORT-76-morphbench.
        print("  ВНИМАНИЕ: верстак не знает --collapse-empty; шея останется ванильной")
    run(cmd, dry)

    # Шея - особый случай, и он выражен ключом САМОЙ посадки, а не отдельной командой:
    # кожи у неё нет НИ ОДНОЙ вершины, тело нужно только как сустав цепи между грудью
    # и головой. Оставить её ванильное значение нельзя - там шар радиусом 8.4 позади
    # черепа. Правило общее: тело, которому не досталось кожи, форму хоронит внутри.
    #
    # ВНИМАНИЕ: ключ `--collapse-empty` верстак пока не понимает - он заказан нарядом
    # history\REPORT-76-morphbench. Пока его нет, шея останется ванильной, и это
    # видно в кадре как лишний шар за головой.

    if not dry:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp), str(out))
        same = out.stat().st_size == donor.stat().st_size
        print("\nготово: %s (%d байт, размер как у донора: %s)"
              % (out.name, out.stat().st_size, "да" if same else "НЕТ - структура изменилась"))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
