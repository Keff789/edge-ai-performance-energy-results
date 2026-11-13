"""Output admission guards keep existing scientific inputs outside write scope."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
SPEC = importlib.util.spec_from_file_location("audit_reproduce", HERE / "reproduce.py")
reproduce = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reproduce)


class OutputProtectionTests(unittest.TestCase):
    def test_historical_and_input_directories_cannot_be_outputs(self):
        root = reproduce.REPO
        for path in (root, root.parent, root / "results/split-inference/data",
                     root / reproduce.STUDY / "inputs", HERE,
                     root / reproduce.STUDY / "nested"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                reproduce.validate_output(root, path, False)
        self.assertEqual(reproduce.validate_output(root, root / reproduce.STUDY, False),
                         root / reproduce.STUDY)
        with self.assertRaises(ValueError):
            reproduce.validate_output(root, root / reproduce.STUDY, True)

    def test_populated_external_or_symlinked_source_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "new"
            self.assertEqual(reproduce.validate_output(reproduce.REPO, output, True), output)
            output.mkdir()
            (output / "foreign").write_text("preserve")
            with self.assertRaises(ValueError):
                reproduce.validate_output(reproduce.REPO, output, False)
            link = root / "alias"
            link.symlink_to(reproduce.REPO / "results/split-inference")
            with self.assertRaises(ValueError):
                reproduce.validate_output(reproduce.REPO, link, False)
            self.assertEqual((output / "foreign").read_text(), "preserve")


if __name__ == "__main__":
    unittest.main()
