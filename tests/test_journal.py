# -*- coding: utf-8 -*-
"""Журнал: уровни решают что писать, приёмники — куда, и отказ приёмника ничего не уносит.

Главное, ради чего набор заведён: сервер писал журнал в трубу к окну запуска, окно снимали,
труба закрывалась — и падение записи обрывало клиенту связь без ответа. Поэтому здесь
проверяется не только разбор уровней, но и то, что мёртвый приёмник не мешает живому
и что запись не бросает наружу вообще никогда.
"""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

from morphbench.journal import (Journal, ListSink, FileSink, StreamSink,  # noqa: E402
                                level_of, level_name, from_config)
from morphbench.config import Config  # noqa: E402


class DeadStream:
    """Труба, читателя у которой не стало: так ведёт себя поток к снятому окну."""

    def __init__(self, error=None):
        self.error = error or OSError(22, "The pipe is being closed")

    def write(self, _text):
        raise self.error

    def flush(self):
        raise self.error


class NarrowStream(io.StringIO):
    """Консоль в cp1251: кириллица ей не по зубам, но это не отказ трубы."""

    def __init__(self):
        super().__init__()
        self.seen = []

    def write(self, text):
        if any(ord(c) > 127 for c in text):
            raise UnicodeEncodeError("cp1251", text, 0, 1, "не та кодовая страница")
        self.seen.append(text)
        return super().write(text)


class TestLevels(unittest.TestCase):

    def test_names_and_numbers(self):
        self.assertEqual(level_of("info"), 20)
        self.assertEqual(level_of("ERROR"), 40)
        self.assertEqual(level_of(20), 20)
        self.assertEqual(level_name(40), "error")

    def test_unknown_name_refuses_at_once(self):
        # Молча пропущенные записи хуже отказа: неизвестный уровень виден сразу.
        with self.assertRaises(ValueError) as e:
            level_of("подробно")
        self.assertIn("подробно", str(e.exception))

    def test_threshold_filters(self):
        low, high = ListSink("debug"), ListSink("warn")
        j = Journal([low, high])
        j.debug("мелочь")
        j.info("событие")
        j.error("беда")
        self.assertEqual(len(low.lines), 3)
        self.assertEqual(len(high.lines), 1)
        self.assertIn("беда", high.lines[0])

    def test_line_carries_level_and_prefix(self):
        sink = ListSink("debug")
        Journal([sink], prefix="serve").info("готово")
        self.assertTrue(sink.lines[0].startswith("info "), sink.lines[0])
        self.assertIn("serve: готово", sink.lines[0])


class TestSinkFailure(unittest.TestCase):

    def test_dead_sink_does_not_stop_the_living(self):
        dead, alive = StreamSink(DeadStream(), "debug"), ListSink("debug")
        j = Journal([dead, alive])
        j.info("первая")
        j.info("вторая")
        self.assertFalse(dead.alive)
        # Живой получил обе записи плюс известие о выбывшем приёмнике.
        self.assertIn("первая", "\n".join(alive.lines))
        self.assertIn("вторая", "\n".join(alive.lines))
        self.assertTrue(any("dropped out" in line for line in alive.lines), alive.lines)

    def test_failure_is_reported_once(self):
        dead, alive = StreamSink(DeadStream(), "debug"), ListSink("debug")
        j = Journal([dead, alive])
        for _ in range(5):
            j.info("строка")
        self.assertEqual(sum("dropped out" in line for line in alive.lines), 1, alive.lines)

    def test_log_never_raises(self):
        # Ни с одним живым приёмником, ни вовсе без приёмников.
        Journal([StreamSink(DeadStream(), "debug")]).error("некуда")
        Journal([]).error("некуда")
        j = Journal([StreamSink(DeadStream(), "debug"), StreamSink(DeadStream(), "debug")])
        j.error("оба мертвы")
        self.assertEqual(j.alive_sinks, [])

    def test_encoding_trouble_is_not_a_failure(self):
        # Консоль в cp1251 — повод написать заменами, а не выбыть.
        stream = NarrowStream()
        sink = StreamSink(stream, "debug")
        Journal([sink]).info("кириллица")
        self.assertTrue(sink.alive)
        self.assertIn("?", stream.getvalue())


class TestFileSink(unittest.TestCase):

    def test_writes_and_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "logs" / "morphbench.log"
            sink = FileSink(path, "debug")
            j = Journal([sink])
            j.info("раз")
            j.debug("два")
            self.assertEqual(path.read_text(encoding="utf-8").count("\n"), 2)
            j.close()
            Journal([FileSink(path, "debug")]).info("три")
            self.assertIn("три", path.read_text(encoding="utf-8"))

    def test_unwritable_path_takes_out_only_the_file(self):
        alive = ListSink("debug")
        # Папка вместо файла: открыть на дозапись нельзя.
        with tempfile.TemporaryDirectory() as tmp:
            sink = FileSink(tmp, "debug")
            j = Journal([sink, alive])
            j.info("запись")
            self.assertFalse(sink.alive)
            self.assertIn("запись", "\n".join(alive.lines))


class TestFromConfig(unittest.TestCase):

    def test_defaults_give_stream_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(Path(tmp) / "morphbench.json")
            j = from_config(cfg, "serve", stream=io.StringIO())
            kinds = [type(s).__name__ for s in j.sinks]
            self.assertEqual(kinds, ["StreamSink", "FileSink"])
            self.assertEqual(j.sinks[0].level, level_of(cfg["logLevel"]))
            # Файл журнала ложится рядом с настройками, а не в текущую папку.
            self.assertEqual(j.sinks[1].path.parent, Path(tmp))
            j.close()

    def test_empty_log_file_means_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "morphbench.json"
            cfg = Config(path)
            cfg._values["logFile"] = ""
            j = from_config(cfg, "serve", stream=io.StringIO())
            self.assertEqual([type(s).__name__ for s in j.sinks], ["StreamSink"])

    def test_bad_level_does_not_lose_the_journal(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config(Path(tmp) / "morphbench.json")
            cfg._values["logLevel"] = "подробно"
            cfg._values["logFile"] = ""
            stream = io.StringIO()
            j = from_config(cfg, "serve", stream=stream)
            self.assertEqual(j.sinks[0].level, level_of("info"))
            self.assertIn("подробно", stream.getvalue())
            j.close()


if __name__ == "__main__":
    common.main()
