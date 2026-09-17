from pathlib import Path
import unittest


# These contract tests intentionally inspect the production adapter surface.
class DriveSourceContractTests(unittest.TestCase):
    def test_source_add_drive_requires_and_passes_title(self):
        app = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        block = app.split('elif operation == "source_add_drive":', 1)[1].split('elif operation == "source_delete":', 1)[0]

        self.assertIn('title = str(args.get("title") or "").strip()', block)
        self.assertIn('if not file_id or not title:', block)
        self.assertIn('"missing_file_id_or_title"', block)
        self.assertIn('client.sources.add_drive(nb_id, file_id, title)', block)

    def test_source_ensure_fresh_is_idempotent_and_bounded(self):
        app = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertIn('elif operation == "source_ensure_fresh":', app)
        block = app.split('elif operation == "source_ensure_fresh":', 1)[1].split('elif operation == "source_sync_drive":', 1)[0]

        self.assertIn('initial_fresh = await client.sources.check_freshness(nb_id, source_id)', block)
        self.assertIn('if initial_fresh:', block)
        self.assertIn('refreshed = await client.sources.refresh(nb_id, source_id)', block)
        self.assertIn('for attempt in range(max_checks):', block)
        self.assertIn('await asyncio.sleep(poll_seconds)', block)
        self.assertIn('final_fresh = await client.sources.check_freshness(nb_id, source_id)', block)
        self.assertIn('"refreshed": not bool(initial_fresh)', block)
        self.assertIn('"is_fresh": bool(final_fresh)', block)

    def test_source_bind_drive_searches_safely_and_avoids_duplicates(self):
        app = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
        self.assertIn('async def _drive_search_files(', app)
        self.assertIn('elif operation == "source_bind_drive":', app)
        block = app.split('elif operation == "source_bind_drive":', 1)[1].split('elif operation == "source_add_drive":', 1)[0]

        self.assertIn('provide_exactly_one_drive_selector', block)
        self.assertIn('_drive_metadata_user(file_id)', block)
        self.assertIn('_drive_search_files(name=name, query=query)', block)
        self.assertIn('"drive_file_not_found"', block)
        self.assertIn('"drive_file_ambiguous"', block)
        self.assertIn('drive_document_id', block)
        self.assertIn('"already_bound": True', block)
        self.assertIn('client.sources.add_drive(nb_id, file_id, title)', block)


if __name__ == "__main__":
    unittest.main()
