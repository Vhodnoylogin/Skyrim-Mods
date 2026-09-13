# -*- coding: utf-8 -*-
"""Сборка выпуска: самодостаточный архив верстака.

    python release.py                      собрать в build\\ и запаковать
    python release.py --version 0.9.0      номер выпуска в имя архива и в manifest.json
    python release.py --no-python          без встроенного Python (нужен установленный)
    python release.py --pynifly <папка>    взять аддон отсюда, а не искать
    python release.py --stage-only         разложить папку выпуска и не паковать
    python release.py --list               что войдёт в архив, ничего не делая

Этот скрипт **в архив не попадает**: он принадлежит репозиторию, а не выпуску. Он же
единственное место, где перечислено, что в архив входит, - перечислением, а не
исключением. Поэтому соседние модули репозитория (например, плагин моста MO2, лежащий
в той же рабочей копии) попасть в архив не могут: их просто нет в списке.

Что кладётся внутрь, сказано в `dependencies.json` полем `bundle`, и решает там ЛИЦЕНЗИЯ,
а не удобство. По тому же файлу пишется `THIRD-PARTY.md` - перечень чужого с лицензиями
и адресами исходников, который GPL обязывает показывать.

Голый Python: ничего из верстака здесь не импортируется, чтобы сборка работала и на машине,
где зависимости ещё не разложены.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
_VAR = re.compile(r"%([^%]+)%")

#: Что принадлежит выпуску. Перечисление, а не исключение: всё, чего здесь нет, в архив
#: не попадёт, сколько бы ни лежало рядом в рабочей копии.
CONTENT = [
    "mb.py",
    "morphbench.exe",
    "LICENSE",
    "README.md",
    "dependencies.json",
    "morphbench/*.py",
    "presenters/*.py",
    "locale/*/*.json",
    "web/*.html",
    "web/*.css",
    "web/js/*.js",
    "docs/*.md",
]
#: Что не кладём, даже если оно подошло под образец выше.
SKIP = ("__pycache__", ".pyc", "morphbench.json", "morphbench.log")


def load_manifest(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8-sig")).get("dependencies", [])


def expand(pattern: str, home: Path) -> str:
    text = _VAR.sub(lambda m: os.environ.get(m.group(1), m.group(0)), pattern)
    if text.startswith("./") or text.startswith(".\\"):
        text = str(home / text[2:])
    return text


def own_files(home: Path) -> list[Path]:
    """Файлы самого верстака по списку CONTENT, в порядке имён."""
    out = []
    for pattern in CONTENT:
        for found in sorted(glob.glob(str(home / pattern))):
            p = Path(found)
            if p.is_file() and not any(s in str(p) for s in SKIP):
                out.append(p)
    return out


def find_folder(dep: dict, home: Path, named: str | None) -> Path | None:
    """Папка зависимости на машине сборщика: названная доводом либо найденная по образцам
    и опознанная по файлам внутри - чтобы не взять одноимённую чужую."""
    proof = [str(p) for p in dep.get("proof", [])]

    def fits(folder: Path) -> bool:
        return folder.is_dir() and all((folder / p).exists() for p in proof)

    if named:
        folder = Path(named)
        if not fits(folder):
            raise SystemExit("в %s нет файлов %s - это не %s"
                             % (folder, ", ".join(proof), dep.get("name")))
        return folder
    for pattern in [str(p) for p in dep.get("search", [])]:
        for candidate in sorted(glob.glob(expand(pattern, home)), reverse=True):
            if fits(Path(candidate)):
                return Path(candidate)
    return None


# ---- укладка зависимостей ----------------------------------------------------------------
def vendor_folder(dep: dict, home: Path, stage: Path, named: str | None) -> str:
    folder = find_folder(dep, home, named)
    if folder is None:
        raise SystemExit("не нашёл %s; назовите папку доводом или возьмите: %s"
                         % (dep["name"], dep.get("source", "")))
    target = stage / str(dep.get("into") or ("vendor/" + dep["name"]))
    shutil.copytree(folder, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "docs"))
    return "%s <- %s" % (target.relative_to(stage), folder)


def vendor_packages(deps: list[dict], stage: Path) -> list[str]:
    """Пакеты python - тем же pip, но в папку выпуска, а не в систему."""
    names = [str(d.get("pip") or d["name"]) for d in deps]
    if not names:
        return []
    into = stage / str(deps[0].get("into") or "vendor")
    into.mkdir(parents=True, exist_ok=True)
    code = subprocess.call([sys.executable, "-m", "pip", "install", "--upgrade",
                            "--target", str(into)] + names)
    if code != 0:
        raise SystemExit("pip не разложил %s, код %d" % (", ".join(names), code))
    for junk in list(into.glob("*.dist-info")) + list(into.glob("__pycache__")):
        shutil.rmtree(junk, ignore_errors=True)
    return ["%s <- pip" % (into.relative_to(stage) / n) for n in names]


def vendor_python(dep: dict, stage: Path, version: str) -> str:
    """Встраиваемая поставка Python с python.org: архив без установщика, разворачивается
    в папку. С ней выпуск самодостаточен - ставить пользователю нечего."""
    url = str(dep.get("embeddable", "")) % {"version": version}
    into = stage / str(dep.get("into") or "python")
    into.mkdir(parents=True, exist_ok=True)
    tmp = into / "embed.zip"
    print("  качаю %s" % url)
    with urllib.request.urlopen(url, timeout=180) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(into)
    tmp.unlink()
    # Встраиваемая поставка по умолчанию не смотрит по сторонам: разрешаем ей видеть
    # vendor\ и папку верстака, иначе numpy и PyNifly останутся невидимыми.
    for pth in into.glob("python*._pth"):
        # В поставке строка site закомментирована; дописывать рядом нельзя - надо снять
        # именно её, иначе прежняя останется и пути так и не подхватятся.
        keep = [l.rstrip() for l in pth.read_text(encoding="utf-8").splitlines()
                if l.strip().lstrip("#").strip() not in ("import site", "..", "..\\vendor")]
        pth.write_text("\n".join(keep + ["..", "..\\vendor", "import site"]) + "\n",
                       encoding="utf-8")
    return "%s <- %s" % (into.relative_to(stage), url)


def third_party(deps: list[dict], stage: Path, version: str) -> None:
    """Перечень чужого внутри пакета: что, зачем, под чем и откуда исходники.
    GPL требует, чтобы это ехало вместе с двоичным."""
    lines = ["# Чужое внутри morphbench %s" % version, "",
             "morphbench под GNU GPL 3 (LICENSE рядом). Внутри пакета лежит чужое:", ""]
    for dep in deps:
        inside = "внутри: %s" % dep["into"] if dep.get("bundle") else "НЕ внутри, ставится отдельно"
        lines += ["## %s — %s" % (dep["name"], dep.get("license", "лицензия не названа")),
                  "", "Зачем: %s" % dep.get("why", ""), "", "%s" % inside,
                  "Исходники: %s" % dep.get("source", "не названы"), ""]
    lines += ["## Исходники самого morphbench", "",
              "GPL даёт право получить исходники всего, что здесь лежит. Исходники верстака",
              "едут прямо в этом архиве: это тот же python, который и работает.", ""]
    (stage / "THIRD-PARTY.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="release.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="0.0.0", help="номер выпуска")
    ap.add_argument("--out", default=None, help="куда складывать; по умолчанию build\\")
    ap.add_argument("--pynifly", default=None, help="папка аддона PyNifly")
    ap.add_argument("--python-version", default="3.12.8", help="какой Python вкладывать")
    ap.add_argument("--no-python", action="store_true", help="без встроенного Python")
    ap.add_argument("--no-vendor", action="store_true", help="без чужого вовсе: только верстак")
    ap.add_argument("--stage-only", action="store_true", help="разложить папку и не паковать")
    ap.add_argument("--list", action="store_true", help="что войдёт в архив, ничего не делая")
    args = ap.parse_args(argv)

    home = HERE
    deps = load_manifest(home / "dependencies.json")
    files = own_files(home)
    if args.list:
        for f in files:
            print("  %s" % f.relative_to(home))
        print("\nсвоих файлов: %d" % len(files))
        for dep in deps:
            print("  %-10s %s" % (dep["name"], "внутрь: " + str(dep.get("into"))
                                  if dep.get("bundle") else "НЕ внутрь"))
        return 0

    out = Path(args.out) if args.out else home / "build"
    stage = out / ("morphbench-%s" % args.version)
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    for f in files:
        target = stage / f.relative_to(home)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)
    print("своё: %d файлов" % len(files))

    laid = []
    if not args.no_vendor:
        packages = [d for d in deps if d.get("bundle") and d.get("kind") == "python-package"]
        laid += vendor_packages(packages, stage)
        for dep in deps:
            if dep.get("bundle") and dep.get("kind") == "folder":
                laid.append(vendor_folder(dep, home, stage, args.pynifly))
        runtime = [d for d in deps if d.get("bundle") and d.get("kind") == "runtime"]
        if runtime and not args.no_python:
            laid.append(vendor_python(runtime[0], stage, args.python_version))
    for line in laid:
        print("  %s" % line)

    third_party(deps, stage, args.version)
    (stage / "manifest.json").write_text(json.dumps(
        {"name": "morphbench", "version": args.version, "license": "GPL-3.0",
         "python": None if args.no_python else args.python_version,
         "bundled": [d["name"] for d in deps if d.get("bundle")] if not args.no_vendor else []},
        ensure_ascii=False, indent=2), encoding="utf-8")

    if args.stage_only:
        print("разложено: %s" % stage)
        return 0
    archive = shutil.make_archive(str(out / ("morphbench-%s" % args.version)), "zip",
                                  root_dir=str(out), base_dir=stage.name)
    size = Path(archive).stat().st_size
    print("архив: %s (%.1f МБ)" % (archive, size / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
