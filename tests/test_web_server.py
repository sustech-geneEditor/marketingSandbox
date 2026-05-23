"""Tests for the standard-library local website HTTP server wrapper."""

from __future__ import annotations

import json
import threading
from tempfile import TemporaryDirectory
import unittest
from urllib.request import Request, urlopen

from marketing_sandbox import (
    WebRunEventStream,
    WebRunLifecycleManager,
    WebSandboxApi,
    WebSandboxRunner,
    backend_defaults_from_env,
    create_http_handler,
    create_server,
)
from tests.test_web_runner import RecordingBackendFactory


class WebServerTests(unittest.TestCase):
    def test_normal_backend_defaults_prefer_explicit_arguments(self):
        defaults = backend_defaults_from_env(
            backend_base_url="https://explicit.example/v1",
            backend_api_key="explicit-key",
            getenv=lambda key, default: {
                "MARKETING_SANDBOX_BASE_URL": "https://env.example/v1",
                "MARKETING_SANDBOX_API_KEY": "env-key",
            }.get(key, default),
        )

        self.assertEqual(defaults["base_url"], "https://explicit.example/v1")
        self.assertEqual(defaults["api_key"], "explicit-key")

    def test_boundary_backend_defaults_accept_empty_environment(self):
        defaults = backend_defaults_from_env(getenv=lambda key, default: default)

        self.assertEqual(defaults, {})

    def test_special_create_http_handler_binds_valid_api(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            api = WebSandboxApi(
                lifecycle_manager=manager,
                event_stream=WebRunEventStream(
                    WebSandboxRunner(RecordingBackendFactory()),
                    lifecycle_manager=manager,
                ),
            )

            handler = create_http_handler(api)

            self.assertTrue(issubclass(handler, object))

    def test_special_http_server_answers_archive_route_over_localhost(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            api = WebSandboxApi(
                lifecycle_manager=manager,
                event_stream=WebRunEventStream(
                    WebSandboxRunner(RecordingBackendFactory()),
                    lifecycle_manager=manager,
                ),
            )
            server = create_server(host="127.0.0.1", port=0, api=api)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                port = server.server_address[1]
                request = Request(
                    f"http://127.0.0.1:{port}/api/sandbox/archives",
                    headers={"Accept": "application/json"},
                    method="GET",
                )
                with urlopen(request, timeout=5) as response:  # nosec B310
                    body = json.loads(response.read().decode("utf-8"))
                    cors = response.headers.get("Access-Control-Allow-Origin")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

            self.assertEqual(body["archives"], [])
            self.assertEqual(cors, "*")

    def test_counterexample_create_http_handler_rejects_non_api(self):
        with self.assertRaisesRegex(TypeError, "WebSandboxApi"):
            create_http_handler(object())

    def test_limit_create_server_can_bind_ephemeral_port_and_close(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            api = WebSandboxApi(
                lifecycle_manager=manager,
                event_stream=WebRunEventStream(
                    WebSandboxRunner(RecordingBackendFactory()),
                    lifecycle_manager=manager,
                ),
            )
            server = create_server(host="127.0.0.1", port=0, api=api)
            try:
                self.assertGreater(server.server_address[1], 0)
            finally:
                server.server_close()


if __name__ == "__main__":
    unittest.main()
