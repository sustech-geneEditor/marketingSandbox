"""Run-stop and archive lifecycle helpers for the web sandbox."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .web_events import WEB_EVENT_CONTRACT_VERSION


ARCHIVE_SCHEMA_VERSION = "marketing-sandbox-archive/v1"
SANDBOX_CORE_VERSION = "marketing-sandbox-core/v1"
ARCHIVE_FORMAT_VERSION = 2
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
ARCHIVE_ID_PATTERN = RUN_ID_PATTERN
SAFE_BOUNDARY_EVENT_TYPES = frozenset({"round_completed", "run_completed"})
RUN_STARTED_EVENT_TYPE = "run_started"
RUN_STATUS_IDLE = "idle"
RUN_STATUS_CHECKING_PROVIDER = "checking_provider"
RUN_STATUS_STARTING = "starting"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_STOP_REQUESTED = "stop_requested"
RUN_STATUS_STOPPED_SAFE = "stopped_safe"
RUN_STATUS_ARCHIVED = "archived"
RUN_STATUS_RESUMING = "resuming"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUSES = frozenset(
    {
        RUN_STATUS_IDLE,
        RUN_STATUS_CHECKING_PROVIDER,
        RUN_STATUS_STARTING,
        RUN_STATUS_RUNNING,
        RUN_STATUS_STOP_REQUESTED,
        RUN_STATUS_STOPPED_SAFE,
        RUN_STATUS_ARCHIVED,
        RUN_STATUS_RESUMING,
        RUN_STATUS_COMPLETED,
        RUN_STATUS_FAILED,
    }
)


class WebLifecycleError(Exception):
    """Raised when a web run lifecycle or archive operation is invalid."""


class WebRunLifecycleManager:
    """Manage web run stop signals and local safe-boundary archives.

    This class deliberately lives outside ``MarketingSandbox``. Pause is a UI
    playback concern; stop is a local live-search control signal checked between
    complete rounds. Archives keep only public snapshots and safe completed
    event prefixes, so a half round cannot pollute later UCB state.
    """

    def __init__(
        self,
        archive_root: str | Path,
        *,
        clock: Any | None = None,
    ) -> None:
        self.archive_root = Path(archive_root)
        self.archive_root.mkdir(parents=True, exist_ok=True)
        if not self.archive_root.is_dir():
            raise WebLifecycleError("archive_root must be a directory.")
        self._clock = clock or _utc_now
        self._runs: dict[str, dict[str, Any]] = {}

    def describe_control_semantics(self) -> dict[str, Any]:
        """Return the public distinction between replay pause and live stop."""

        return {
            "pause": {
                "kind": "replay_pause",
                "localSearchContinues": True,
                "safeBoundaryChanged": False,
                "description": "Pause only freezes the browser playback cursor.",
            },
            "stop": {
                "kind": "live_search_stop",
                "localSearchContinues": False,
                "safeBoundaryChanged": True,
                "description": (
                    "Stop asks the local runner to halt before dispatching the "
                    "next round and then offers archive choices."
                ),
            },
        }

    def register_run(
        self,
        run_id: str,
        *,
        session_snapshot: Mapping[str, Any] | None = None,
        secret_values: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Create or refresh a run lifecycle state without exposing secrets."""

        run_id = self._require_token(run_id, "run_id")
        state = self._runs.setdefault(
            run_id,
            {
                "runId": run_id,
                "status": RUN_STATUS_STARTING,
                "stopRequested": False,
                "stopReason": "",
                "events": [],
                "sessionSnapshot": {},
                "secretValues": (),
                "createdAt": self._timestamp(),
                "updatedAt": self._timestamp(),
            },
        )
        state["sessionSnapshot"] = self._sanitize(
            dict(session_snapshot or state.get("sessionSnapshot") or {}),
            secret_values,
        )
        state["secretValues"] = tuple(
            item for item in tuple(secret_values) + tuple(state.get("secretValues", ())) if item
        )
        state["updatedAt"] = self._timestamp()
        return self.public_run_state(run_id)

    def pause_playback(self, run_id: str) -> dict[str, Any]:
        """Describe a playback pause without changing live stop state."""

        run_id = self._require_token(run_id, "run_id")
        state = self._runs.get(run_id)
        return {
            "ok": True,
            "runId": run_id,
            "control": "pause_replay",
            "localSearchContinues": True,
            "stopRequested": bool(state and state.get("stopRequested")),
        }

    def request_stop(self, run_id: str, *, reason: str = "user_stop") -> dict[str, Any]:
        """Request local live-search stop at the next safe round boundary."""

        state = self._require_run_state(run_id)
        state["stopRequested"] = True
        state["stopReason"] = self._require_text(reason, "stop reason")
        if state["status"] in {RUN_STATUS_STARTING, RUN_STATUS_RUNNING}:
            state["status"] = RUN_STATUS_STOP_REQUESTED
        state["updatedAt"] = self._timestamp()
        return self.public_run_state(run_id)

    def should_stop(self, run_id: str) -> bool:
        """Return whether the stream should stop before the next round."""

        state = self._runs.get(self._require_token(run_id, "run_id"))
        return bool(state and state.get("stopRequested"))

    def append_event(self, run_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        """Append one already-sanitized web event to the run log."""

        state = self._require_run_state(run_id)
        payload = self._require_event(event)
        if state["status"] == RUN_STATUS_STARTING and payload["type"] == RUN_STARTED_EVENT_TYPE:
            state["status"] = RUN_STATUS_RUNNING
        state["events"].append(self._sanitize(payload, state.get("secretValues", ())))
        state["updatedAt"] = self._timestamp()
        return self.public_run_state(run_id)

    def mark_stopped(self, run_id: str, *, reason: str = "user_stop") -> dict[str, Any]:
        """Mark a run as stopped after the stream has honored a stop request."""

        state = self._require_run_state(run_id)
        state["status"] = RUN_STATUS_STOPPED_SAFE
        state["stopRequested"] = True
        state["stopReason"] = self._require_text(reason, "stop reason")
        state["updatedAt"] = self._timestamp()
        return self.public_run_state(run_id)

    def mark_completed(self, run_id: str) -> dict[str, Any]:
        """Mark a run as completed."""

        state = self._require_run_state(run_id)
        state["status"] = RUN_STATUS_COMPLETED
        state["stopRequested"] = False
        state["updatedAt"] = self._timestamp()
        return self.public_run_state(run_id)

    def mark_failed(self, run_id: str, *, reason: str = "run_failed") -> dict[str, Any]:
        """Mark a run as failed without fabricating a completed round."""

        state = self._require_run_state(run_id)
        state["status"] = RUN_STATUS_FAILED
        state["stopReason"] = self._require_text(reason, "failure reason")
        state["updatedAt"] = self._timestamp()
        return self.public_run_state(run_id)

    def public_run_state(self, run_id: str) -> dict[str, Any]:
        """Return a safe run-state summary for web routes."""

        state = self._require_run_state(run_id)
        safe_boundary = self._safe_boundary(state["events"])
        return {
            "ok": True,
            "runId": state["runId"],
            "status": state["status"],
            "stopRequested": bool(state["stopRequested"]),
            "stopReason": state["stopReason"],
            "eventCount": len(state["events"]),
            "safeBoundary": safe_boundary,
            "stateMachine": {
                "version": "marketing-sandbox-run-state/v1",
                "allowedStatuses": tuple(sorted(RUN_STATUSES)),
            },
        }

    def build_archive(
        self,
        run_id: str,
        *,
        label: str = "",
        status: str | None = None,
        stop_reason: str | None = None,
        error_message: str = "",
    ) -> dict[str, Any]:
        """Build a safe archive payload from the latest completed boundary."""

        state = self._require_run_state(run_id)
        secret_values = state.get("secretValues", ())
        safe_boundary = self._safe_boundary(state["events"])
        search_state = self._recover_search_state(
            safe_boundary["events"],
            safe_boundary,
            session_snapshot=state.get("sessionSnapshot", {}),
        )
        archive_id = self._archive_id_for_run(run_id)
        archive_status = status or state["status"]
        reason = stop_reason or state.get("stopReason") or archive_status
        can_continue = self._can_continue_from_archive_parts(
            search_state=search_state,
            safe_boundary=safe_boundary,
            session_snapshot=state.get("sessionSnapshot", {}),
            version_compatible=True,
        )
        archive = {
            "schemaVersion": ARCHIVE_SCHEMA_VERSION,
            "archiveFormatVersion": ARCHIVE_FORMAT_VERSION,
            "sandboxCoreVersion": SANDBOX_CORE_VERSION,
            "eventContractVersion": WEB_EVENT_CONTRACT_VERSION,
            "archiveId": archive_id,
            "createdAt": self._timestamp(),
            "label": label.strip() if isinstance(label, str) and label.strip() else run_id,
            "status": archive_status,
            "stopReason": reason,
            "errorMessage": error_message,
            "sessionSnapshot": state.get("sessionSnapshot", {}),
            "playback": {
                "source": "live_archive",
                "events": safe_boundary["events"],
            },
            "safeBoundary": {
                key: value
                for key, value in safe_boundary.items()
                if key != "events"
            },
            "searchState": search_state,
            "resume": {
                "canReplay": bool(safe_boundary["events"]),
                "canContinue": can_continue,
                "mode": "continue_from_completed_round",
                "requiresFreshCredentials": True,
            },
            "versionCompatibility": {
                "status": "compatible",
                "canReplay": bool(safe_boundary["events"]),
                "canContinue": can_continue,
                "resumePolicy": "continue_from_completed_round",
            },
        }
        return self._sanitize(archive, secret_values)

    def save_archive(
        self,
        archive_or_run_id: Mapping[str, Any] | str,
        *,
        label: str = "",
        status: str | None = None,
        stop_reason: str | None = None,
    ) -> dict[str, Any]:
        """Save an archive JSON file and return its safe summary."""

        if isinstance(archive_or_run_id, str):
            run_id = archive_or_run_id
            archive = self.build_archive(
                run_id,
                label=label,
                status=status,
                stop_reason=stop_reason,
            )
        else:
            run_id = ""
            archive = self._validate_archive(dict(archive_or_run_id))
        path = self._archive_path(archive["archiveId"])
        path.write_text(
            json.dumps(archive, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        if run_id:
            state = self._runs.get(run_id)
            if state is not None:
                state["status"] = RUN_STATUS_ARCHIVED
                state["updatedAt"] = self._timestamp()
        return self._archive_summary(archive)

    def list_archives(self) -> tuple[dict[str, Any], ...]:
        """Return saved archive summaries without loading plaintext secrets."""

        summaries: list[dict[str, Any]] = []
        for path in sorted(self.archive_root.glob("*.json")):
            archive = self._validate_archive(
                json.loads(path.read_text(encoding="utf-8"))
            )
            summaries.append(self._archive_summary(archive))
        return tuple(
            sorted(summaries, key=lambda item: item["createdAt"], reverse=True)
        )

    def load_archive(self, archive_id: str) -> dict[str, Any]:
        """Load and validate one archive."""

        archive = json.loads(self._archive_path(archive_id).read_text(encoding="utf-8"))
        return self._validate_archive(archive)

    def restore_archive(self, archive_id: str) -> dict[str, Any]:
        """Return the replay payload for one archive."""

        archive = self.load_archive(archive_id)
        return {
            "ok": True,
            "archive": archive,
            "events": deepcopy(archive["playback"]["events"]),
            "resume": deepcopy(archive["resume"]),
        }

    def prepare_continue_from_archive(self, archive_id: str) -> dict[str, Any]:
        """Return a safe continuation plan; credentials must be supplied later."""

        archive = self.load_archive(archive_id)
        if not archive["resume"]["canContinue"]:
            blocked_reason = archive["resume"].get(
                "blockedReason",
                "archive has no completed round to continue from.",
            )
            raise WebLifecycleError(blocked_reason)
        return {
            "ok": True,
            "status": RUN_STATUS_RESUMING,
            "archiveId": archive["archiveId"],
            "requiresFreshCredentials": True,
            "sessionSnapshot": archive["sessionSnapshot"],
            "safeBoundary": archive["safeBoundary"],
            "searchState": deepcopy(archive["searchState"]),
            "resumePlan": {
                "mode": archive["resume"]["mode"],
                "nextRoundIndex": archive["searchState"].get("nextRoundIndex", 1),
                "completedRoundCount": archive["safeBoundary"]["completedRoundCount"],
                "restoresUcbState": bool(
                    archive["searchState"].get("restoresUcbState")
                ),
                "unfinishedRoundDiscarded": bool(
                    archive["safeBoundary"].get("partialEventsDropped", 0)
                ),
                "requiresFreshCredentials": True,
                "eventContractVersion": archive["eventContractVersion"],
                "sandboxCoreVersion": archive["sandboxCoreVersion"],
            },
            "versionCompatibility": deepcopy(archive["versionCompatibility"]),
            "events": deepcopy(archive["playback"]["events"]),
        }

    def auto_archive_on_disconnect(
        self,
        run_id: str,
        *,
        disconnected_seconds: float,
        timeout_seconds: float,
        error_message: str = "",
    ) -> dict[str, Any]:
        """Save the latest safe progress after a tolerated API disconnect."""

        if disconnected_seconds < timeout_seconds:
            return {
                "ok": False,
                "status": "waiting",
                "runId": self._require_token(run_id, "run_id"),
                "remainingSeconds": timeout_seconds - disconnected_seconds,
            }
        self.mark_stopped(run_id, reason="api_disconnect_timeout")
        archive = self.build_archive(
            run_id,
            status="auto_archived",
            stop_reason="api_disconnect_timeout",
            error_message=error_message,
        )
        summary = self.save_archive(archive)
        state = self._runs.get(self._require_token(run_id, "run_id"))
        if state is not None:
            state["status"] = RUN_STATUS_ARCHIVED
            state["updatedAt"] = self._timestamp()
        return {
            "ok": True,
            "status": "auto_archived",
            "archive": summary,
        }

    def _safe_boundary(self, events: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        validated = [self._require_event(event) for event in events]
        last_safe_index = -1
        completed_rounds: list[int] = []
        for index, event in enumerate(validated):
            if event["type"] in SAFE_BOUNDARY_EVENT_TYPES:
                last_safe_index = index
                if event["type"] == "round_completed" and event["round"] not in completed_rounds:
                    completed_rounds.append(event["round"])
        if last_safe_index < 0:
            safe_events = [
                event for event in validated if event["type"] == RUN_STARTED_EVENT_TYPE
            ]
        else:
            safe_events = validated[: last_safe_index + 1]
        latest_safe_event_id = safe_events[-1]["id"] if safe_events else ""
        return {
            "events": safe_events,
            "completedRounds": completed_rounds,
            "completedRoundCount": len(completed_rounds),
            "latestSafeEventId": latest_safe_event_id,
            "partialEventsDropped": max(len(validated) - len(safe_events), 0),
            "safeBoundaryRule": "latest round_completed or run_completed event",
        }

    def _validate_archive(self, archive: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(archive, Mapping):
            raise WebLifecycleError("archive must be an object.")
        payload = dict(archive)
        schema_version = str(payload.get("schemaVersion") or "")
        schema_supported = schema_version == ARCHIVE_SCHEMA_VERSION
        archive_id = self._require_token(payload.get("archiveId"), "archiveId")
        payload["archiveId"] = archive_id
        playback = payload.get("playback")
        if not isinstance(playback, Mapping):
            raise WebLifecycleError("archive playback must be an object.")
        events = playback.get("events")
        if not isinstance(events, list):
            raise WebLifecycleError("archive playback events must be a list.")
        event_ids: set[str] = set()
        cleaned_events: list[dict[str, Any]] = []
        for event in events:
            payload_event = self._require_event(event)
            if payload_event["id"] in event_ids:
                raise WebLifecycleError("archive event ids must be unique.")
            event_ids.add(payload_event["id"])
            cleaned_events.append(payload_event)
        payload["playback"] = {
            "source": str(playback.get("source", "live_archive")),
            "events": cleaned_events,
        }
        for key in ("createdAt", "label", "status", "stopReason"):
            if key not in payload:
                payload[key] = ""
        payload.setdefault("sessionSnapshot", {})
        safe_boundary = self._safe_boundary(cleaned_events)
        payload["safeBoundary"] = {
            key: value for key, value in safe_boundary.items() if key != "events"
        }
        sandbox_core_version = str(payload.get("sandboxCoreVersion") or SANDBOX_CORE_VERSION)
        explicit_core_version = "sandboxCoreVersion" in payload
        event_contract_version = str(
            payload.get("eventContractVersion") or WEB_EVENT_CONTRACT_VERSION
        )
        payload["schemaVersion"] = schema_version or "unknown"
        payload["archiveFormatVersion"] = int(
            payload.get("archiveFormatVersion") or ARCHIVE_FORMAT_VERSION
        )
        payload["sandboxCoreVersion"] = sandbox_core_version
        payload["eventContractVersion"] = event_contract_version
        version_compatible = schema_supported and (
            not explicit_core_version or sandbox_core_version == SANDBOX_CORE_VERSION
        )
        compatibility_status = self._version_compatibility_status(
            schema_supported=schema_supported,
            explicit_core_version=explicit_core_version,
            sandbox_core_version=sandbox_core_version,
        )
        search_state = self._recover_search_state(
            cleaned_events,
            safe_boundary,
            session_snapshot=payload["sessionSnapshot"],
        )
        payload["searchState"] = search_state
        can_continue = self._can_continue_from_archive_parts(
            search_state=search_state,
            safe_boundary=safe_boundary,
            session_snapshot=payload["sessionSnapshot"],
            version_compatible=version_compatible,
        )
        blocked_reason = self._resume_blocked_reason(
            can_continue=can_continue,
            schema_supported=schema_supported,
            version_compatible=version_compatible,
            search_state=search_state,
            safe_boundary=safe_boundary,
            session_snapshot=payload["sessionSnapshot"],
        )
        payload["resume"] = {
            "canReplay": bool(cleaned_events),
            "canContinue": can_continue,
            "mode": "continue_from_completed_round" if can_continue else "replay_only",
            "requiresFreshCredentials": True,
            "blockedReason": blocked_reason,
        }
        payload["versionCompatibility"] = {
            "status": compatibility_status,
            "canReplay": bool(cleaned_events),
            "canContinue": can_continue,
            "resumePolicy": (
                "continue_from_completed_round" if can_continue else "replay_only"
            ),
            "schemaVersion": payload["schemaVersion"],
            "sandboxCoreVersion": sandbox_core_version,
            "eventContractVersion": event_contract_version,
        }
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if "apiKey" in serialized or "session-secret" in serialized:
            raise WebLifecycleError("archive must not contain plaintext API secrets.")
        return payload

    def _version_compatibility_status(
        self,
        *,
        schema_supported: bool,
        explicit_core_version: bool,
        sandbox_core_version: str,
    ) -> str:
        if not schema_supported:
            return "unsupported_schema_replay_only"
        if explicit_core_version and sandbox_core_version != SANDBOX_CORE_VERSION:
            return "incompatible_core_replay_only"
        if not explicit_core_version:
            return "migrated_current_core"
        return "compatible"

    def _resume_blocked_reason(
        self,
        *,
        can_continue: bool,
        schema_supported: bool,
        version_compatible: bool,
        search_state: Mapping[str, Any],
        safe_boundary: Mapping[str, Any],
        session_snapshot: Mapping[str, Any],
    ) -> str:
        if can_continue:
            return ""
        if not schema_supported:
            return "archive schema version is replay-only and cannot be resumed."
        if not version_compatible:
            return "archive sandbox core version is incompatible with safe resume."
        if safe_boundary.get("completedRoundCount", 0) <= 0:
            return "archive has no completed round to continue from."
        if self._snapshot_uses_ucb(session_snapshot) and not search_state.get(
            "restoresUcbState"
        ):
            return "UCB archive has no recoverable completed reward history."
        return "archive can be replayed but cannot be safely resumed."

    def _can_continue_from_archive_parts(
        self,
        *,
        search_state: Mapping[str, Any],
        safe_boundary: Mapping[str, Any],
        session_snapshot: Mapping[str, Any],
        version_compatible: bool,
    ) -> bool:
        if not version_compatible:
            return False
        if int(safe_boundary.get("completedRoundCount", 0) or 0) <= 0:
            return False
        if self._snapshot_uses_ucb(session_snapshot):
            return bool(search_state.get("restoresUcbState"))
        return True

    def _recover_search_state(
        self,
        events: Sequence[Mapping[str, Any]],
        safe_boundary: Mapping[str, Any],
        *,
        session_snapshot: Mapping[str, Any],
    ) -> dict[str, Any]:
        strategy_by_family: dict[str, dict[str, Any]] = {}
        family_states: dict[str, dict[str, Any]] = {}
        reward_history: list[dict[str, Any]] = []
        for order, event in enumerate(events):
            payload = self._require_event(event)
            if payload["type"] == "strategy_proposed":
                strategy = self._mapping_or_empty(payload.get("strategy"))
                family_id = self._optional_text(strategy.get("familyId"))
                if family_id:
                    strategy_by_family[family_id] = {
                        "familyId": family_id,
                        "strategyName": self._optional_text(strategy.get("name")),
                        "intent": self._optional_text(strategy.get("intent")),
                        "familyFit": self._optional_text(strategy.get("familyFit")),
                        "round": payload["round"],
                        "eventId": payload["id"],
                    }
                continue
            if payload["type"] != "search_updated":
                continue
            search = self._mapping_or_empty(payload.get("search"))
            metrics = self._mapping_or_empty(search.get("internalMetrics"))
            family_id = self._optional_text(metrics.get("familyId"))
            if not family_id:
                family = self._first_mapping_item(search.get("families"))
                family_id = self._optional_text(family.get("id"))
            if not family_id:
                continue
            state_after = self._mapping_or_empty(metrics.get("stateAfter"))
            reward = self._optional_number(metrics.get("reward"))
            pull_count = self._optional_int(state_after.get("pullCount"))
            reward_sum = self._optional_number(state_after.get("rewardSum"))
            mean_reward = self._optional_number(state_after.get("meanReward"))
            last_selected_round = self._optional_int(
                state_after.get("lastSelectedRound")
            )
            signals = self._mapping_or_empty(search.get("signals"))
            strategy_name = (
                self._optional_text(signals.get("strategyName"))
                or strategy_by_family.get(family_id, {}).get("strategyName")
                or f"{family_id} strategy"
            )
            record = {
                "order": order,
                "eventId": payload["id"],
                "round": payload["round"],
                "familyId": family_id,
                "strategyName": strategy_name,
                "reward": reward,
                "positiveUtility": self._optional_number(
                    metrics.get("positiveUtility")
                ),
                "riskPenalty": self._optional_number(metrics.get("riskPenalty")),
                "positiveComponents": dict(
                    self._mapping_or_empty(metrics.get("positiveComponents"))
                ),
                "riskComponents": dict(
                    self._mapping_or_empty(metrics.get("riskComponents"))
                ),
                "appliedCaps": list(metrics.get("appliedCaps") or ()),
                "mappingNote": self._optional_text(metrics.get("mappingNote")),
                "summaryNote": self._optional_text(
                    self._mapping_or_empty(signals.get("summaryLabels")).get(
                        "signal_note"
                    )
                )
                or self._optional_text(signals.get("summary")),
                "riskNote": self._optional_text(
                    self._mapping_or_empty(signals.get("riskLabels")).get("risk_note")
                )
                or self._optional_text(signals.get("risk")),
            }
            if reward is not None:
                reward_history.append(record)
            existing = family_states.get(family_id, {})
            family_states[family_id] = {
                "familyId": family_id,
                "pullCount": pull_count
                if pull_count is not None
                else int(existing.get("pullCount", 0)) + (1 if reward is not None else 0),
                "rewardSum": reward_sum
                if reward_sum is not None
                else float(existing.get("rewardSum", 0.0)) + (reward or 0.0),
                "meanReward": mean_reward
                if mean_reward is not None
                else self._safe_mean(
                    float(existing.get("rewardSum", 0.0)) + (reward or 0.0),
                    int(existing.get("pullCount", 0)) + (1 if reward is not None else 0),
                ),
                "lastSelectedRound": last_selected_round or payload["round"],
                "latestStrategy": strategy_by_family.get(family_id, {})
                or {
                    "familyId": family_id,
                    "strategyName": strategy_name,
                    "round": payload["round"],
                },
                "latestRewardEventId": payload["id"],
            }
        best_family_id = self._best_family_id(family_states)
        return {
            "source": "completed_round_events",
            "ucbStateIncludesCompletedRoundsOnly": True,
            "metricBoundary": (
                "Archived reward and UCB values are internal search trace, "
                "not purchase rates or market forecasts."
            ),
            "completedRoundCount": safe_boundary.get("completedRoundCount", 0),
            "completedRounds": list(safe_boundary.get("completedRounds", ())),
            "partialEventsDropped": safe_boundary.get("partialEventsDropped", 0),
            "nextRoundIndex": self._next_round_index(safe_boundary),
            "usesUcb": self._snapshot_uses_ucb(session_snapshot),
            "restoresUcbState": bool(reward_history),
            "familyStates": family_states,
            "rewardHistory": reward_history,
            "currentBestFamilyId": best_family_id,
            "currentBestStrategy": family_states.get(best_family_id, {}).get(
                "latestStrategy",
                {},
            ),
            "recoveryRule": (
                "Only search_updated events before the latest safe round_completed "
                "or run_completed boundary are used for UCB recovery."
            ),
        }

    @staticmethod
    def _snapshot_uses_ucb(session_snapshot: Mapping[str, Any]) -> bool:
        config = session_snapshot.get("config") if isinstance(session_snapshot, Mapping) else None
        if not isinstance(config, Mapping):
            return False
        search = config.get("search")
        return bool(isinstance(search, Mapping) and search.get("useUcb") is True)

    @staticmethod
    def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _first_mapping_item(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                if isinstance(item, Mapping):
                    return item
        return {}

    @staticmethod
    def _optional_text(value: Any) -> str:
        return value.strip() if isinstance(value, str) and value.strip() else ""

    @staticmethod
    def _optional_number(value: Any) -> float | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    @staticmethod
    def _safe_mean(reward_sum: float, pull_count: int) -> float:
        return reward_sum / pull_count if pull_count else 0.0

    @staticmethod
    def _next_round_index(safe_boundary: Mapping[str, Any]) -> int:
        rounds = safe_boundary.get("completedRounds", ())
        if not isinstance(rounds, Sequence) or isinstance(rounds, (str, bytes)) or not rounds:
            return 1
        numeric_rounds = [item for item in rounds if isinstance(item, int)]
        return (max(numeric_rounds) + 1) if numeric_rounds else 1

    @staticmethod
    def _best_family_id(family_states: Mapping[str, Mapping[str, Any]]) -> str:
        if not family_states:
            return ""
        ordered = sorted(
            family_states.items(),
            key=lambda item: (
                -float(item[1].get("meanReward", 0.0) or 0.0),
                -int(item[1].get("pullCount", 0) or 0),
                str(item[0]),
            ),
        )
        return ordered[0][0]

    def _archive_summary(self, archive: Mapping[str, Any]) -> dict[str, Any]:
        events = archive["playback"]["events"]
        return {
            "archiveId": archive["archiveId"],
            "createdAt": archive["createdAt"],
            "label": archive["label"],
            "status": archive["status"],
            "stopReason": archive["stopReason"],
            "eventCount": len(events),
            "completedRoundCount": archive["safeBoundary"]["completedRoundCount"],
            "canContinue": bool(archive["resume"]["canContinue"]),
        }

    def _archive_id_for_run(self, run_id: str) -> str:
        token = self._require_token(run_id, "run_id")
        stamp = self._timestamp().replace("-", "").replace(":", "").replace("+", "z")
        stamp = re.sub(r"[^A-Za-z0-9_-]+", "-", stamp).strip("-")
        return f"{token}-{stamp}"

    def _archive_path(self, archive_id: str) -> Path:
        archive_id = self._require_token(archive_id, "archiveId")
        path = (self.archive_root / f"{archive_id}.json").resolve()
        root = self.archive_root.resolve()
        if root != path.parent:
            raise WebLifecycleError("archiveId escapes archive root.")
        return path

    def _require_run_state(self, run_id: str) -> dict[str, Any]:
        run_id = self._require_token(run_id, "run_id")
        try:
            return self._runs[run_id]
        except KeyError as error:
            raise WebLifecycleError(f"unknown run id: {run_id}.") from error

    @staticmethod
    def _require_event(event: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(event, Mapping):
            raise WebLifecycleError("event must be an object.")
        event_id = WebRunLifecycleManager._require_text(event.get("id"), "event id")
        event_type = WebRunLifecycleManager._require_text(event.get("type"), "event type")
        round_value = event.get("round")
        if isinstance(round_value, bool) or not isinstance(round_value, int) or round_value < 0:
            raise WebLifecycleError("event round must be a non-negative integer.")
        payload = dict(event)
        payload["id"] = event_id
        payload["type"] = event_type
        payload["round"] = round_value
        return payload

    @staticmethod
    def _require_text(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise WebLifecycleError(f"{label} must be non-empty text.")
        return value.strip()

    @staticmethod
    def _require_token(value: Any, label: str) -> str:
        token = WebRunLifecycleManager._require_text(value, label)
        if not RUN_ID_PATTERN.fullmatch(token):
            raise WebLifecycleError(f"{label} must be an ASCII token.")
        return token

    @classmethod
    def _sanitize(cls, value: Any, secret_values: Sequence[str]) -> Any:
        if isinstance(value, Mapping):
            safe: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if key_text.lower() in {"apikey", "api_key", "authorization"}:
                    continue
                safe[key_text] = cls._sanitize(item, secret_values)
            return safe
        if isinstance(value, list):
            return [cls._sanitize(item, secret_values) for item in value]
        if isinstance(value, tuple):
            return [cls._sanitize(item, secret_values) for item in value]
        if isinstance(value, str):
            safe_text = value
            for secret in secret_values:
                if secret:
                    safe_text = safe_text.replace(secret, "[redacted]")
            return safe_text
        return value

    def _timestamp(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime):
            raise WebLifecycleError("clock must return a datetime.")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()


def handle_stop_request(
    payload: Mapping[str, Any],
    manager: WebRunLifecycleManager,
) -> tuple[int, dict[str, Any]]:
    """Framework-neutral stop route helper."""

    try:
        request = _require_mapping(payload, "stop payload")
        result = manager.request_stop(
            request.get("runId"),
            reason=str(request.get("reason") or "user_stop"),
        )
    except WebLifecycleError as error:
        return 400, {"ok": False, "status": "invalid_request", "message": str(error)}
    return 200, result


def handle_archive_save_request(
    payload: Mapping[str, Any],
    manager: WebRunLifecycleManager,
) -> tuple[int, dict[str, Any]]:
    """Framework-neutral archive-save route helper."""

    try:
        request = _require_mapping(payload, "archive payload")
        archive_payload = request.get("archive")
        if archive_payload is None:
            summary = manager.save_archive(
                request.get("runId"),
                label=str(request.get("label") or ""),
                status=request.get("status"),
                stop_reason=request.get("stopReason"),
            )
        else:
            summary = manager.save_archive(_require_mapping(archive_payload, "archive"))
    except WebLifecycleError as error:
        return 400, {"ok": False, "status": "invalid_request", "message": str(error)}
    return 200, {"ok": True, "archive": summary}


def handle_archive_restore_request(
    payload: Mapping[str, Any],
    manager: WebRunLifecycleManager,
) -> tuple[int, dict[str, Any]]:
    """Framework-neutral archive-restore route helper."""

    try:
        request = _require_mapping(payload, "restore payload")
        result = manager.restore_archive(request.get("archiveId"))
    except WebLifecycleError as error:
        return 400, {"ok": False, "status": "invalid_request", "message": str(error)}
    return 200, result


def handle_archive_continue_request(
    payload: Mapping[str, Any],
    manager: WebRunLifecycleManager,
) -> tuple[int, dict[str, Any]]:
    """Framework-neutral safe-boundary continuation-plan helper."""

    try:
        request = _require_mapping(payload, "continue payload")
        result = manager.prepare_continue_from_archive(request.get("archiveId"))
    except WebLifecycleError as error:
        return 400, {"ok": False, "status": "invalid_request", "message": str(error)}
    return 200, result


def handle_archive_list_request(
    manager: WebRunLifecycleManager,
) -> tuple[int, dict[str, Any]]:
    """Framework-neutral archive-list route helper."""

    return 200, {"ok": True, "archives": list(manager.list_archives())}


def handle_api_disconnect_timeout(
    payload: Mapping[str, Any],
    manager: WebRunLifecycleManager,
) -> tuple[int, dict[str, Any]]:
    """Framework-neutral helper for API disconnect auto-archive checks."""

    try:
        request = _require_mapping(payload, "disconnect payload")
        result = manager.auto_archive_on_disconnect(
            request.get("runId"),
            disconnected_seconds=_require_float(request.get("disconnectedSeconds")),
            timeout_seconds=_require_float(request.get("timeoutSeconds")),
            error_message=str(request.get("message") or ""),
        )
    except WebLifecycleError as error:
        return 400, {"ok": False, "status": "invalid_request", "message": str(error)}
    return (200 if result["ok"] else 202), result


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WebLifecycleError(f"{label} must be an object.")
    return value


def _require_float(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WebLifecycleError("timeout values must be numeric.")
    parsed = float(value)
    if parsed < 0:
        raise WebLifecycleError("timeout values cannot be negative.")
    return parsed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
