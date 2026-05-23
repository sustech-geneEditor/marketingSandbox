"""Tests for the live web event stream bridge."""

from __future__ import annotations

import json
import unittest

from marketing_sandbox import (
    OutputContractInputError,
    WebEventStreamError,
    WebRunEventStream,
    WebSandboxRunner,
    format_json_line_event,
    format_sse_event,
    handle_live_event_stream,
)
from tests.test_web_events import make_action, make_result, make_round, make_strategy
from tests.test_web_runner import (
    SESSION_KEY,
    RecordingBackendFactory,
    make_payload,
    make_session,
)


class StaticResultRunner:
    """Runner fallback that returns a prebuilt SandboxResult."""

    def __init__(self, result):
        self.result = result
        self.calls: list[dict[str, object]] = []

    def run(self, session, *, round_count=None):
        self.calls.append(
            {
                "session": session.session_id,
                "round_count": round_count,
                "credential_source": session.credential_source,
            }
        )
        return self.result


class FailingRunner:
    """Runner that simulates a provider or transport failure."""

    def run(self, session, *, round_count=None):
        raise RuntimeError(f"transport failed with token {SESSION_KEY}")


class ContractFailingRunner:
    """Runner that simulates a guarded model output contract failure."""

    def run(self, session, *, round_count=None):
        raise OutputContractInputError("Decision output contract rejected.")


class FailingRoundSandbox:
    """Sandbox that emits no completed round after progress starts."""

    @property
    def history(self):
        return ()

    def run_round(self):
        raise RuntimeError(f"first round failed with token {SESSION_KEY}")


class FailingRoundRunner:
    """Runner that can build a sandbox but fails inside the first round."""

    def build_sandbox(self, session):
        return FailingRoundSandbox()


class ContractFailingRoundSandbox:
    """Sandbox that fails a streamed round with a contract error."""

    @property
    def history(self):
        return ()

    def run_round(self):
        raise OutputContractInputError("Decision output contract rejected.")


class ContractFailingRoundRunner:
    """Runner that can build a sandbox but fails contract validation in-round."""

    def build_sandbox(self, session):
        return ContractFailingRoundSandbox()


