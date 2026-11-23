"""Offline or unreadable image folders must never cost Gallery user data.

Favorites, collections, manual tags and extracted tags live on the file rows of
their root. A drive that is unplugged at startup, disconnects during a scan or
cannot be listed is not a deletion; only removing a folder in Settings is.

Run with CYBERHUB_CORE_PATH=../CyberHub python -m unittest discover -s tests.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_gallery_performance import g


POSIX_USER = os.name == "posix" and getattr(os, "geteuid", lambda: 0)() != 0


class RootAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.photos = self.base / "Photos"
        self.archive = self.base / "Archive"
        for folder, names in ((self.photos, ["p1.png"]), (self.archive, ["x1.png", "sub/x2.png"])):
            for name in names:
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                g.Image.new("RGB", (32, 32), "red").save(path)
        self.folders = [str(self.photos), str(self.archive)]
        self.dbs = []

    def tearDown(self):
        for db in self.dbs:
            db.stop_processing()
            db._local.connections.close()
        self.tmp.cleanup()

    def open_db(self):
        """Open the DB the way Gallery.on_startup does for the current folders."""
        roots, _ = g.gallery_roots_from_settings(self.folders)
        db = g.GalleryDB(str(self.base / "cyberdelia.db"), str(self.base / ".thumbs"), roots)
        self.dbs.append(db)
        return db

    def seed_user_data(self):
        db = self.open_db()
        db.index_tree(force=False)
        conn = db._get_conn()
        archive = ["Archive/x1.png", "Archive/sub/x2.png"]
        db.toggle_favorite(archive[0])
        collection = db.create_collection("Keepers")
        db.add_to_collection(collection["id"], archive)
        db.update_manual_tags(archive, ["keeper"], "add")
        for path in archive:
            db._index_tags(conn, path, {"parameters": "forest, lake"})
        conn.commit()
        return db

    def user_data(self, db):
        conn = db._get_conn()

        def count(sql):
            return conn.execute(sql).fetchone()[0]

        return {
            "archive_files": count("SELECT COUNT(*) FROM files WHERE path LIKE 'Archive/%'"),
            "favorites": count("SELECT COUNT(*) FROM files WHERE favorite=1"),
            "collection_links": count("SELECT COUNT(*) FROM file_collections"),
            "manual_tags": count("SELECT COUNT(*) FROM gallery_manual_file_tags"),
            "tags": count("SELECT COUNT(*) FROM file_tags WHERE file_path LIKE 'Archive/%'"),
        }

    SEEDED = {"archive_files": 2, "favorites": 1, "collection_links": 2, "manual_tags": 2, "tags": 4}

    def test_folder_names_do_not_depend_on_availability(self):
        first = self.base / "a" / "Photos"
        second = self.base / "b" / "Photos"
        second.mkdir(parents=True)
        roots, offline = g.gallery_roots_from_settings([str(first), " ", str(second), ""])
        self.assertEqual(roots, {"Photos": str(first), "Photos_2": str(second)})
        self.assertEqual(offline, {"Photos"})

    def test_offline_root_keeps_user_data_until_it_returns(self):
        db = self.seed_user_data()
        self.assertEqual(self.user_data(db), self.SEEDED)

        unplugged = self.base / "Archive_unplugged"
        self.archive.rename(unplugged)
        db = self.open_db()
        db.index_tree(force=False)
        self.assertEqual(self.user_data(db), self.SEEDED)

        unplugged.rename(self.archive)
        db = self.open_db()
        db.index_tree(force=False)
        self.assertEqual(self.user_data(db), self.SEEDED)

    def test_forced_rescan_with_offline_root_keeps_user_data(self):
        self.seed_user_data()
        self.archive.rename(self.base / "Archive_unplugged")
        db = self.open_db()
        db.index_tree(force=True)
        self.assertEqual(self.user_data(db), self.SEEDED)

    def test_offline_root_keeps_auto_tagger_scores(self):
        # Auto Tagger stores its scores next to Gallery's rows and removes them
        # with a trigger when a files row is deleted (same DDL as Auto Tagger 1.0.7).
        db = self.seed_user_data()
        conn = db._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS auto_tagger_files (
                file_path TEXT PRIMARY KEY, source_mtime REAL DEFAULT 0,
                model_revision TEXT DEFAULT '', status INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS auto_tagger_scores (
                file_path TEXT, tag_name TEXT, category TEXT, score REAL,
                PRIMARY KEY (file_path, tag_name, category));
            CREATE TRIGGER IF NOT EXISTS auto_tagger_cleanup_file
            AFTER DELETE ON files BEGIN
                DELETE FROM auto_tagger_scores WHERE file_path=OLD.path;
                DELETE FROM auto_tagger_files WHERE file_path=OLD.path;
            END;
        """)
        for path in ("Archive/x1.png", "Archive/sub/x2.png"):
            conn.execute("INSERT INTO auto_tagger_files(file_path, status) VALUES (?, 1)", (path,))
            conn.executemany("INSERT INTO auto_tagger_scores VALUES (?, ?, 'general', ?)",
                             [(path, "forest", 0.91), (path, "lake", 0.72)])
        conn.commit()

        def scores(current):
            return current._get_conn().execute("SELECT COUNT(*) FROM auto_tagger_scores").fetchone()[0]

        self.assertEqual(scores(db), 4)
        unplugged = self.base / "Archive_unplugged"
        self.archive.rename(unplugged)
        db = self.open_db()
        db.index_tree(force=False)
        self.assertEqual(scores(db), 4)
        unplugged.rename(self.archive)
        db = self.open_db()
        db.index_tree(force=False)
        self.assertEqual(scores(db), 4)
        self.assertEqual(self.user_data(db), self.SEEDED)

    def test_removing_a_root_in_settings_still_prunes_it(self):
        self.seed_user_data()
        self.folders = [str(self.photos)]
        db = self.open_db()
        db.index_tree(force=False)
        data = self.user_data(db)
        self.assertEqual(data["archive_files"], 0)
        self.assertEqual(data["collection_links"], 0)
        self.assertEqual(data["manual_tags"], 0)

    def test_root_that_disappears_before_cleanup_keeps_records(self):
        db = self.seed_user_data()
        self.archive.rename(self.base / "Archive_unplugged")
        conn = db._get_conn()
        with db.lock:
            pruned = db._prune_missing_folders(conn, {"Archive"})
            conn.commit()
        self.assertEqual(pruned, (0, 0))
        self.assertEqual(self.user_data(db), self.SEEDED)

    def test_folder_with_io_error_is_not_pruned(self):
        db = self.seed_user_data()
        sub = str(self.archive / "sub")
        real_stat = os.stat

        def flaky_stat(path, *args, **kwargs):
            if str(path) == sub:
                raise PermissionError(13, "Permission denied", sub)
            return real_stat(path, *args, **kwargs)

        conn = db._get_conn()
        with patch.object(g.os, "stat", flaky_stat), db.lock:
            pruned = db._prune_missing_folders(conn, {"Archive"})
            conn.commit()
        self.assertEqual(pruned, (0, 0))
        self.assertEqual(self.user_data(db), self.SEEDED)

    def test_deleted_folder_below_present_root_is_still_pruned(self):
        db = self.seed_user_data()
        for child in (self.archive / "sub").iterdir():
            child.unlink()
        (self.archive / "sub").rmdir()
        conn = db._get_conn()
        with db.lock:
            pruned = db._prune_missing_folders(conn, {"Archive"})
            conn.commit()
        self.assertEqual(pruned, (1, 1))
        self.assertEqual(self.user_data(db)["archive_files"], 1)

    def test_watcher_events_from_unmounted_root_are_not_deletions(self):
        db = self.seed_user_data()
        events = [str(self.archive / "x1.png"), str(self.archive / "sub")]
        self.archive.rename(self.base / "Archive_unplugged")
        result = db.sync_changed_paths(events)
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["folders"], 0)
        self.assertEqual(self.user_data(db), self.SEEDED)

    def test_watcher_still_removes_a_really_deleted_file(self):
        db = self.seed_user_data()
        (self.archive / "x1.png").unlink()
        result = db.sync_changed_paths([str(self.archive / "x1.png")])
        self.assertEqual(result["removed"], 1)
        self.assertEqual(self.user_data(db)["archive_files"], 1)

    def test_directory_state_separates_missing_from_unknown(self):
        self.assertEqual(g.directory_state(str(self.archive)), "dir")
        self.assertEqual(g.directory_state(str(self.archive / "x1.png")), "missing")
        self.assertEqual(g.directory_state(str(self.base / "nope")), "missing")
        self.assertEqual(g.directory_state(None), "unknown")
        with patch.object(g.os, "stat", side_effect=OSError(5, "I/O error")):
            self.assertEqual(g.directory_state(str(self.archive)), "unknown")

    @unittest.skipUnless(POSIX_USER, "needs POSIX permissions as a normal user")
    def test_forced_scan_keeps_records_of_unreadable_subfolder(self):
        self.seed_user_data()
        (self.photos / "p1.png").unlink()  # a real deletion elsewhere is still pruned
        sub = self.archive / "sub"
        os.chmod(sub, 0)
        try:
            db = self.open_db()
            db.index_tree(force=True)
        finally:
            os.chmod(sub, 0o755)
        self.assertEqual(self.user_data(db), self.SEEDED)
        photos = db._get_conn().execute("SELECT COUNT(*) FROM files WHERE path LIKE 'Photos/%'").fetchone()[0]
        self.assertEqual(photos, 0)

    @unittest.skipUnless(POSIX_USER, "needs POSIX permissions as a normal user")
    def test_forced_scan_keeps_records_when_root_cannot_be_listed(self):
        self.seed_user_data()
        os.chmod(self.archive, 0)
        try:
            db = self.open_db()
            db.index_tree(force=True)
        finally:
            os.chmod(self.archive, 0o755)
        self.assertEqual(self.user_data(db), self.SEEDED)

    def test_unreadable_folder_mapping_stays_inside_root(self):
        root = str(self.archive)
        error = PermissionError(13, "Permission denied", str(self.archive / "sub"))
        self.assertEqual(g.GalleryDB._unreadable_db_folder("Archive", root, error), "Archive/sub")
        self.assertEqual(g.GalleryDB._unreadable_db_folder("Archive", root, OSError("no name")), "Archive")
        outside = PermissionError(13, "Permission denied", str(self.base))
        self.assertEqual(g.GalleryDB._unreadable_db_folder("Archive", root, outside), "Archive")


if __name__ == "__main__":
    unittest.main()
