# -*- coding: utf-8 -*-
"""Локализация: код несёт ключи, тексты лежат в файлах языков.

Ловит: ключ, для которого нет текста ни в языке, ни в базовом; подстановку по месту вместо
подстановки по имени; отсутствующий или испорченный файл языка, лишающий программу
сообщений; расхождение состава ключей между языками; ключ, случайно оставленный
английской фразой.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench import i18n  # noqa: E402

LOCALE = Path(i18n.__file__).resolve().parent.parent / "locale"


def write(folder: Path, name: str, data: dict, section: str = "") -> None:
    """Словарь языка: единым файлом либо файлом раздела внутри папки языка."""
    if section:
        (folder / name).mkdir(parents=True, exist_ok=True)
        path = folder / name / ("%s.json" % section)
    else:
        path = folder / ("%s.json" % name)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def texts_of(language: str) -> dict:
    """Все тексты одного языка из папки выпуска: файлы раздела слиты в один словарь."""
    out = {}
    for path in sorted((LOCALE / language).glob("*.json")):
        for k, v in json.loads(path.read_text(encoding="utf-8-sig")).items():
            if not k.startswith("#"):
                out[k] = v
    return out


class TestCatalogue(unittest.TestCase):

    def test_falls_back_to_base_then_to_the_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"a.one": "one", "a.two": "two"})
            write(folder, "xx", {"a.one": "один"})
            cat = i18n.Catalogue("xx", folder)
            self.assertEqual(cat("a.one"), "один")     # свой язык
            self.assertEqual(cat("a.two"), "two")      # базовый
            self.assertEqual(cat("a.three"), "a.three")  # сам ключ - видно и можно найти

    def test_named_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"k": "%(what)s at %(where)s"})
            write(folder, "xx", {"k": "в %(where)s лежит %(what)s"})   # порядок слов другой
            self.assertEqual(i18n.Catalogue("en", folder)("k", what="меш", where="папке"),
                             "меш at папке")
            self.assertEqual(i18n.Catalogue("xx", folder)("k", what="меш", where="папке"),
                             "в папке лежит меш")

    def test_translator_slip_does_not_lose_the_message(self):
        """Опечатка переводчика в подстановке - не повод отказать: текст уходит как есть,
        а значения приписываются, чтобы сказанное не пропало."""
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"k": "port %(port)d taken"})
            write(folder, "xx", {"k": "порт %(prot)d занят"})          # опечатка в имени
            out = i18n.Catalogue("xx", folder)("k", port=8767)
            self.assertIn("8767", out)
            self.assertIn("порт", out)

    def test_missing_or_broken_file_leaves_the_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"k": "text"})
            (folder / "bad.json").write_text("{ это не json", encoding="utf-8")
            cat = i18n.Catalogue("bad", folder)
            self.assertEqual(cat.language, "en")       # откатились к базовому
            self.assertEqual(cat("k"), "text")
            self.assertIsNotNone(cat.problem)
            self.assertEqual(i18n.Catalogue("нетТакогоЯзыка", folder).language, "en")

    def test_unknown_language_is_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"k": "text"})
            cat = i18n.Catalogue("en", folder)
            self.assertEqual(cat.use("de"), "en")
            self.assertEqual(cat("k"), "text")

    def test_comment_keys_are_not_texts(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"#": "пояснение для переводчика", "k": "text"})
            cat = i18n.Catalogue("en", folder)
            self.assertEqual(cat.text("#"), "#")


class TestFolders(unittest.TestCase):
    """Язык - папка с произвольными файлами разделов: новый раздел кладут НОВЫМ файлом,
    и ни один существующий при этом не переписывается."""

    def test_sections_merge_into_one_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"cli.one": "one"}, section="cli")
            write(folder, "en", {"page.two": "two"}, section="page")
            cat = i18n.Catalogue("en", folder)
            self.assertEqual(cat("cli.one"), "one")
            self.assertEqual(cat("page.two"), "two")
            # Добавить раздел - это положить ещё один файл, ничего не трогая.
            write(folder, "en", {"page.three": "three"}, section="extra")
            self.assertEqual(i18n.Catalogue("en", folder)("page.three"), "three")

    def test_folder_language_falls_back_to_folder_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"a.one": "one", "a.two": "two"}, section="a")
            write(folder, "xx", {"a.one": "один"}, section="a")
            cat = i18n.Catalogue("xx", folder)
            self.assertEqual(cat("a.one"), "один")
            self.assertEqual(cat("a.two"), "two")

    def test_one_key_in_two_files_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"a.one": "первый"}, section="one")
            write(folder, "en", {"a.one": "второй"}, section="two")
            cat = i18n.Catalogue("en", folder)
            self.assertEqual(cat("a.one"), "первый")      # берётся первый по имени файла
            self.assertIsNotNone(cat.problem)
            self.assertIn("a.one", cat.problem)

    def test_available_lists_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write(folder, "en", {"a.one": "one"}, section="a")
            write(folder, "ru", {"a.one": "один"}, section="a")
            write(folder, "de", {"a.one": "eins"})            # единым файлом - тоже язык
            self.assertEqual(i18n.Catalogue("en", folder).available(), ["de", "en", "ru"])


class TestShippedLocales(unittest.TestCase):
    """Словари, которые едут с верстаком."""

    def setUp(self):
        self.langs = {p.name: texts_of(p.name) for p in LOCALE.iterdir() if p.is_dir()}
        self.keys = {lang: set(d) for lang, d in self.langs.items()}

    def test_english_is_there_and_is_the_base(self):
        self.assertIn("en", self.langs)
        self.assertIn("ru", self.langs)
        self.assertTrue(self.keys["en"], "в английском нет ни одного текста")
        # Единых файлов рядом с папками быть не должно: раскладка одна, а не две.
        self.assertEqual(sorted(p.name for p in LOCALE.glob("*.json")), [])

    def test_every_language_covers_the_same_keys(self):
        base = self.keys["en"]
        for lang, keys in self.keys.items():
            self.assertEqual(keys - base, set(), "лишние ключи в %s" % lang)
            self.assertEqual(base - keys, set(), "непереведённые ключи в %s" % lang)

    def test_keys_are_labels_not_sentences(self):
        for key in self.keys["en"]:
            self.assertNotIn(" ", key, key)
            self.assertTrue(key.isascii(), key)
            self.assertIn(".", key, "ключ без раздела: %s" % key)

    def test_substitutions_match_between_languages(self):
        import re
        holes = re.compile(r"%\((\w+)\)")
        for key in self.keys["en"]:
            base = set(holes.findall(self.langs["en"][key]))
            for lang, texts in self.langs.items():
                self.assertEqual(set(holes.findall(texts[key])), base,
                                 "подстановки разошлись: %s в %s" % (key, lang))

    def test_keys_in_use_have_texts(self):
        """Всякий ключ, названный в коде, должен иметь текст - иначе пользователь увидит
        саму метку."""
        import re
        used = set()
        call = re.compile(r'\bt\(\s*"([a-zA-Z][\w.]*\w)"')
        root = LOCALE.parent
        for folder in ("morphbench", "presenters", "."):
            for path in sorted((root / folder).glob("*.py")):
                used |= set(call.findall(path.read_text(encoding="utf-8")))
        self.assertTrue(used, "ни одного ключа в коде не нашлось - проверка сломана")
        self.assertEqual(used - self.keys["en"], set(), "в коде есть ключи без текста")


if __name__ == "__main__":
    common.main()
