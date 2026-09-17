from pathlib import Path
import unittest


class DriveSourceContractTests(unittest.TestCase):
    def test_source_add_drive_requires_and_passes_title(self):
        app = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        block = app.split('elif operation == "source_add_drive":', 1)[1].split('elif operation == "source_delete":', 1)[0]

        self.assertIn('title = str(args.get("title") or "").strip()', block)
        self.assertIn('if not file_id or not title:', block)
        self.assertIn('"missing_file_id_or_title"', block)
        self.assertIn('client.sources.add_drive(nb_id, file_id, title)', block)


if __name__ == "__main__":
    unittest.main()