class WebRunEventStreamTests(unittest.TestCase):
    def test_normal_live_runner_streams_round_events_in_order(self):
        factory = RecordingBackendFactory()
        stream = WebRunEventStream(WebSandboxRunner(factory))

        events = stream.collect_events(make_session(), round_count=1)

        event_types = [event["type"] for event in events]
        self.assertEqual(event_types[0], "run_started")
        self.assertEqual(event_types[1], "round_progress")
        self.assertEqual(event_types[-1], "run_completed")
        self.assertIn("round_started", event_types)
        self.assertIn("round_completed", event_types)
        self.assertLess(
            event_types.index("round_progress"),
            event_types.index("round_started"),
        )
        progress_event = events[1]
        self.assertEqual(progress_event["progress"]["stage"], "model_calls")
        self.assertGreater(progress_event["progress"]["expectedModelCalls"], 0)
        self.assertLess(
            event_types.index("round_completed"),
            event_types.index("run_completed"),
        )
        self.assertEqual(len({event["id"] for event in events}), len(events))
        self.assertNotIn(SESSION_KEY, repr(events))
        self.assertTrue(factory.calls)

    def test_boundary_omitted_round_count_uses_session_config(self):
        payload = make_payload(
            search={
                "useUcb": False,
                "rounds": 2,
                "candidatesPerRound": 1,
                "familyIds": [],
            }
        )
        stream = WebRunEventStream(WebSandboxRunner(RecordingBackendFactory()))

        events = stream.collect_events(make_session(payload))

        self.assertEqual(
            len([event for event in events if event["type"] == "round_started"]),
            2,
        )
        self.assertEqual(events[-1]["round"], 2)

    def test_boundary_explicit_round_count_cannot_exceed_config(self):
        stream = WebRunEventStream(StaticResultRunner(make_result()))

        with self.assertRaisesRegex(WebEventStreamError, "cannot exceed"):
            stream.collect_events(make_session(), round_count=3)

    def test_boundary_serializers_emit_jsonl_and_sse_chunks(self):
        event = {
            "id": "demo-0001-run_started",
            "type": "run_started",
            "round": 0,
            "headline": "Run",
            "summary": "Started.",
        }

        json_line = format_json_line_event(event)
        sse_chunk = format_sse_event(event)

        self.assertEqual(json.loads(json_line)["id"], event["id"])
        self.assertTrue(json_line.endswith("\n"))
        self.assertIn("id: demo-0001-run_started\n", sse_chunk)
        self.assertIn("event: run_started\n", sse_chunk)
        self.assertTrue(sse_chunk.endswith("\n\n"))

    def test_special_iter_json_lines_and_sse_use_stream_events(self):
        stream = WebRunEventStream(StaticResultRunner(make_result(rounds=())))
        session = make_session()

        json_line = next(stream.iter_json_lines(session, run_id="jsonstream"))
        sse_chunk = next(stream.iter_sse(session, run_id="ssestream"))

        self.assertEqual(json.loads(json_line)["type"], "run_started")
        self.assertIn("event: run_started\n", sse_chunk)
        self.assertNotIn(SESSION_KEY, json_line + sse_chunk)

    def test_special_sensitive_values_are_redacted_from_stream_events(self):
        strategy = make_strategy(
            actions=(
                make_action(
                    parameters={
                        "content_focus": "proof-led",
                        "session_debug": SESSION_KEY,
                    }
                ),
            )
        )
        result = make_result(rounds=(make_round(strategy=strategy),))
        stream = WebRunEventStream(StaticResultRunner(result))

        serialized = repr(stream.collect_events(make_session(), run_id="redact"))

        self.assertNotIn(SESSION_KEY, serialized)
        self.assertIn("[redacted]", serialized)

    def test_special_response_helper_returns_success_payload(self):
        stream = WebRunEventStream(StaticResultRunner(make_result(rounds=())))

        status, response = handle_live_event_stream(
            make_session(),
            stream,
            run_id="response",
        )

        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["status"], "completed")
        self.assertEqual(response["eventCount"], len(response["events"]))
        self.assertNotIn(SESSION_KEY, repr(response))

    def test_special_ucb_metrics_survive_live_stream_payload(self):
        stream = WebRunEventStream(StaticResultRunner(make_result()))

        events = stream.collect_events(make_session(), run_id="ucbmetrics")

        family_event = next(event for event in events if event["type"] == "family_selected")
        search_event = next(event for event in events if event["type"] == "search_updated")
        self.assertEqual(
            family_event["internalSearch"]["ucbScore"]["display"],
            "cold start infinity",
        )
        self.assertEqual(search_event["search"]["internalMetrics"]["reward"], 0.72)
        self.assertIn(
            "not market outcomes",
            search_event["search"]["internalMetrics"]["metricBoundary"],
        )

    def test_counterexample_fixture_session_is_rejected_before_running(self):
        runner = StaticResultRunner(make_result())
        stream = WebRunEventStream(runner)
        session = make_session(make_payload(source="fixture"))

        status, response = handle_live_event_stream(session, stream)

        self.assertEqual(status, 400)
        self.assertFalse(response["ok"])
        self.assertEqual(response["status"], "invalid_request")
        self.assertEqual(response["issueKind"], "invalid_request")
        self.assertIn("live session", response["message"])
        self.assertFalse(runner.calls)

    def test_counterexample_runner_failure_returns_safe_error_response(self):
        stream = WebRunEventStream(FailingRunner())

        status, response = handle_live_event_stream(make_session(), stream)

        self.assertEqual(status, 500)
        self.assertFalse(response["ok"])
        self.assertEqual(response["status"], "run_failed")
        self.assertEqual(response["issueKind"], "runtime_error")
        self.assertIn("[redacted]", response["message"])
        self.assertNotIn(SESSION_KEY, repr(response))

    def test_counterexample_contract_failure_is_labeled_for_the_web_page(self):
        stream = WebRunEventStream(ContractFailingRunner())

        status, response = handle_live_event_stream(make_session(), stream)

        self.assertEqual(status, 500)
        self.assertFalse(response["ok"])
        self.assertEqual(response["status"], "run_failed")
        self.assertEqual(response["issueKind"], "contract_error")
        self.assertIn("contract rejected", response["message"])

    def test_counterexample_round_failure_still_streams_progress_first(self):
        stream = WebRunEventStream(FailingRoundRunner())
        iterator = stream.iter_events(make_session(), run_id="roundfailure", round_count=1)

        self.assertEqual(next(iterator)["type"], "run_started")
        progress_event = next(iterator)

        self.assertEqual(progress_event["type"], "round_progress")
        self.assertEqual(progress_event["round"], 1)
        self.assertIn("provider calls", progress_event["summary"])
        failure_event = next(iterator)
        self.assertEqual(failure_event["type"], "run_failed")
        self.assertEqual(failure_event["round"], 1)
        self.assertEqual(failure_event["issue"]["kind"], "runtime_error")
        self.assertIn("[redacted]", failure_event["issue"]["message"])
        self.assertNotIn(SESSION_KEY, repr(failure_event))
        with self.assertRaises(StopIteration):
            next(iterator)

    def test_counterexample_round_failure_response_keeps_failure_event(self):
        stream = WebRunEventStream(FailingRoundRunner())

        status, response = handle_live_event_stream(
            make_session(),
            stream,
            run_id="roundfailurepayload",
            round_count=1,
        )

        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["status"], "failed")
        self.assertEqual(response["events"][-1]["type"], "run_failed")
        self.assertNotIn(SESSION_KEY, repr(response))

    def test_counterexample_streamed_contract_failure_is_labeled_contract_error(self):
        stream = WebRunEventStream(ContractFailingRoundRunner())

        events = stream.collect_events(
            make_session(),
            run_id="contractfailure",
            round_count=1,
        )

        self.assertEqual(events[-1]["type"], "run_failed")
        self.assertEqual(events[-1]["issue"]["kind"], "contract_error")
        self.assertIn("contract rejected", events[-1]["issue"]["message"])

    def test_limit_large_completed_result_keeps_unique_stream_event_ids(self):
        rounds = tuple(make_round(index, with_search=False) for index in range(1, 25))
        payload = make_payload(
            search={
                "useUcb": False,
                "rounds": 24,
                "candidatesPerRound": 1,
                "familyIds": [],
            }
        )
        stream = WebRunEventStream(StaticResultRunner(make_result(rounds=rounds)))

        events = stream.collect_events(make_session(payload), run_id="limitrun")

        self.assertEqual(events[-1]["round"], 24)
        self.assertEqual(
            len([event for event in events if event["type"] == "round_started"]),
            24,
        )
        self.assertEqual(len({event["id"] for event in events}), len(events))


if __name__ == "__main__":
    unittest.main()
