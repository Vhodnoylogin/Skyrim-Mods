# -*- coding: utf-8 -*-
"""Установка верстака: найти чужое за человека и вписать пути в настройки.

    python install.py                что найдено, чего нет и что с этим делать
    python install.py --apply        вписать найденные пути в morphbench.json
    python install.py --pip          доставить недостающие пакеты python
    python install.py --json         то же машинно
    python install.py --manifest X --config Y --search Z    другой манифест, настройки, папка

Заявление о зависимостях лежит рядом в `dependencies.json` и правится человеком; этот
скрипт ничего о зависимостях не знает сам и только исполняет написанное там.

Работает **на голом Python**: ни одной строчки из самого верстака здесь не импортируется.
Иначе установщик не запустился бы ровно в том случае, ради которого он нужен, - когда
numpy ещё не стоит и `import morphbench` падает.

Код выхода: 0 - всё обязательное на месте, 1 - чего-то обязательного нет.
"""
from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_VAR = re.compile(r"%([^%]+)%")


def expand(pattern: str, home: Path) -> str:
    """`%ПЕРЕМЕННАЯ%` из окружения, `./` - от папки верстака. Ненайденная переменная
    оставляет образец как есть: он просто ничего не найдёт, и это честнее подстановки пустоты."""
    def sub(m):
        return os.environ.get(m.group(1), m.group(0))
    text = _VAR.sub(sub, pattern)
    if text.startswith("./") or text.startswith(".\\"):
        text = str(home / text[2:])
    return text


class Check:
    """Ответ по одной зависимости: найдена ли, где, и что делать, если нет."""

    __slots__ = ("dep", "found", "where", "detail")

    def __init__(self, dep: dict, found: bool, where=None, detail: str = ""):
        self.dep = dep
        self.found = bool(found)
        self.where = None if where is None else str(where)
        self.detail = detail

    @property
    def name(self) -> str:
        return str(self.dep.get("name", "?"))

    @property
    def required(self) -> bool:
        return bool(self.dep.get("required", True))

    @property
    def blocking(self) -> bool:
        return self.required and not self.found

    def advice(self) -> str:
        if self.found:
            return ""
        dep = self.dep
        if dep.get("install"):
            return str(dep["install"])
        if dep.get("get"):
            return "взять: %s" % dep["get"]
        return "поставить вручную"

    def as_dict(self) -> dict:
        return {"name": self.name, "kind": dep_kind(self.dep), "required": self.required,
                "found": self.found, "where": self.where, "detail": self.detail,
                "why": str(self.dep.get("why", "")), "advice": self.advice()}


def dep_kind(dep: dict) -> str:
    return str(dep.get("kind", "python-package"))


# ---- проверки по роду -------------------------------------------------------------------
def check_runtime(dep: dict) -> Check:
    least = str(dep.get("minimum", "3")).split(".")
    have = sys.version_info[:len(least)]
    ok = list(have) >= [int(x) for x in least]
    return Check(dep, ok, sys.executable,
                 "%d.%d.%d, нужно не ниже %s" % (sys.version_info[:3] + (".".join(least),)))


def check_package(dep: dict) -> Check:
    name = str(dep.get("import") or dep.get("name"))
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        spec = None
    where = getattr(spec, "origin", None) if spec else None
    return Check(dep, spec is not None, where, "" if spec else "не найден модуль %s" % name)


def check_folder(dep: dict, home: Path, extra: list[str]) -> Check:
    proof = [str(p) for p in dep.get("proof", [])]

    def fits(folder: Path) -> bool:
        return folder.is_dir() and all((folder / p).exists() for p in proof)

    seen = []
    for pattern in list(extra) + [str(p) for p in dep.get("search", [])]:
        for candidate in sorted(glob.glob(expand(pattern, home)), reverse=True):
            folder = Path(candidate)
            seen.append(str(folder))
            if fits(folder):
                return Check(dep, True, folder, "опознана по %s" % ", ".join(proof))
    detail = "просмотрено мест: %d" % len(seen)
    if seen:
        detail += "; ближайшее без нужных файлов: %s" % seen[0]
    return Check(dep, False, None, detail)


def check(dep: dict, home: Path, extra: list[str]) -> Check:
    if dep.get("bundled"):
        folder = home / str(dep["bundled"])
        return Check(dep, folder.exists(), folder, "положена внутрь пакета")
    kind = dep_kind(dep)
    if kind == "runtime":
        return check_runtime(dep)
    if kind == "folder":
        return check_folder(dep, home, extra)
    return check_package(dep)


