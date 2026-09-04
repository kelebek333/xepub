import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "xepub"))
from state import StateStore


class StateTests(unittest.TestCase):
    def test_atomic_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; state = StateStore(path)
            state.book("abc")["chapter"] = 2; state.preferences["theme"] = "sepia"; state.save()
            restored = StateStore(path)
            self.assertEqual(restored.book("abc")["chapter"], 2)
            self.assertEqual(restored.preferences["theme"], "sepia")


if __name__ == "__main__": unittest.main()
