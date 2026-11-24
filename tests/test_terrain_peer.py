"""Test client preflight against an original HTTP catalogue."""

from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from adapters.a1_2_10 import terrain_peer


CATALOGUE = "/api/info?planet=earth"


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.images = [b"fixture image 1", b"fixture image 2"]
        self.materials = dict(zip(["garden:mint", "rock:slate"],
                                  (sha256(img).hexdigest() for img in self.images)))
        self.rows = [
            {"id": 0, "key": "original"},
            {"id": 1, "key": "original"},  # Built-in aliases are legal.
            {"id": 2, "key": "innesto_6_garden_mint", "texture": "/pack/ow_innesto_6_garden_mint.png"},
            {"id": 3, "key": "innesto_4_rock_slate", "texture": "/pack/ow_innesto_4_rock_slate.png"},
        ]
        self.requests = []
        self.responses = {row["texture"]: (200, img, {}) for row, img in zip(self.rows[2:], self.images)}
        self.catalogue()
        responses, requests = self.responses, self.requests

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                status, body, headers = responses[self.path]
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server = server
        thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

    def catalogue(self):
        self.responses[CATALOGUE] = (200, json.dumps({"materials": self.rows}).encode(), {})

    def verify(self):
        terrain_peer.verify_peer(*self.server.server_address, self.materials, 2)

    def test_expected_order_is_numeric_independent_of_json_order(self):
        self.rows.reverse()
        self.catalogue()
        self.verify()
        self.assertEqual(self.requests, [CATALOGUE, "/pack/ow_innesto_6_garden_mint.png",
                                         "/pack/ow_innesto_4_rock_slate.png"])

    def test_wrong_missing_or_extra_materials_are_refused_before_texture_fetch(self):
        initial = self.rows
        for rows in (
            initial[:-1],
            [*initial, {"id": 4, "key": "innesto_extra", "texture": "/extra"}],
            [*initial[:2], dict(initial[2], key="ow_innesto_6_garden_mint"), initial[3]],
            [*initial[:2], dict(initial[2], key="INNESTO_6_GARDEN_MINT"), initial[3]],
            [*initial, dict(initial[3], id=4)],
            [*initial, {"id": 4, "key": "original-new"}],
            [*initial, {"id": 4, "key": "OW_INNESTO_4_ROCK_SLATE"}],
            [*initial[:2], dict(initial[2], id=3), dict(initial[3], id=2)],
            [*initial[:2], dict(initial[2], id=6), initial[3]],
            [*initial[:2], dict(initial[2], id=True), initial[3]],
            [*initial[:2], {k: v for k, v in initial[2].items() if k != "id"}, initial[3]],
        ):
            with self.subTest(rows=rows):
                self.rows = rows
                self.catalogue()
                self.requests.clear()
                with self.assertRaises(ValueError):
                    self.verify()
                self.assertEqual(self.requests, [CATALOGUE])

    def test_redirects_and_unexpected_paths_are_never_followed(self):
        for path in ("https://outside.invalid/file", "//outside.invalid/file",
                     "/pack/../other", "/pack/ow_innesto_4_rock_slate.png", "/encoded%2fpath"):
            with self.subTest(path=path):
                self.rows[2]["texture"] = path
                self.catalogue()
                self.requests.clear()
                with self.assertRaises(ValueError):
                    self.verify()
                self.assertEqual(self.requests, [CATALOGUE])
        self.responses[CATALOGUE] = (302, b"", {"Location": "https://outside.invalid"})
        with self.assertRaises(ValueError):
            self.verify()

    def test_corrupt_or_oversized_peer_textures_are_rejected(self):
        for body in (b"modified texture", b"X" * (70 * 1024)):
            with self.subTest(size=len(body)):
                self.responses[self.rows[2]["texture"]] = (200, body, {})
                with self.assertRaises(ValueError):
                    self.verify()

    def test_invalid_json_shape_and_duplicate_members_fail_closed(self):
        for body in (b"{", b"null", b'{"materials":42}', b'{"materials":[]}', b'{"materials":[true]}',
                     b'{"materials":[{"key":"original","id":0,"id":1}]}'):
            with self.subTest(body=body):
                self.responses[CATALOGUE] = (200, body, {})
                with self.assertRaises(ValueError):
                    self.verify()

    def test_shift_in_stock_id_range_is_refused(self):
        self.rows = [*self.rows[:2], {"id": 2, "key": "another_fixture"},
                     dict(self.rows[2], id=3), dict(self.rows[3], id=4)]
        self.catalogue()
        with self.assertRaises(ValueError):
            self.verify()
        self.assertEqual(self.requests, [CATALOGUE])

    def test_stock_count_requires_a_valid_stock_only_catalogue(self):
        with self.assertRaises(ValueError):
            terrain_peer.stock_count(*self.server.server_address)
        self.rows = self.rows[:2]
        self.catalogue()
        self.assertEqual(terrain_peer.stock_count(*self.server.server_address), 2)
        self.rows[1]["id"] = 0
        self.catalogue()
        with self.assertRaises(ValueError):
            terrain_peer.stock_count(*self.server.server_address)

    def test_invalid_private_count_is_refused(self):
        for count in (False, None, 0, -1, 2.0, "2"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                terrain_peer.verify_peer(*self.server.server_address, self.materials, count)

    def test_stalled_response_times_out(self):
        class Stall(BaseHTTPRequestHandler):
            def do_GET(self):
                time.sleep(.3)

            def log_message(self, *_):
                pass

        with ThreadingHTTPServer(("127.0.0.1", 0), Stall) as server:
            server.timeout = .5
            worker = threading.Thread(target=server.handle_request)
            worker.start()
            with patch.object(terrain_peer, "TIMEOUT", .05):
                with self.assertRaisesRegex(ValueError, "peer"):
                    terrain_peer.verify_peer(*server.server_address, self.materials, 2)
            worker.join()


if __name__ == "__main__":
    unittest.main()