# ---- настройки --------------------------------------------------------------------------
def apply_settings(checks: list[Check], config: Path) -> list[str]:
    """Вписать найденные пути в настройки. Значение, уже стоящее в файле и указывающее
    на существующее место, не трогается: человек мог поставить его нарочно."""
    written = []
    values = {}
    if config.exists():
        try:
            values = json.loads(config.read_text(encoding="utf-8-sig"))
        except ValueError as e:
            raise SystemExit("настройки %s не читаются: %s" % (config, e))
    for c in checks:
        key = c.dep.get("setting")
        if not key or not c.found or not c.where:
            continue
        old = str(values.get(key, "") or "").strip()
        if old and Path(old).exists():
            continue
        values[key] = c.where
        written.append("%s = %s" % (key, c.where))
    if written:
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text(json.dumps(values, indent=2, ensure_ascii=False), encoding="utf-8")
    return written


def pip_install(checks: list[Check]) -> list[str]:
    """Доставить недостающие пакеты python тем же интерпретатором, которым запущены."""
    done = []
    for c in checks:
        if c.found or dep_kind(c.dep) != "python-package":
            continue
        target = str(c.dep.get("pip") or c.dep.get("name"))
        print("  ставлю %s…" % target)
        code = subprocess.call([sys.executable, "-m", "pip", "install", target])
        done.append("%s: %s" % (target, "поставлен" if code == 0 else "не поставлен, код %d" % code))
    return done


# ---- показ ------------------------------------------------------------------------------
def report(checks: list[Check], config: Path) -> str:
    width = max([len(c.name) for c in checks] + [4])
    lines = []
    for c in checks:
        mark = "есть" if c.found else ("НЕТ " if c.required else "нет ")
        tail = c.where or c.detail
        lines.append("  %s  %-*s  %s" % (mark, width, c.name, tail))
        if not c.found:
            lines.append("  %s  %-*s  %s" % (" " * 4, width, "", c.advice()))
            lines.append("  %s  %-*s  зачем: %s" % (" " * 4, width, "", c.dep.get("why", "")))
    missing = [c for c in checks if c.blocking]
    optional = [c for c in checks if not c.required and not c.found]
    lines.append("")
    if missing:
        lines.append("не хватает обязательного: %s" % ", ".join(c.name for c in missing))
    else:
        lines.append("всё обязательное на месте")
    if optional:
        lines.append("необязательное отсутствует: %s" % ", ".join(c.name for c in optional))
    lines.append("настройки: %s" % config)
    return "\n".join(lines)


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(prog="install.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=None, help="заявление о зависимостях (dependencies.json)")
    ap.add_argument("--config", default=None, help="настройки, куда писать пути (morphbench.json)")
    ap.add_argument("--search", action="append", default=[],
                    help="ещё одно место поиска папок; ключ повторяем")
    ap.add_argument("--apply", action="store_true", help="вписать найденные пути в настройки")
    ap.add_argument("--pip", action="store_true", help="доставить недостающие пакеты python")
    ap.add_argument("--json", action="store_true", help="машинный ответ")
    args = ap.parse_args(argv)

    home = HERE
    manifest = Path(args.manifest) if args.manifest else home / "dependencies.json"
    config = Path(args.config) if args.config else home / "morphbench.json"
    if not manifest.exists():
        raise SystemExit("нет заявления о зависимостях: %s" % manifest)
    deps = json.loads(manifest.read_text(encoding="utf-8-sig")).get("dependencies", [])
    checks = [check(d, home, args.search) for d in deps]

    installed = pip_install(checks) if args.pip else []
    if installed:
        checks = [check(d, home, args.search) for d in deps]
    written = apply_settings(checks, config) if args.apply else []

    if args.json:
        print(json.dumps({"manifest": str(manifest), "config": str(config),
                          "dependencies": [c.as_dict() for c in checks],
                          "installed": installed, "written": written,
                          "ready": not any(c.blocking for c in checks)},
                         ensure_ascii=False, indent=2))
    else:
        print(report(checks, config))
        for line in written:
            print("вписано: %s" % line)
        if not args.apply and any(c.dep.get("setting") and c.found for c in checks):
            print("вписать найденное в настройки: python install.py --apply")
        if any(c.blocking and dep_kind(c.dep) == "python-package" for c in checks):
            print("доставить пакеты python: python install.py --pip")
    return 1 if any(c.blocking for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
