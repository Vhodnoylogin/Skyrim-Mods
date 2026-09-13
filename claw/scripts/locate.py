r"""Находит корень проекта и соседние модули — поиском метки, а не счётом родителей.

Зачем. Скрипты сборки ходят наружу модуля за двумя вещами: за `tools\paths` проекта
и за верстаком `dev\morphbench`. Раньше путь считался счётом родительских папок
(`ROOT.parent.parent`), и это молча привязывало код к глубине, на которой лежит модуль.
Стоило переложить модуль на уровень глубже — и сборка искала `tools` не там, где он есть.

Правило проекта то же самое: пути выводятся, а не зашиваются. Счёт родителей — такая же
зашитая величина, как абсолютный путь, только менее заметная.

Метка корня — файл `tools\paths.py`: он есть в проекте всегда, потому что через него
выводятся все остальные пути.
"""
from __future__ import annotations

from pathlib import Path

#: По этому файлу опознаётся корень проекта.
MARKER = Path("tools") / "paths.py"


def project_root(start: Path | str | None = None) -> Path:
    """Ближайшая папка вверх по дереву, в которой лежит `tools\\paths.py`."""
    here = Path(start or __file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / MARKER).is_file():
            return candidate
    raise SystemExit(
        "не найден корень проекта: вверх от %s нет папки с %s" % (here, MARKER))


def project_tools(start: Path | str | None = None) -> Path:
    """Папка `tools\\` проекта — её кладут в sys.path, чтобы импортировать `paths`."""
    return project_root(start) / "tools"


def morphbench(start: Path | str | None = None) -> Path:
    """`mb.py` верстака: соседняя рабочая копия ветки `morphbench`.

    Ищется от корня проекта, а не от модуля: рабочие копии лежат рядом в `dev\\`,
    и их взаимное расположение задано раскладкой проекта, а не глубиной модуля.
    """
    path = project_root(start) / "dev" / "morphbench" / "mb.py"
    if not path.is_file():
        raise SystemExit("не найден верстак: %s" % path)
    return path
