"""Tests for the website run-config boundary and safe provider checks."""

from __future__ import annotations

import unittest

from marketing_sandbox import (
    WebRunConfig,
    WebRunConfigError,
    WebRunSession,
    handle_api_connection_test,
    probe_api_connection,
)


SESSION_KEY = "session-secret-key"


def make_live_payload(**changes):
    payload = {
        "source": "live",
        "provider": {
            "id": "openai-compatible",
            "baseUrl": "https://provider.example/v1",
            "apiKey": SESSION_KEY,
            "useBackendDefaults": False,
            "defaultModel": "reasoning-model",
        },
        "models": {
            "decision": "",
            "consumers": "",
            "synthesizer": "",
            "critic": "",
        },
        "product": {
            "name": "Classroom product",
            "brand": "Known proof stays bounded.",
            "facts": "Portable product with a verified trial pack.",
            "goal": "Find a marketing path that survives competitor pressure.",
        },
        "personaIds": ["value-pragmatist", "trust-first"],
        "scenarioId": "competitor-pressure",
        "actionCategories": ["Product", "Price", "Promotion"],
        "search": {
            "useUcb": True,
            "rounds": 4,
            "candidatesPerRound": 1,
            "familyIds": ["trial_value_entry", "trust_risk_reduction"],
        },
    }
    payload.update(changes)
    return payload


