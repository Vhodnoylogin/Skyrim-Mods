r"""Расширяет шары охвата тела так, чтобы они накрывали его на ЛЮБЫХ ползунках.

Зачем. У каждой части меша записан шар: центр и радиус. Игра по нему решает, попадает
ли часть в кадр, и не рисует то, что снаружи. Считается он по позе покоя - а морфы
двигают вершины за его пределы, и деталь исчезает по углу обзора. На нашем теле
за свой шар выходили пятнадцать частей из шестнадцати, `fur_tailtip` - на 192%.

Почему отдельным шагом, а не внутри сборщика тела. Правило журнала: всякая операция
над продуктом обязана быть шагом. Шары правятся ПОСЛЕ того, как тело собрано и файл
морфов написан, - иначе считать нечего.

Считает не сам: перебор ползунков выполняет верстак `dev\morphbench` своей командой
`bounds --write`. Зовём командой, а не как библиотеку, - командная строка верстака -
объявленный договор, а внутренности живут своей жизнью.

    python fix-bounds.py <меш.nif> [--tri <файл.tri>] [--margin 0.05] [--dry]

`--tri` указывать ВАЖНО там, где в игре победит другой файл морфов: базовый мод возит
свои 24 ползунка, но поверх него ложится надстройка с 29, и шар обязан накрывать
широкий случай. Без ключа верстак берёт файл по имени меша.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def bench() -> Path:
    sys.path.insert(0, str(HERE))
    from locate import morphbench                   # noqa: WPS433
    return morphbench(HERE)


def fix(nif: Path, tri: Path | None, margin: str | None, dry: bool) -> int:
    if not nif.is_file():
        raise SystemExit("нет меша: %s" % nif)
    # Пишем в СОСЕДНИЙ файл и подменяем: верстак ищет морфы по имени меша, и временное
    # имя вроде `x.bounds.nif` увело бы его от `<тело>.tri`. Ключ --tri это снимает,
    # но подмена на месте всё равно безопаснее записи поверх читаемого файла.
    tmp = nif.with_suffix(".bounds.nif")
    cmd = [sys.executable, str(bench()), "bounds", str(nif), "--write", str(tmp)]
    if tri is not None:
        cmd += ["--tri", str(tri)]
    if margin is not None:
        cmd += ["--margin", margin]
    print("  " + " ".join('"%s"' % c if " " in c else c for c in cmd))
    if dry:
        return 0
    done = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.stdout:
        print("\n".join("    " + s for s in done.stdout.rstrip().splitlines()[-20:]))
    if done.returncode != 0 or not tmp.is_file():
        raise SystemExit("верстак отказал:\n" + (done.stderr or done.stdout or "")[-2000:])
    before, after = nif.stat().st_size, tmp.stat().st_size
    shutil.move(str(tmp), str(nif))
    print("    размер: %d -> %d (%s)"
          % (before, after, "тот же" if before == after else "ИЗМЕНИЛСЯ"))
    return 0


def main(argv: list[str]) -> int:
    names = [a for a in argv if not a.startswith("--")]
    if not names:
        sys.stderr.write(__doc__)
        return 2
    tri = Path(argv[argv.index("--tri") + 1]) if "--tri" in argv else None
    margin = argv[argv.index("--margin") + 1] if "--margin" in argv else None
    return fix(Path(names[0]), tri, margin, "--dry" in argv)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
