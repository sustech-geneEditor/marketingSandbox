"""Tests for the live OpenAI-compatible model backend adapter."""

from __future__ import annotations

import json
import unittest
from urllib.error import URLError

from marketing_sandbox import (
    LLMBackendAuthenticationError,
    LLMBackendCancelledError,
    LLMBackendConfigurationError,
    LLMBackendModelError,
    LLMBackendRateLimitError,
    LLMBackendResponseError,
    LLMBackendTimeoutError,
    LLMBackendTransportError,
    OpenAICompatibleChatBackend,
    WebSandboxRunner,
    make_openai_compatible_backend_factory,
    openai_compatible_backend_factory,
)
from tests.test_web_runner import SESSION_KEY, make_payload, make_session


BACKEND_KEY = "server-side-provider-key"


def completion(text):
    return {"choices": [{"message": {"content": text}}]}


class QueueRequester:
    """Fake completion transport that records each provider request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": json.loads(body.decode("utf-8")),
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("Fake provider response queue is empty.")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def make_backend(requester, **changes):
    config = {
        "base_url": "https://provider.example/v1",
        "api_key": SESSION_KEY,
        "model": "sandbox-model",
        "role": "decision",
        "requester": requester,
        "max_retries": 0,
    }
    config.update(changes)
    return OpenAICompatibleChatBackend(**config)


class OpenAICompatibleChatBackendTests(unittest.TestCase):
    def test_normal_generate_posts_chat_completion_prompt_and_returns_text(self):
        requester = QueueRequester((200, completion('{"ok": true}')))
        backend = make_backend(requester)

        text = backend.generate("Return role JSON only.")

        call = requester.calls[0]
        self.assertEqual(text, '{"ok": true}')
        self.assertEqual(call["url"], "https://provider.example/v1/chat/completions")
        self.assertEqual(call["body"]["model"], "sandbox-model")
        self.assertEqual(call["body"]["messages"][0]["content"], "Return role JSON only.")
        self.assertEqual(call["headers"]["Authorization"], f"Bearer {SESSION_KEY}")
        self.assertNotIn(SESSION_KEY, repr(backend))

    def test_boundary_existing_chat_completion_url_is_not_appended_twice(self):
        requester = QueueRequester((200, completion("ready")))
        backend = make_backend(
            requester,
            base_url="https://provider.example/v1/chat/completions",
        )

        backend.generate("Prompt")

        self.assertEqual(
            requester.calls[0]["url"],
            "https://provider.example/v1/chat/completions",
        )

    def test_boundary_segmented_text_content_is_joined_for_role_parser(self):
        requester = QueueRequester(
            (
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": [
                                    {"type": "text", "text": '{"decision":'},
                                    {"type": "text", "text": '"ready"}'},
                                ]
                            }
                        }
                    ]
                },
            )
        )

        text = make_backend(requester).generate("Prompt")

        self.assertEqual(text, '{"decision":"ready"}')

    def test_boundary_empty_assistant_content_is_rejected(self):
        requester = QueueRequester((200, completion("   ")))

        with self.assertRaisesRegex(LLMBackendResponseError, "empty assistant"):
            make_backend(requester).generate("Prompt")

    def test_special_transient_server_error_retries_then_returns_completion(self):
        sleeps = []
        requester = QueueRequester(
            (503, {"error": {"message": "provider warming"}}),
            (200, completion("recovered")),
        )
        backend = make_backend(
            requester,
            max_retries=1,
            retry_backoff_seconds=0.5,
            sleeper=sleeps.append,
        )

        text = backend.generate("Prompt")

        self.assertEqual(text, "recovered")
        self.assertEqual(len(requester.calls), 2)
        self.assertEqual(sleeps, [0.5])

    def test_special_default_transport_retry_budget_reconnects_eight_times(self):
        sleeps = []
        requester = QueueRequester(*[URLError("host unavailable") for _ in range(9)])
        backend = OpenAICompatibleChatBackend(
            base_url="https://provider.example/v1",
            api_key=SESSION_KEY,
            model="sandbox-model",
            requester=requester,
            sleeper=sleeps.append,
        )

        with self.assertRaisesRegex(LLMBackendTransportError, "could not be reached"):
            backend.generate("Prompt")

        self.assertEqual(len(requester.calls), 9)
        self.assertEqual(sleeps, [])

    def test_special_rate_limit_error_has_its_own_category(self):
        requester = QueueRequester((429, {"error": {"message": "slow down"}}))

        with self.assertRaises(LLMBackendRateLimitError) as captured:
            make_backend(requester).generate("Prompt")

        self.assertEqual(captured.exception.status_code, 429)
        self.assertIn("rate limit", str(captured.exception))

    def test_special_unreachable_base_url_becomes_transport_error(self):
        requester = QueueRequester(URLError("host unavailable"))

        with self.assertRaisesRegex(LLMBackendTransportError, "could not be reached"):
            make_backend(requester).generate("Prompt")

    def test_special_timeout_error_redacts_secret_from_failure(self):
        requester = QueueRequester(TimeoutError(f"provider timeout {SESSION_KEY}"))

        with self.assertRaises(LLMBackendTimeoutError) as captured:
            make_backend(requester).generate("Prompt")

        self.assertIn("[redacted]", str(captured.exception))
        self.assertNotIn(SESSION_KEY, str(captured.exception))

    def test_special_cancellation_stops_before_first_provider_request(self):
        requester = QueueRequester((200, completion("should not happen")))
        backend = make_backend(requester, cancellation_check=lambda: True)

        with self.assertRaisesRegex(LLMBackendCancelledError, "cancelled"):
            backend.generate("Prompt")

        self.assertEqual(requester.calls, [])

    def test_counterexample_invalid_key_response_is_classified_and_redacted(self):
        requester = QueueRequester(
            (401, {"error": {"message": f"bad API key {SESSION_KEY}"}})
        )

        with self.assertRaises(LLMBackendAuthenticationError) as captured:
            make_backend(requester).generate("Prompt")

        self.assertEqual(captured.exception.status_code, 401)
        self.assertIn("[redacted]", str(captured.exception))
        self.assertNotIn(SESSION_KEY, str(captured.exception))

    def test_counterexample_missing_model_response_is_classified(self):
        requester = QueueRequester((404, {"error": {"message": "model missing"}}))

        with self.assertRaises(LLMBackendModelError) as captured:
            make_backend(requester).generate("Prompt")

        self.assertEqual(captured.exception.status_code, 404)
        self.assertIn("model", str(captured.exception))

    def test_limit_large_prompt_stays_in_request_without_secret_leaking_to_repr(self):
        requester = QueueRequester((200, completion("bounded output")))
        backend = make_backend(requester)
        prompt = "Known product facts. " * 8000

        text = backend.generate(prompt)

        self.assertEqual(text, "bounded output")
        self.assertEqual(requester.calls[0]["body"]["messages"][0]["content"], prompt)
        self.assertNotIn(SESSION_KEY, repr(requester.calls[0]["body"]))


class OpenAICompatibleFactoryTests(unittest.TestCase):
    def test_normal_factory_uses_session_key_and_supplied_role_model(self):
        requester = QueueRequester((200, completion("decision json")))
        backend = openai_compatible_backend_factory(
            role="decision",
            model="planner-model",
            session=make_session(),
            persona=None,
            requester=requester,
            max_retries=0,
        )

        backend.generate("Prompt")

        self.assertEqual(backend.model, "planner-model")
        self.assertEqual(backend.role, "decision")
        self.assertEqual(
            requester.calls[0]["headers"]["Authorization"],
            f"Bearer {SESSION_KEY}",
        )

    def test_boundary_bound_factory_uses_backend_defaults_for_server_credentials(self):
        payload = make_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": "",
                "apiKey": "",
                "useBackendDefaults": True,
                "defaultModel": "server-route",
            }
        )
        requester = QueueRequester((200, completion("critic json")))
        factory = make_openai_compatible_backend_factory(
            backend_defaults={
                "base_url": "https://server.example/v1",
                "api_key": BACKEND_KEY,
            },
            requester=requester,
            max_retries=0,
        )

        backend = factory(
            role="critic",
            model="server-route",
            session=make_session(payload),
            persona=None,
        )
        backend.generate("Prompt")

        self.assertEqual(
            requester.calls[0]["url"],
            "https://server.example/v1/chat/completions",
        )
        self.assertEqual(
            requester.calls[0]["headers"]["Authorization"],
            f"Bearer {BACKEND_KEY}",
        )
        self.assertNotIn(BACKEND_KEY, repr(backend))

    def test_special_default_web_runner_assembles_real_backend_routes(self):
        payload = make_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": "https://provider.example/v1",
                "apiKey": SESSION_KEY,
                "useBackendDefaults": False,
                "defaultModel": "",
            },
            models={
                "decision": "planner-model",
                "consumers": "consumer-model",
                "synthesizer": "summary-model",
                "critic": "critic-model",
            },
        )

        sandbox = WebSandboxRunner().build_sandbox(make_session(payload))

        self.assertIsInstance(
            sandbox.decision_agent._backend,  # noqa: SLF001 - assembly contract.
            OpenAICompatibleChatBackend,
        )
        self.assertEqual(
            sandbox.decision_agent._backend.model,  # noqa: SLF001
            "planner-model",
        )
        self.assertEqual(
            sandbox.feedback_synthesizer._backend.model,  # noqa: SLF001
            "summary-model",
        )
        self.assertEqual(
            sandbox.consumer_agents[0]._backend.model,  # noqa: SLF001
            "consumer-model",
        )

    def test_counterexample_factory_rejects_fixture_sessions(self):
        fixture_session = make_session(make_payload(source="fixture"))

        with self.assertRaisesRegex(LLMBackendConfigurationError, "live"):
            openai_compatible_backend_factory(
                role="decision",
                model="fixture-route",
                session=fixture_session,
                persona=None,
            )

    def test_counterexample_factory_needs_defaults_when_session_selects_them(self):
        payload = make_payload(
            provider={
                "id": "openai-compatible",
                "baseUrl": "",
                "apiKey": "",
                "useBackendDefaults": True,
                "defaultModel": "server-route",
            }
        )

        with self.assertRaisesRegex(LLMBackendConfigurationError, "base_url"):
            openai_compatible_backend_factory(
                role="decision",
                model="server-route",
                session=make_session(payload),
                persona=None,
            )


if __name__ == "__main__":
    unittest.main()
