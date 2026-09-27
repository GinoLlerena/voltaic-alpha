"""Serving the React UI from the API, and the rate limit that publishing requires.

Owner decision, 26 September 2026: publish the read-only API at the UI's origin,
rate-limited. These tests hold the edges of that: an unknown API path must be a
404 and never the app shell; the UI must not be a way to read files outside its
build directory; the API contract must not change; and the limit must refuse a
flood without refusing a person.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from options_alpha_lab.api.limits import RateLimiter, retry_after_header
from options_alpha_lab.api.server import create_app
from options_alpha_lab.presentation.source import resolve

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "demo" / "h0_demo.db"
SHELL = "<!doctype html><div id=root></div>"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class UiServingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.dist = base / "dist"
        (self.dist / "assets").mkdir(parents=True)
        (self.dist / "index.html").write_text(SHELL)
        (self.dist / "assets" / "app-1a2b.js").write_text("console.log(1)")
        (self.dist / "favicon.svg").write_text("<svg/>")
        (base / "secret.txt").write_text("outside the build")
        self.client = TestClient(create_app(resolve("", DB), ui_dir=self.dist))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_the_root_serves_the_shell_uncached(self) -> None:
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, SHELL)
        self.assertEqual(r.headers["cache-control"], "no-cache")

    def test_a_client_side_route_loads_the_shell(self) -> None:
        for path in ("/decision/abc", "/activity", "/?tour=2"):
            with self.subTest(path):
                self.assertEqual(self.client.get(path).text, SHELL)

    def test_assets_and_root_files_are_served(self) -> None:
        self.assertEqual(self.client.get("/assets/app-1a2b.js").text, "console.log(1)")
        self.assertEqual(self.client.get("/favicon.svg").text, "<svg/>")

    def test_the_api_still_answers_behind_the_ui(self) -> None:
        r = self.client.get("/api/v1/decisions")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/json", r.headers["content-type"])

    def test_an_unknown_api_path_is_a_404_never_the_shell(self) -> None:
        for path in ("/api/v1/no-such-route", "/api", "/api/"):
            with self.subTest(path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 404)
                self.assertNotIn("root", r.text)

    def test_the_ui_cannot_read_outside_its_build(self) -> None:
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
            with self.subTest(path):
                self.assertNotIn("outside the build", self.client.get(path).text)

    def test_the_api_contract_does_not_change(self) -> None:
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertTrue(all(p.startswith("/api/v1/") for p in paths), list(paths))

    def test_writes_are_still_refused_on_the_shell(self) -> None:
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method):
                self.assertEqual(getattr(self.client, method)("/").status_code, 405)

    def test_no_build_means_no_ui(self) -> None:
        client = TestClient(create_app(resolve("", DB), ui_dir=Path(self._tmp.name) / "none"))
        self.assertEqual(client.get("/").status_code, 404)


class RateLimiterTests(unittest.TestCase):
    def test_a_burst_is_admitted_then_refused_with_a_wait(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(burst=3, rate=1.0, clock=clock)
        self.assertEqual([limiter.check("a") for _ in range(3)], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(limiter.check("a"), 1.0)

    def test_tokens_refill_with_time(self) -> None:
        clock = FakeClock()
        limiter = RateLimiter(burst=2, rate=2.0, clock=clock)
        limiter.check("a")
        limiter.check("a")
        self.assertGreater(limiter.check("a"), 0)
        clock.now += 0.5
        self.assertEqual(limiter.check("a"), 0.0)

    def test_clients_do_not_share_a_bucket(self) -> None:
        limiter = RateLimiter(burst=1, rate=0.1, clock=FakeClock())
        self.assertEqual(limiter.check("a"), 0.0)
        self.assertGreater(limiter.check("a"), 0)
        self.assertEqual(limiter.check("b"), 0.0)

    def test_the_defaults_admit_a_person_with_several_tabs(self) -> None:
        # Three tabs of the heaviest page: ~10 resources each on load, then each
        # refreshed every 15 s, for ten minutes.
        clock = FakeClock()
        limiter = RateLimiter(clock=clock)
        refused = sum(limiter.check("me") > 0 for _ in range(30))
        for _ in range(40):
            clock.now += 15
            refused += sum(limiter.check("me") > 0 for _ in range(30))
        self.assertEqual(refused, 0)

    def test_retry_after_is_a_whole_positive_second(self) -> None:
        self.assertEqual(retry_after_header(0.2), "1")
        self.assertEqual(retry_after_header(2.1), "3")


class RateLimitMiddlewareTests(unittest.TestCase):
    def test_a_flood_gets_429_with_retry_after(self) -> None:
        client = TestClient(create_app(resolve("", DB), limiter=RateLimiter(burst=2, rate=0.01)))
        codes = [client.get("/api/v1/decisions").status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        r = client.get("/api/v1/decisions")
        self.assertEqual(r.status_code, 429)
        self.assertGreaterEqual(int(r.headers["retry-after"]), 1)

    def test_static_files_are_not_limited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "index.html").write_text(SHELL)
            client = TestClient(
                create_app(resolve("", DB), ui_dir=dist, limiter=RateLimiter(burst=1, rate=0.01))
            )
            self.assertTrue(all(client.get("/").status_code == 200 for _ in range(5)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
