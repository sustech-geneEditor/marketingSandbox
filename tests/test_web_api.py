"""Tests for the local website API route layer."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from tempfile import TemporaryDirectory
import unittest

from marketing_sandbox import (
    WebRunEventStream,
    WebRunLifecycleManager,
    WebSandboxApi,
    WebSandboxRunner,
)
from tests.test_web_runner import RecordingBackendFactory, SESSION_KEY, make_payload


def json_body(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def response_json(response):
    return json.loads(response.body.decode("utf-8"))


def one_round_payload(**changes):
    payload = make_payload(
        search={
            "useUcb": False,
            "rounds": 1,
            "candidatesPerRound": 1,
            "familyIds": [],
        }
    )
    payload.update(changes)
    return payload


def event(event_id, event_type="run_started", round_index=0):
    return {
        "id": event_id,
        "type": event_type,
        "round": round_index,
        "headline": event_type,
        "summary": "summary",
    }


def fixed_clock():
    return datetime(2026, 5, 23, 1, 2, 3, tzinfo=timezone.utc)


def fake_model_requester(url, headers, body, timeout):
    return 200, {"choices": [{"message": {"content": "ok"}}]}


def make_api(root, *, probe_requester=None, model_requester=fake_model_requester):
    manager = WebRunLifecycleManager(root, clock=fixed_clock)
    runner = WebSandboxRunner(RecordingBackendFactory())
    stream = WebRunEventStream(runner, lifecycle_manager=manager)
    return WebSandboxApi(
        lifecycle_manager=manager,
        event_stream=stream,
        provider_probe_requester=probe_requester,
        provider_model_requester=model_requester,
    )


class WebSandboxApiTests(unittest.TestCase):
    def test_normal_live_events_json_route_runs_fake_sandbox_and_redacts_key(self):
        with TemporaryDirectory() as root:
            api = make_api(root)

            response = api.handle(
                "POST",
                "/api/sandbox/live-events",
                json_body(one_round_payload(runId="runA")),
                headers={"Accept": "application/json"},
            )
            payload = response_json(response)

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertGreater(payload["eventCount"], 0)
            self.assertEqual(payload["events"][0]["type"], "run_started")
            self.assertNotIn(SESSION_KEY, json.dumps(payload, ensure_ascii=False))

    def test_boundary_live_events_sse_streams_encoded_chunks(self):
        with TemporaryDirectory() as root:
            api = make_api(root)

            response = api.handle(
                "POST",
                "/api/sandbox/live-events",
                json_body(one_round_payload()),
                headers={"Accept": "text/event-stream"},
            )
            text = b"".join(response.chunks or ()).decode("utf-8")

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.is_streaming)
            self.assertIn("Content-Type", response.headers)
            self.assertIn("event: run_started", text)
            self.assertIn("data:", text)

    def test_boundary_options_request_returns_cors_headers(self):
        with TemporaryDirectory() as root:
            api = make_api(root)

            response = api.handle("OPTIONS", "/api/sandbox/archives")

            self.assertEqual(response.status_code, 204)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"], "*")
            self.assertIn("POST", response.headers["Access-Control-Allow-Methods"])

    def test_boundary_empty_archive_store_lists_no_archives(self):
        with TemporaryDirectory() as root:
            api = make_api(root)

            response = api.handle("GET", "/api/sandbox/archives")
            payload = response_json(response)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["archives"], [])

    def test_boundary_body_size_limit_returns_413(self):
        with TemporaryDirectory() as root:
            api = WebSandboxApi(
                lifecycle_manager=WebRunLifecycleManager(root),
                event_stream=WebRunEventStream(
                    WebSandboxRunner(RecordingBackendFactory()),
                    lifecycle_manager=WebRunLifecycleManager(root),
                ),
                max_body_bytes=4,
            )

            response = api.handle("POST", "/api/sandbox/provider-check", b"12345")
            payload = response_json(response)

            self.assertEqual(response.status_code, 413)
            self.assertEqual(payload["status"], "body_too_large")

    def test_special_path_stop_route_marks_registered_run(self):
        with TemporaryDirectory() as root:
            api = make_api(root)
            api.lifecycle_manager.register_run("stopRun")

            response = api.handle(
                "POST",
                "/api/sandbox/runs/stopRun/stop",
                b"",
            )
            payload = response_json(response)

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["stopRequested"])
            self.assertEqual(payload["runId"], "stopRun")

    def test_special_frontend_stop_route_accepts_body_run_id(self):
        with TemporaryDirectory() as root:
            api = make_api(root)
            api.lifecycle_manager.register_run("frontendStop")

            response = api.handle(
                "POST",
                "/api/sandbox/runs/stop",
                json_body({"runId": "frontendStop", "reason": "user_stop"}),
            )
            payload = response_json(response)

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], "stop_requested")

    def test_special_archive_save_list_and_restore_roundtrip(self):
        with TemporaryDirectory() as root:
            api = make_api(root)
            api.handle(
                "POST",
                "/api/sandbox/live-events",
                json_body(one_round_payload()),
                headers={"Accept": "application/json", "X-Sandbox-Run-Id": "archiveRun"},
            )

            save_response = api.handle(
                "POST",
                "/api/sandbox/archives",
                json_body({"runId": "archiveRun", "label": "Saved API route"}),
            )
            archive_id = response_json(save_response)["archive"]["archiveId"]
            list_response = api.handle("GET", "/api/sandbox/archives")
            restore_response = api.handle("GET", f"/api/sandbox/archives/{archive_id}")
            restored = response_json(restore_response)

            self.assertEqual(save_response.status_code, 200)
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(response_json(list_response)["archives"][0]["archiveId"], archive_id)
            self.assertEqual(restore_response.status_code, 200)
            self.assertEqual(restored["archive"]["archiveId"], archive_id)
            self.assertTrue(restored["events"])
            self.assertNotIn(SESSION_KEY, json.dumps(restored, ensure_ascii=False))

    def test_special_archive_resume_route_returns_safe_continuation_plan(self):
        with TemporaryDirectory() as root:
            api = make_api(root)
            api.handle(
                "POST",
                "/api/sandbox/live-events",
                json_body(one_round_payload()),
                headers={"Accept": "application/json", "X-Sandbox-Run-Id": "resumeRun"},
            )
            save_response = api.handle(
                "POST",
                "/api/sandbox/archives",
                json_body({"runId": "resumeRun"}),
            )
            archive_id = response_json(save_response)["archive"]["archiveId"]

            response = api.handle(
                "POST",
                f"/api/sandbox/archives/{archive_id}/resume",
                b"",
            )
            payload = response_json(response)

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["requiresFreshCredentials"])
            self.assertEqual(payload["archiveId"], archive_id)
            self.assertGreater(payload["safeBoundary"]["completedRoundCount"], 0)

    def test_special_provider_check_uses_probe_requester_and_redacts_key(self):
        calls = []
        model_calls = []

        def requester(url, headers, timeout):
            calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
            return 200

        def model_requester(url, headers, body, timeout):
            model_calls.append(
                {
                    "url": url,
                    "headers": dict(headers),
                    "body": json.loads(body.decode("utf-8")),
                    "timeout": timeout,
                }
            )
            return 200, {"choices": [{"message": {"content": "ok"}}]}

        with TemporaryDirectory() as root:
            api = make_api(
                root,
                probe_requester=requester,
                model_requester=model_requester,
            )
            response = api.handle(
                "POST",
                "/api/sandbox/provider-check",
                json_body(
                    {
                        "provider": {
                            "id": "openai-compatible",
                            "baseUrl": "https://provider.example/v1",
                            "apiKey": "provider-secret",
                            "useBackendDefaults": False,
                            "defaultModel": "tiny-check-model",
                        },
                        "models": {},
                    }
                ),
            )
            payload = response_json(response)

            self.assertEqual(response.status_code, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["modelCheck"]["modelStatus"], "callable")
            self.assertEqual(calls[0]["url"], "https://provider.example/v1/models")
            self.assertEqual(
                model_calls[0]["url"],
                "https://provider.example/v1/chat/completions",
            )
            self.assertEqual(model_calls[0]["body"]["model"], "tiny-check-model")
            self.assertNotIn("provider-secret", response.body.decode("utf-8"))

    def test_special_provider_check_reports_model_route_failure_safely(self):
        def requester(url, headers, timeout):
            return 200

        def model_requester(url, headers, body, timeout):
            return 404, {"error": {"message": "missing model for provider-secret"}}

        with TemporaryDirectory() as root:
            api = make_api(
                root,
                probe_requester=requester,
                model_requester=model_requester,
            )

            response = api.handle(
                "POST",
                "/api/sandbox/provider-check",
                json_body(
                    {
                        "provider": {
                            "id": "openai-compatible",
                            "baseUrl": "https://provider.example/v1",
                            "apiKey": "provider-secret",
                            "useBackendDefaults": False,
                            "defaultModel": "missing-model",
                        },
                        "models": {},
                    }
                ),
            )
            payload = response_json(response)

            self.assertEqual(response.status_code, 502)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["modelStatus"], "not_callable")
            self.assertNotIn("provider-secret", response.body.decode("utf-8"))

    def test_special_disconnect_timeout_route_auto_archives_safe_run(self):
        with TemporaryDirectory() as root:
            api = make_api(root)
            api.lifecycle_manager.register_run("disconnectRun")
            api.lifecycle_manager.append_event("disconnectRun", event("disconnect-start"))

            response = api.handle(
                "POST",
                "/api/sandbox/runs/disconnectRun/api-disconnect-timeout",
                json_body({"disconnectedSeconds": 61, "timeoutSeconds": 60}),
            )
            payload = response_json(response)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["status"], "auto_archived")
            self.assertEqual(len(api.lifecycle_manager.list_archives()), 1)

    def test_counterexample_unknown_route_returns_404(self):
        with TemporaryDirectory() as root:
            api = make_api(root)

            response = api.handle("GET", "/api/sandbox/nope")
            payload = response_json(response)

            self.assertEqual(response.status_code, 404)
            self.assertEqual(payload["status"], "not_found")

    def test_counterexample_malformed_json_returns_400(self):
        with TemporaryDirectory() as root:
            api = make_api(root)

            response = api.handle("POST", "/api/sandbox/provider-check", b"{bad")
            payload = response_json(response)

            self.assertEqual(response.status_code, 400)
            self.assertEqual(payload["status"], "invalid_request")

    def test_limit_many_archives_stay_listable_through_api(self):
        with TemporaryDirectory() as root:
            api = make_api(root)
            for index in range(25):
                run_id = f"run{index}"
                api.lifecycle_manager.register_run(run_id)
                api.lifecycle_manager.append_event(run_id, event(f"{run_id}-start"))
                api.lifecycle_manager.save_archive(run_id, label=f"Archive {index}")

            response = api.handle("GET", "/api/sandbox/archives")
            payload = response_json(response)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(payload["archives"]), 25)
            self.assertTrue(all("archiveId" in item for item in payload["archives"]))


if __name__ == "__main__":
    unittest.main()
