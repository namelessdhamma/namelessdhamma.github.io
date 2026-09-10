import tempfile
import unittest
from pathlib import Path

from nd_oauth.file_state import FileOAuthStateStore


class FileOAuthStateStoreTests(unittest.TestCase):
    def test_missing_persistent_file_is_empty_first_boot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = FileOAuthStateStore(root / "volume" / "state.json")
            self.assertFalse(store.restore(root / "runtime" / "state.json"))

    def test_persist_and_restore_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "runtime" / "state.json"
            source.parent.mkdir(parents=True)
            source.write_bytes(b'{"clients":1}')
            durable = root / "volume" / "state.json"
            store = FileOAuthStateStore(durable)

            store.persist(source)
            self.assertEqual(durable.read_bytes(), b'{"clients":1}')
            self.assertEqual(durable.stat().st_mode & 0o777, 0o600)

            source.unlink()
            self.assertTrue(store.restore(source))
            self.assertEqual(source.read_bytes(), b'{"clients":1}')
            self.assertEqual(source.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
