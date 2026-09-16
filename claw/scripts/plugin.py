"""Плагины мода: текст - исходник, .esp - продукт.

Запись .esp двоичная: git хранил бы её полной копией на каждую правку и не показал бы
ни одного различия. Поэтому исходником плагина считается ТЕКСТ, который раскладывает
Spriggit: папка `claw\\plugins\\<имя>\\` с одним `.yaml` на запись. Его видно в различиях,
его можно править руками и сливать.

Сам .esp при этом тоже хранится - в LFS, независимо от веса, - потому что он входит
в выпуск: без него мод не собрать на машине, где Spriggit не поставлен.

    python claw/scripts/plugin.py dump  [имя]   .esp  ->  текст
    python claw/scripts/plugin.py build [имя]   текст ->  .esp
    python claw/scripts/plugin.py check [имя]   собрать во временное и сверить с хранимым

Без имени берутся все плагины сразу. Имя - название папки в `claw\\plugins\\`.

ВАЖНО про сверку. Обратный ход Spriggit **не побайтовый**: он переписывает заголовок
плагина по-своему (счётчик записей, следующий свободный номер). Поэтому `check` сверяет
не байты, а текст: собранный .esp раскладывается обратно и сравнивается с исходной папкой.
Расхождение в тексте - настоящая потеря, расхождение в байтах - нет.
"""
import filecmp
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from locate import project_tools                        # noqa: E402
sys.path.insert(0, str(project_tools(HERE)))
from paths import P                                     # noqa: E402

SOURCES = ROOT / "plugins"
BUILT = ROOT / "assets" / "plugins"
WRAPPER = (P.mods / "Skyrim-Claude Code Modder's Toolkit" / "tools" / "spriggit-cli.sh")

# Раскладка Spriggit: пакет задаёт формат текста, выпуск - набор полей записи.
# Плагин собран под SkyrimSE даже для VR: формат записей у них общий, а флаг ESL
# читает мод Skyrim VR ESL Support.
PACKAGE = "Spriggit.Yaml"
RELEASE = "SkyrimSE"
VERSION = "0.41.0"


def git_bash():
    """Путь к bash из комплекта Git.

    Просто `bash` брать нельзя: в Windows на PATH первым стоит `System32\\bash.exe` -
    точка входа в WSL, и без установленного дистрибутива она отвечает отказом,
    который выглядит как отказ Spriggit. Поэтому bash берётся оттуда же, откуда git.
    """
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parents[1] / "bin" / "bash.exe"
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("bash")
    if found and "system32" not in found.lower():
        return found
    raise SystemExit("не найден bash из комплекта Git")


class Spriggit:
    """Обёртка над обёрткой: Toolkit уже чинит длинные пути, здесь - только доводы."""

    def __init__(self, wrapper):
        if not wrapper.is_file():
            raise SystemExit("не найден spriggit-cli.sh: %s" % wrapper)
        self.wrapper = wrapper
        self.bash = git_bash()

    def _run(self, *args):
        cmd = [self.bash, str(self.wrapper)] + [str(a) for a in args]
        done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if done.returncode != 0:
            # Spriggit пишет и в поток ошибок, и в обычный: показывать оба, иначе
            # причина отказа теряется и остаётся голый код возврата.
            sys.stderr.write((done.stderr or "") + (done.stdout or ""))
            raise SystemExit("spriggit вернул %d" % done.returncode)

    def dump(self, esp, folder):
        self._run("serialize", "--InputPath", esp, "--OutputPath", folder,
                  "--GameRelease", RELEASE, "--PackageName", PACKAGE,
                  "--PackageVersion", VERSION)

    def build(self, folder, esp):
        self._run("deserialize", "--InputPath", folder, "--OutputPath", esp)


def names(argv):
    """Имена плагинов: заданные доводом либо все папки исходников."""
    if argv:
        return argv
    if not SOURCES.is_dir():
        raise SystemExit("нет папки исходников: %s" % SOURCES)
    return sorted(p.name for p in SOURCES.iterdir() if p.is_dir())


def differs(left, right):
    """Различия двух деревьев текста - списком путей, а не первым попавшимся."""
    out = []
    cmp = filecmp.dircmp(str(left), str(right))
    stack = [("", cmp)]
    while stack:
        prefix, node = stack.pop()
        for name in node.left_only:
            out.append("только в исходнике: %s%s" % (prefix, name))
        for name in node.right_only:
            out.append("только в собранном: %s%s" % (prefix, name))
        for name in node.diff_files:
            out.append("различается: %s%s" % (prefix, name))
        for name, sub in node.subdirs.items():
            stack.append(("%s%s/" % (prefix, name), sub))
    return out


def cmd_dump(sp, name):
    esp = BUILT / ("%s.esp" % name)
    if not esp.is_file():
        raise SystemExit("нет плагина: %s" % esp)
    folder = SOURCES / name
    if folder.exists():
        shutil.rmtree(folder)
    sp.dump(esp, folder)
    print("   %-24s .esp -> текст (%d файлов)" % (name, len(list(folder.rglob("*")))))
    return True


def cmd_build(sp, name):
    folder = SOURCES / name
    if not folder.is_dir():
        raise SystemExit("нет исходника: %s" % folder)
    BUILT.mkdir(parents=True, exist_ok=True)
    esp = BUILT / ("%s.esp" % name)
    sp.build(folder, esp)
    print("   %-24s текст -> .esp (%d байт)" % (name, esp.stat().st_size))
    return True


def cmd_check(sp, name):
    """Собрать во временное, разложить обратно и сверить текст с текстом."""
    folder = SOURCES / name
    if not folder.is_dir():
        raise SystemExit("нет исходника: %s" % folder)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        esp = tmp / ("%s.esp" % name)
        sp.build(folder, esp)
        again = tmp / "again"
        sp.dump(esp, again)
        bad = differs(folder, again)
    if bad:
        print("   %-24s РАЗОШЁЛСЯ:" % name)
        for line in bad:
            print("      %s" % line)
        return False
    stored = BUILT / ("%s.esp" % name)
    mark = "" if stored.is_file() else "   (хранимого .esp нет!)"
    print("   %-24s текст сходится%s" % (name, mark))
    return stored.is_file()


CMDS = {"dump": cmd_dump, "build": cmd_build, "check": cmd_check}


def main(argv):
    if not argv or argv[0] not in CMDS:
        raise SystemExit(__doc__)
    action, rest = CMDS[argv[0]], argv[1:]
    sp = Spriggit(WRAPPER)
    print("%s:" % argv[0])
    ok = all([action(sp, name) for name in names(rest)])
    print("итог: %s" % ("сошлось" if ok else "ЕСТЬ РАСХОЖДЕНИЯ"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
