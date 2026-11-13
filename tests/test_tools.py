import unittest

from tests.helpers import TempCase
from tools.file_manager import FileManager
from tools.task_manager import TaskManager


class FileManagerTests(TempCase):
    def setUp(self):
        super().setUp()
        self.fm = FileManager(self.tmp / "ws")

    def test_roundtrip(self):
        self.fm.write("a/hello.txt", "Hi")
        self.assertEqual(self.fm.read("a/hello.txt"), "Hi")
        self.assertEqual(self.fm.list(), ["a/hello.txt"])

    def test_path_traversal_blocked(self):
        for bad in ["../evil.txt", "/etc/passwd", "a/../../x"]:
            with self.subTest(bad=bad):
                with self.assertRaises(PermissionError):
                    self.fm.write(bad, "x")
        self.assertFalse((self.tmp / "evil.txt").exists())

    def test_read_missing_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.fm.read("nope.txt")


class TaskManagerTests(TempCase):
    def test_lifecycle(self):
        t = TaskManager(self.db)
        t.add("learn Flask", "High")
        t.add("write tests")
        self.assertEqual(t.pending_count(), 2)
        t.complete(1)
        self.assertEqual(t.list(), ["#2 [Medium] write tests"])
        t.delete(2)
        self.assertEqual(t.pending_count(), 0)

    def test_errors(self):
        t = TaskManager(self.db)
        with self.assertRaises(ValueError):
            t.add("")
        with self.assertRaises(LookupError):
            t.complete(99)
        with self.assertRaises(LookupError):
            t.delete(99)


if __name__ == "__main__":
    unittest.main()
