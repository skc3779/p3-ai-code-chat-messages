import tempfile
import unittest
from pathlib import Path

from src.large_context_cache import LargeContextCache


class LargeContextCacheTests(unittest.TestCase):
    def test_artifact_integrity_and_corruption_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = LargeContextCache(Path(directory), "job")
            cache.save_artifact("map", "abc", "summary", {"chunk": 1})
            self.assertEqual(cache.load_artifact("map", "abc"), "summary")
            (cache.maps / "abc.md").write_text("tampered", encoding="utf-8")
            self.assertIsNone(cache.load_artifact("map", "abc"))

    def test_corrupt_metadata_json_invalidates_only_that_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = LargeContextCache(Path(directory), "job")
            cache.save_artifact("map", "good", "good summary", {})
            cache.save_artifact("map", "bad", "bad summary", {})
            (cache.maps / "bad.json").write_text("{broken", encoding="utf-8")
            self.assertEqual(cache.load_artifact("map", "good"), "good summary")
            self.assertIsNone(cache.load_artifact("map", "bad"))

    def test_final_requires_matching_inventory_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = LargeContextCache(Path(directory), "job")
            cache.save_final("answer", "inventory-a")
            self.assertEqual(cache.load_final("inventory-a"), "answer")
            self.assertIsNone(cache.load_final("inventory-b"))


if __name__ == "__main__":
    unittest.main()
