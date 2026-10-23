from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing

from workspace_backup import backup, restore, verify


class WorkspaceBackupTest(unittest.TestCase):
    def test_sqlite_wal_and_private_config_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, copy, recovered = (root / name for name in ("source", "backup", "recovered"))
            source.mkdir()
            (source / "config.json").write_text('{"dry_run":true,"api_server":{"password":"local-only"}}')
            database = source / "trades.sqlite"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("CREATE TABLE trades(id INTEGER PRIMARY KEY, profit REAL)")
                connection.execute("INSERT INTO trades(profit) VALUES (1.25)")
                connection.commit()
                backup(source, copy)
            manifest = verify(copy)
            self.assertEqual(len(manifest["files"]), 2)
            self.assertEqual(next(x for x in manifest["files"] if x["path"] == "trades.sqlite")["mode"], "sqlite-online-backup")
            restore(copy, recovered)
            with closing(sqlite3.connect(recovered / "trades.sqlite")) as connection:
                self.assertEqual(connection.execute("SELECT profit FROM trades").fetchone()[0], 1.25)
            self.assertEqual(json.loads((recovered / "config.json").read_text())["api_server"]["password"], "local-only")
            with self.assertRaises(ValueError):
                restore(copy, recovered)

    def test_tamper_is_rejected_before_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, copy = root / "source", root / "backup"
            source.mkdir()
            (source / "data.txt").write_text("original")
            backup(source, copy)
            (copy / "data.txt").write_text("changed")
            with self.assertRaises(ValueError):
                restore(copy, root / "recovered")
            self.assertFalse((root / "recovered").exists())


if __name__ == "__main__":
    unittest.main()
