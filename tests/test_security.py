"""Security and storage-integrity tests: path safety, backups, corrupt data."""

import datetime
import json
import tempfile
import unittest
from pathlib import Path

import craftlib
from craftlib import CraftError, safe_path, load_store, save_store, backup_store
import craft_samples


class TestPathSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="craftsec-"))

    def test_normal_subpath_ok(self):
        p = safe_path(self.tmp, "craft-store.json")
        self.assertEqual(p.parent.resolve(), self.tmp.resolve())

    def test_traversal_dotdot_rejected(self):
        with self.assertRaises(CraftError):
            safe_path(self.tmp, "..", "etc", "passwd")

    def test_deep_traversal_via_filename_rejected(self):
        with self.assertRaises(CraftError):
            safe_path(self.tmp, "../../home/nobody/.ssh/id_rsa")

    def test_absolute_escape_rejected(self):
        with self.assertRaises(CraftError):
            safe_path(self.tmp, "/etc/passwd")

    def test_null_byte_rejected(self):
        with self.assertRaises(CraftError):
            safe_path(self.tmp, "craft\x00store.json")

    def test_symlink_escape_rejected(self):
        # Real target lives OUTSIDE base (a sibling of tmp).
        outside = self.tmp.parent / ("outside-real-" + self.tmp.name)
        outside.mkdir(exist_ok=True)
        link = self.tmp / "link"
        link.symlink_to(outside)
        with self.assertRaises(CraftError):
            safe_path(self.tmp, "link", "kaboom.json")

    def test_base_dir_is_hard_boundary_even_if_base_is_symlink(self):
        real = self.tmp / "realdata"
        real.mkdir(exist_ok=True)
        base_spin = self.tmp / "spin"
        base_spin.symlink_to(real)
        p = safe_path(base_spin, "store.json")
        self.assertTrue(craftlib._safe_child(real, p))

    def test_nonstring_parts_rejected(self):
        with self.assertRaises(CraftError):
            safe_path(self.tmp, 12345)

    def test_backup_dir_outside_base_rejected(self):
        # The backup dir (temp *parent*) sits outside the file's own directory.
        save_store(self.tmp / "store.json", {"version": 1, "wips": [], "stash": []})
        with self.assertRaises(CraftError):
            backup_store(self.tmp / "store.json", backup_dir=self.tmp.parent)

    def test_names_like_url_command_file_content_stay_data_not_logic(self):
        # Craft names are escaped by json.dump; bytes never become executed code.
        evil = "'; import os; os.system('echo pwned'); '"
        store = craft_samples.sample_store()
        store["wips"][0]["name"] = evil
        f = self.tmp / "store.json"
        save_store(f, store)
        loaded = load_store(f)
        self.assertEqual(loaded["wips"][0]["name"], evil)


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="craftstore-"))
        self.file = self.tmp / "craft-store.json"

    def test_load_missing_returns_empty_store(self):
        store = load_store(self.file)
        self.assertEqual(store["wips"], [])
        self.assertEqual(store["stash"], [])

    def test_roundtrip(self):
        store = craft_samples.sample_store()
        save_store(self.file, store)
        loaded = load_store(self.file)
        self.assertEqual(len(loaded["wips"]), 3)
        self.assertEqual(loaded["stash"][1]["dye_lot"], "LT-1188")

    def test_backup_created_on_save(self):
        save_store(self.file, craft_samples.sample_store())
        store2 = craft_samples.sample_store()
        store2["wips"][0]["done_units"] = 125
        save_store(self.file, store2)
        backups = list((self.tmp / "backups").glob("craft-store-*.json"))
        self.assertGreaterEqual(len(backups), 1)
        with open(backups[-1], encoding="utf-8") as fh:
            backup_created = json.load(fh)
        self.assertEqual(backup_created["wips"][0]["done_units"], 120)

    def test_backup_keeps_only_recent_five(self):
        save_store(self.file, {"version": 1, "wips": [], "stash": []})
        for n in range(9):
            self.file.write_text(json.dumps({"version": 1, "wips": [n], "stash": []}), encoding="utf-8")
            backup_store(self.file)
        backups = sorted((self.tmp / "backups").glob("craft-store-*.json"))
        self.assertEqual(len(backups), craftlib.MAX_BACKUPS)

    def test_no_backup_before_first_save(self):
        self.assertIsNone(backup_store(self.file))

    def test_corrupt_json_rejected(self):
        self.file.write_text("{not json at all", encoding="utf-8")
        with self.assertRaises(CraftError):
            load_store(self.file)

    def test_wrong_shape_rejected(self):
        self.file.write_text('{"wips": 42, "stash": []}', encoding="utf-8")
        with self.assertRaises(CraftError):
            load_store(self.file)

    def test_atomic_save_leaves_no_tmp_files(self):
        save_store(self.file, craft_samples.sample_store())
        leftovers = [p for p in self.tmp.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
