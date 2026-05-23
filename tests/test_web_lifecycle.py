"""Tests for web run stop, archive, restore, and auto-save lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from tempfile import TemporaryDirectory
import unittest

from marketing_sandbox import (
    ARCHIVE_SCHEMA_VERSION,
    RUN_STATUS_ARCHIVED,
    RUN_STATUS_STARTING,
    RUN_STATUS_STOPPED_SAFE,
    SANDBOX_CORE_VERSION,
    SandboxWebEventMapper,
    UCBSearchConfig,
    UCBSearchController,
    WebLifecycleError,
    WebRunEventStream,
    WebRunLifecycleManager,
    WebSandboxRunner,
    handle_api_disconnect_timeout,
    handle_archive_continue_request,
    handle_archive_list_request,
    handle_archive_restore_request,
    handle_archive_save_request,
    handle_stop_request,
)
from tests.test_web_events import make_result
from tests.test_ucb_search_controller import make_family
from tests.test_web_runner import RecordingBackendFactory, make_payload, make_session


SESSION_SECRET = "runner-session-secret"


def fixed_clock():
    return datetime(2026, 5, 23, 1, 2, 3, tzinfo=timezone.utc)


def event(event_id, event_type, round_index=0, **extras):
    payload = {
        "id": event_id,
        "type": event_type,
        "round": round_index,
        "headline": event_type,
        "summary": "summary",
    }
    payload.update(extras)
    return payload


def one_round_events(run_id="run"):
    return SandboxWebEventMapper().map_result(make_result(), run_id=run_id)


class WebRunLifecycleManagerTests(unittest.TestCase):
    def test_normal_stopped_run_archive_saves_and_restores_safe_events(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root, clock=fixed_clock)
            manager.register_run("runA", session_snapshot={"sessionId": "runA"})
            for payload in one_round_events("runA"):
                manager.append_event("runA", payload)
            manager.request_stop("runA")

            summary = manager.save_archive("runA", label="Class demo stop")
            restored = manager.restore_archive(summary["archiveId"])

            self.assertEqual(summary["completedRoundCount"], 1)
            self.assertTrue(restored["resume"]["canContinue"])
            self.assertEqual(restored["archive"]["schemaVersion"], ARCHIVE_SCHEMA_VERSION)
            self.assertEqual(restored["archive"]["sandboxCoreVersion"], SANDBOX_CORE_VERSION)
            self.assertTrue(restored["archive"]["searchState"]["restoresUcbState"])
            self.assertEqual(restored["events"][-1]["type"], "run_completed")

    def test_boundary_pause_playback_does_not_request_live_stop(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run("pauseRun")

            pause = manager.pause_playback("pauseRun")
            state = manager.public_run_state("pauseRun")

            self.assertEqual(pause["control"], "pause_replay")
            self.assertTrue(pause["localSearchContinues"])
            self.assertFalse(state["stopRequested"])
            self.assertEqual(state["status"], RUN_STATUS_STARTING)

    def test_boundary_partial_round_archive_drops_events_after_last_completed_round(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run("partial")
            manager.append_event("partial", event("partial-1", "run_started"))
            manager.append_event("partial", event("partial-2", "round_started", 1))
            manager.append_event("partial", event("partial-3", "strategy_proposed", 1))

            archive = manager.build_archive("partial", status="stopped")

            self.assertEqual([item["type"] for item in archive["playback"]["events"]], ["run_started"])
            self.assertEqual(archive["safeBoundary"]["partialEventsDropped"], 2)
            self.assertFalse(archive["resume"]["canContinue"])

    def test_boundary_empty_archive_store_lists_no_archives(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)

            self.assertEqual(manager.list_archives(), ())
            status, response = handle_archive_list_request(manager)
            self.assertEqual(status, 200)
            self.assertEqual(response["archives"], [])

    def test_special_stop_request_is_honored_between_live_rounds(self):
        payload = make_payload(
            search={
                "useUcb": False,
                "rounds": 3,
                "candidatesPerRound": 1,
                "familyIds": [],
            }
        )
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            stream = WebRunEventStream(
                WebSandboxRunner(RecordingBackendFactory()),
                lifecycle_manager=manager,
            )
            events = []

            for payload_event in stream.iter_events(
                make_session(payload),
                run_id="stoprun",
            ):
                events.append(payload_event)
                if payload_event["type"] == "round_completed":
                    manager.request_stop("stoprun")

            event_types = [item["type"] for item in events]
            self.assertEqual(event_types.count("round_started"), 1)
            self.assertNotIn("run_completed", event_types)
            self.assertEqual(manager.public_run_state("stoprun")["status"], RUN_STATUS_STOPPED_SAFE)

    def test_special_secret_values_are_removed_from_archive_payload(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run(
                "secretRun",
                session_snapshot={
                    "sessionId": "secretRun",
                    "provider": {"apiKey": SESSION_SECRET},
                    "note": f"token {SESSION_SECRET}",
                },
                secret_values=(SESSION_SECRET,),
            )
            manager.append_event(
                "secretRun",
                event(
                    "secret-1",
                    "run_started",
                    debug=f"hidden {SESSION_SECRET}",
                ),
            )

            archive = manager.build_archive("secretRun")

            serialized = json.dumps(archive, ensure_ascii=False)
            self.assertNotIn(SESSION_SECRET, serialized)
            self.assertNotIn("apiKey", serialized)
            self.assertIn("[redacted]", serialized)

    def test_special_framework_route_helpers_cover_stop_save_restore(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run("routeRun")
            for payload in one_round_events("routeRun"):
                manager.append_event("routeRun", payload)

            stop_status, stop_response = handle_stop_request(
                {"runId": "routeRun", "reason": "user_stop"},
                manager,
            )
            save_status, save_response = handle_archive_save_request(
                {"runId": "routeRun", "label": "Saved route"},
                manager,
            )
            restore_status, restore_response = handle_archive_restore_request(
                {"archiveId": save_response["archive"]["archiveId"]},
                manager,
            )
            continue_status, continue_response = handle_archive_continue_request(
                {"archiveId": save_response["archive"]["archiveId"]},
                manager,
            )

            self.assertEqual(stop_status, 200)
            self.assertTrue(stop_response["stopRequested"])
            self.assertEqual(save_status, 200)
            self.assertEqual(restore_status, 200)
            self.assertTrue(restore_response["events"])
            self.assertEqual(continue_status, 200)
            self.assertTrue(continue_response["requiresFreshCredentials"])
            self.assertEqual(continue_response["safeBoundary"]["completedRoundCount"], 1)
            self.assertEqual(continue_response["status"], "resuming")
            self.assertTrue(continue_response["resumePlan"]["restoresUcbState"])

    def test_special_api_disconnect_timeout_auto_archives_latest_safe_boundary(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run("disconnect")
            for payload in one_round_events("disconnect"):
                manager.append_event("disconnect", payload)

            status, response = handle_api_disconnect_timeout(
                {
                    "runId": "disconnect",
                    "disconnectedSeconds": 65,
                    "timeoutSeconds": 60,
                    "message": "provider timed out",
                },
                manager,
            )

            self.assertEqual(status, 200)
            self.assertEqual(response["status"], "auto_archived")
            self.assertEqual(response["archive"]["stopReason"], "api_disconnect_timeout")
            self.assertEqual(len(manager.list_archives()), 1)
            self.assertEqual(manager.public_run_state("disconnect")["status"], RUN_STATUS_ARCHIVED)

    def test_boundary_api_disconnect_waits_before_final_timeout_window(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run("disconnect")

            status, response = handle_api_disconnect_timeout(
                {
                    "runId": "disconnect",
                    "disconnectedSeconds": 59,
                    "timeoutSeconds": 60,
                    "message": "provider timed out",
                },
                manager,
            )

            self.assertEqual(status, 202)
            self.assertEqual(response["status"], "waiting")
            self.assertEqual(len(manager.list_archives()), 0)

    def test_counterexample_path_traversal_archive_id_is_rejected(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)

            with self.assertRaisesRegex(WebLifecycleError, "ASCII token"):
                manager.load_archive("../outside")

    def test_counterexample_duplicate_event_ids_are_rejected_on_load(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            archive = {
                "schemaVersion": ARCHIVE_SCHEMA_VERSION,
                "archiveId": "dupeArchive",
                "createdAt": fixed_clock().isoformat(),
                "label": "dupe",
                "status": "stopped",
                "stopReason": "test",
                "playback": {
                    "source": "live_archive",
                    "events": [
                        event("same", "run_started"),
                        event("same", "round_started", 1),
                    ],
                },
            }
            path = manager.archive_root / "dupeArchive.json"
            path.write_text(json.dumps(archive), encoding="utf-8")

            with self.assertRaisesRegex(WebLifecycleError, "unique"):
                manager.load_archive("dupeArchive")

    def test_counterexample_incompatible_core_archive_is_replayable_but_not_resumable(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run(
                "versionRun",
                session_snapshot={
                    "config": {
                        "search": {
                            "useUcb": True,
                        }
                    }
                },
            )
            for payload in one_round_events("versionRun"):
                manager.append_event("versionRun", payload)
            archive = manager.build_archive("versionRun")
            archive["sandboxCoreVersion"] = "marketing-sandbox-core/v999"
            archive_id = "versionArchive"
            archive["archiveId"] = archive_id
            path = manager.archive_root / f"{archive_id}.json"
            path.write_text(json.dumps(archive), encoding="utf-8")

            restored = manager.restore_archive(archive_id)

            self.assertTrue(restored["resume"]["canReplay"])
            self.assertFalse(restored["resume"]["canContinue"])
            self.assertEqual(
                restored["archive"]["versionCompatibility"]["status"],
                "incompatible_core_replay_only",
            )
            with self.assertRaisesRegex(WebLifecycleError, "core version"):
                manager.prepare_continue_from_archive(archive_id)

    def test_special_archive_search_state_restores_ucb_selection_logic(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run(
                "ucbrestore",
                session_snapshot={
                    "config": {
                        "search": {
                            "useUcb": True,
                        }
                    }
                },
            )
            for payload in one_round_events("ucbrestore"):
                manager.append_event("ucbrestore", payload)

            summary = manager.save_archive("ucbrestore")
            plan = manager.prepare_continue_from_archive(summary["archiveId"])
            controller = UCBSearchController(
                (
                    make_family("trust_risk_reduction"),
                    make_family("trial_value_entry"),
                ),
                UCBSearchConfig(candidate_slots_per_round=1),
            )
            controller.restore_from_archive_search_state(plan["searchState"])
            selection = controller.select(plan["resumePlan"]["nextRoundIndex"])

            self.assertEqual(controller.state_for("trust_risk_reduction").pull_count, 1)
            self.assertEqual(selection.selected_family_ids, ("trial_value_entry",))
            self.assertTrue(plan["searchState"]["ucbStateIncludesCompletedRoundsOnly"])

    def test_limit_many_archives_list_in_reverse_creation_order(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            for index in range(30):
                run_id = f"run{index}"
                manager.register_run(run_id)
                manager.append_event(run_id, event(f"{run_id}-1", "run_started"))
                manager.save_archive(run_id, label=f"Archive {index}")

            archives = manager.list_archives()

            self.assertEqual(len(archives), 30)
            self.assertTrue(all(item["eventCount"] == 1 for item in archives))
            self.assertTrue(all(item["canContinue"] is False for item in archives))

    def test_limit_large_event_archive_keeps_only_completed_round_prefix(self):
        with TemporaryDirectory() as root:
            manager = WebRunLifecycleManager(root)
            manager.register_run("large")
            manager.append_event("large", event("large-start", "run_started"))
            for index in range(1, 40):
                manager.append_event("large", event(f"large-r{index}", "round_completed", index))
            manager.append_event("large", event("large-partial", "round_started", 40))

            archive = manager.build_archive("large")

            self.assertEqual(archive["safeBoundary"]["completedRoundCount"], 39)
            self.assertEqual(archive["safeBoundary"]["partialEventsDropped"], 1)
            self.assertEqual(archive["playback"]["events"][-1]["round"], 39)


if __name__ == "__main__":
    unittest.main()