class WebSessionTests(unittest.TestCase):
    def test_normal_live_session_splits_frontend_config_from_session_secret(self):
        session = WebRunSession.from_frontend_payload("demo-session", make_live_payload())

        public_snapshot = session.public_snapshot()
        serialized_snapshot = repr(public_snapshot)

        self.assertEqual(session.credential_source, "session_key")
        self.assertEqual(session.config.provider.provider_id, "openai-compatible")
        self.assertNotIn(SESSION_KEY, repr(session))
        self.assertNotIn(SESSION_KEY, serialized_snapshot)

    def test_boundary_fixture_session_ignores_temporary_key_and_empty_route(self):
        payload = make_live_payload(
            source="fixture",
            provider={
                "id": "openai-compatible",
                "apiKey": SESSION_KEY,
                "baseUrl": "",
                "useBackendDefaults": False,
                "defaultModel": "",
            },
            models={},
        )

        session = WebRunSession.from_frontend_payload("fixture-session", payload)

        self.assertEqual(session.credential_source, "not_required")
        self.assertFalse(session.has_session_api_key)
        self.assertNotIn(SESSION_KEY, repr(session.public_snapshot()))

    def test_boundary_backend_defaults_allow_live_session_without_browser_key(self):
        payload = make_live_payload(
            provider={
                "id": "deepseek-compatible",
                "baseUrl": "",
                "apiKey": "",
                "useBackendDefaults": True,
                "defaultModel": "deepseek-router",
            }
        )

        session = WebRunSession.from_frontend_payload("backend-defaults", payload)

        self.assertEqual(session.credential_source, "backend_defaults")
        self.assertEqual(session.config.provider.provider_id, "deepseek-compatible")
        self.assertFalse(session.has_session_api_key)

    def test_boundary_config_accepts_documented_search_limits(self):
        payload = make_live_payload()
        payload["search"] = {
            "useUcb": False,
            "rounds": 24,
            "candidatesPerRound": 4,
            "familyIds": [],
        }

        config = WebRunConfig.from_frontend_payload(payload)

        self.assertEqual(config.rounds, 24)
        self.assertEqual(config.candidates_per_round, 4)
        self.assertEqual(config.family_ids, ())

    def test_special_role_routes_replace_default_model_route(self):
        payload = make_live_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": "https://provider.example/v1",
                "apiKey": SESSION_KEY,
                "useBackendDefaults": False,
                "defaultModel": "",
            },
            models={
                "decision": "planner",
                "consumers": "persona-model",
                "synthesizer": "summary-model",
                "critic": "critic-model",
            },
        )

        config = WebRunConfig.from_frontend_payload(payload)

        self.assertTrue(config.provider.has_model_route)
        self.assertEqual(config.provider.role_models["critic"], "critic-model")

    def test_special_connection_handler_checks_models_endpoint_without_echoing_key(self):
        seen_request = {}

        def requester(url, headers, timeout):
            seen_request["url"] = url
            seen_request["headers"] = headers
            seen_request["timeout"] = timeout
            return 204

        status, response = handle_api_connection_test(
            make_live_payload(),
            requester=requester,
        )

        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "connected")
        self.assertEqual(seen_request["url"], "https://provider.example/v1/models")
        self.assertEqual(seen_request["headers"]["Authorization"], f"Bearer {SESSION_KEY}")
        self.assertNotIn(SESSION_KEY, repr(response))

    def test_special_connection_probe_redacts_session_key_from_transport_failure(self):
        provider = WebRunConfig.from_frontend_payload(make_live_payload()).provider

        def requester(url, headers, timeout):
            raise RuntimeError(f"bad bearer {SESSION_KEY}")

        result = probe_api_connection(
            provider,
            session_api_key=SESSION_KEY,
            requester=requester,
        )

        self.assertFalse(result.ok)
        self.assertIn("[redacted]", result.message)
        self.assertNotIn(SESSION_KEY, result.message)

    def test_special_backend_default_probe_redacts_default_key_from_transport_failure(self):
        default_key = "backend-secret-key"
        payload = make_live_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": "",
                "apiKey": "",
                "useBackendDefaults": True,
                "defaultModel": "backend-routed-model",
            }
        )
        provider = WebRunConfig.from_frontend_payload(payload).provider

        def requester(url, headers, timeout):
            raise RuntimeError(f"backend failure {default_key}")

        result = probe_api_connection(
            provider,
            backend_defaults={
                "base_url": "https://backend.example/v1",
                "api_key": default_key,
            },
            requester=requester,
        )

        self.assertEqual(result.models_url, "https://backend.example/v1/models")
        self.assertNotIn(default_key, result.message)

    def test_counterexample_rejects_unrecognized_run_source(self):
        payload = make_live_payload(source="desktop")

        with self.assertRaisesRegex(WebRunConfigError, "source"):
            WebRunConfig.from_frontend_payload(payload)

    def test_counterexample_rejects_live_session_without_any_key_source(self):
        payload = make_live_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": "https://provider.example/v1",
                "apiKey": "",
                "useBackendDefaults": False,
                "defaultModel": "reasoning-model",
            }
        )

        with self.assertRaisesRegex(WebRunConfigError, "session API key"):
            WebRunSession.from_frontend_payload("missing-key", payload)

    def test_counterexample_handler_rejects_secret_bearing_url_safely(self):
        payload = make_live_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": f"https://user:{SESSION_KEY}@provider.example/v1",
                "apiKey": SESSION_KEY,
                "useBackendDefaults": False,
                "defaultModel": "reasoning-model",
            }
        )

        status, response = handle_api_connection_test(payload)

        self.assertEqual(status, 400)
        self.assertNotIn(SESSION_KEY, repr(response))
        self.assertIn("credentials", response["message"])

    def test_limit_snapshot_keeps_large_config_safe_for_future_archives(self):
        payload = make_live_payload()
        payload["personaIds"] = [f"persona-{index}" for index in range(80)]
        payload["search"]["familyIds"] = [f"family_{index}" for index in range(60)]
        payload["actionCategories"] = [
            "Positioning",
            "Product",
            "Price",
            "Channel",
            "Promotion",
            "Retention",
        ]

        snapshot = WebRunSession.from_frontend_payload(
            "large-session",
            payload,
        ).public_snapshot()

        self.assertEqual(len(snapshot["config"]["personaIds"]), 80)
        self.assertEqual(len(snapshot["config"]["search"]["familyIds"]), 60)
        self.assertNotIn(SESSION_KEY, repr(snapshot))


if __name__ == "__main__":
    unittest.main()
