import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "xepub"))
from paginator import command


class PaginatorTests(unittest.TestCase):
    def test_command_serializes_arguments(self):
        source = command("goTo", '[data-annotation-id="abc"]')
        self.assertIn('goTo("[data-annotation-id=\\"abc\\"]")', source)
        self.assertIn("document.documentElement.clientWidth", source)
        self.assertNotIn("devicePixelRatio", source)

    def test_unknown_operation_is_rejected(self):
        with self.assertRaises(ValueError):
            command("arbitraryBookCode")


if __name__ == "__main__":
    unittest.main()
