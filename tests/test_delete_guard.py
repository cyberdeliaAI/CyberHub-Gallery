"""The whole-library delete scope must confirm the exact count the user saw (T13).

POST /api/delete/start {"scope": "without_metadata"} has no upper limit, so
it requires expected_count. Settings has sent it since Core 1.3.0.
"""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_gallery_performance import g


class Handler:
    def __init__(self, payload):
        self.payload = payload
        self.status = None
        self.body = None

    def read_body_json(self, length):
        return self.payload

    def respond_json(self, body, status=200):
        self.body, self.status = body, status


class DeleteGuardTests(unittest.TestCase):
    def setUp(self):
        self.module = g.GalleryModule(object())
        self.module.db = SimpleNamespace(get_without_metadata_paths=lambda: ["A/one.png", "A/two.png"])
        self.started = []

        def start(paths, label):
            self.started.append((list(paths), label))
            return True

        self.module._start_delete_job = start

    def call(self, payload):
        handler = Handler(payload)
        with patch.object(g, "HAS_TRASH", True):
            self.module._api_delete_start(handler, 0, "application/json")
        return handler

    def test_missing_expected_count_is_rejected(self):
        handler = self.call({"scope": "without_metadata"})
        self.assertEqual(handler.status, 400)
        self.assertEqual(handler.body["count"], 2)
        self.assertEqual(self.started, [])

    def test_invalid_expected_count_is_rejected(self):
        for value in (True, "two", None, [2]):
            with self.subTest(value=value):
                handler = self.call({"scope": "without_metadata", "expected_count": value})
                self.assertEqual(handler.status, 400)
        self.assertEqual(self.started, [])

    def test_changed_count_is_rejected(self):
        handler = self.call({"scope": "without_metadata", "expected_count": 3})
        self.assertEqual(handler.status, 409)
        self.assertEqual(self.started, [])

    def test_matching_count_starts_the_job(self):
        handler = self.call({"scope": "without_metadata", "expected_count": 2})
        self.assertEqual(handler.status, 200)
        self.assertEqual(self.started, [(["A/one.png", "A/two.png"], "Deleting images without metadata")])

    def test_selected_paths_scope_is_unchanged(self):
        handler = self.call({"scope": "paths", "paths": ["A/one.png"]})
        self.assertEqual(handler.status, 200)
        self.assertEqual(self.started[0][0], ["A/one.png"])


if __name__ == "__main__":
    unittest.main()
