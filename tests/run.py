# -*- coding: utf-8 -*-
"""Прогнать все проверки подряд.

Наборы находятся обходом папки (unittest discovery, файлы test_*.py). Те, которым нужен
PyNifly для записи настоящего файла, пропускаются с внятным словом, если аддона нет:
пропуск — это не сбой, а честное «проверить было нечем».

    python tests/run.py               все наборы
    python tests/run.py test_tri.py   один набор (шаблон имени файла)
"""
import os
import sys
import unittest

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _modules(suite, acc: set) -> set:
    """Имена модулей всех проверок в наборе: столько «наборов» и прогнано."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            _modules(item, acc)
        else:
            acc.add(item.__class__.__module__)
    return acc


def main(argv) -> int:
    pattern = argv[1] if len(argv) > 1 else "test_*.py"
    suite = unittest.defaultTestLoader.discover(HERE, pattern=pattern, top_level_dir=HERE)
    modules = _modules(suite, set())
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)

    broken = {t.__class__.__module__ for t, _ in result.failures + result.errors}
    print()
    print("=" * 78)
    print("наборов: %d, со сбоями: %d, проверок: %d, сбоев: %d, ошибок: %d, пропущено: %d"
          % (len(modules), len(broken), result.testsRun, len(result.failures),
             len(result.errors), len(result.skipped)))
    if broken:
        print("наборы со сбоями: %s" % ", ".join(sorted(broken)))
    return 1 if (result.failures or result.errors) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
