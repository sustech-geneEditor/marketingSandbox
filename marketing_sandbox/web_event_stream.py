"""Framework-neutral event stream bridge for live website sandbox runs."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Iterator, Mapping

from .decision_agent import DecisionOutputError
from .marketing_sandbox import SandboxResult
from .output_contract_guard import OutputContractGuardError
from .web_events import SandboxWebEventMapper, WebEventMappingError
from .web_runner import WebRunnerError
from .web_session import WebRunSession


RUN_ID_UNSAFE_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


class WebEventStreamError(Exception):
    """Raised when a live sandbox run cannot become a web event stream."""


class WebRunEventStream:
    """Turn one live web run session into ordered frontend events.

    When the runner exposes ``build_sandbox`` this bridge emits a run boundary,
    then streams each completed round as soon as it is available. Runners that
    only expose ``run`` still work as a completed-result fallback.
    """

    def __init__(
        self,
        runner: Any,
        *,
        mapper_factory: Callable[..., SandboxWebEventMapper] = SandboxWebEventMapper,
        lifecycle_manager: Any | None = None,
    ) -> None:
        if not callable(getattr(runner, "run", None)) and not callable(
            getattr(runner, "build_sandbox", None)
        ):
            raise WebEventStreamError(
                "WebRunEventStream runner must expose run or build_sandbox."
            )
        if not callable(mapper_factory):
            raise WebEventStreamError("mapper_factory must be callable.")
        self._runner = runner
        self._mapper_factory = mapper_factory
        self._lifecycle_manager = lifecycle_manager

    def iter_events(
        self,
        session: WebRunSession,
        *,
        run_id: str | None = None,
        round_count: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield frontend event payloads for one live run."""

        session = self._require_live_session(session)
        event_run_id = self._resolve_run_id(session, run_id)
        rounds = self._round_count_for_session(session, round_count)
        mapper = self._make_mapper(session)
        self._register_lifecycle_run(event_run_id, session)

        if callable(getattr(self._runner, "build_sandbox", None)):
            try:
                yield from self._iter_round_by_round(
                    session,
                    mapper,
                    run_id=event_run_id,
                    round_count=rounds,
                )
            except Exception as error:
                self._mark_lifecycle_failed(event_run_id, error)
                raise
            return

        if self._should_stop(event_run_id):
            self._mark_lifecycle_stopped(event_run_id, "user_stop")
            return
        result = self._runner.run(session, round_count=rounds)
        try:
            events = mapper.map_result(result, run_id=event_run_id)
        except WebEventMappingError as error:
            raise WebEventStreamError(str(error)) from error
        for event in events:
            self._append_lifecycle_event(event_run_id, event)
            yield event
        self._mark_lifecycle_completed(event_run_id)

    def collect_events(
        self,
        session: WebRunSession,
        *,
        run_id: str | None = None,
        round_count: int | None = None,
    ) -> tuple[dict[str, Any], ...]:
        """Collect the stream into a tuple for route handlers and tests."""

        return tuple(
            self.iter_events(session, run_id=run_id, round_count=round_count)
        )

    def iter_json_lines(
        self,
        session: WebRunSession,
        *,
        run_id: str | None = None,
        round_count: int | None = None,
    ) -> Iterator[str]:
        """Yield newline-delimited JSON chunks for simple streaming routes."""

        for event in self.iter_events(
            session,
            run_id=run_id,
            round_count=round_count,
        ):
            yield format_json_line_event(event)

    def iter_sse(
        self,
        session: WebRunSession,
        *,
        run_id: str | None = None,
        round_count: int | None = None,
    ) -> Iterator[str]:
        """Yield Server-Sent Event chunks for a future browser endpoint."""

        for event in self.iter_events(
            session,
            run_id=run_id,
            round_count=round_count,
        ):
            yield format_sse_event(event)

    def response_payload(
        self,
        session: WebRunSession,
        *,
        run_id: str | None = None,
        round_count: int | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Return a framework-neutral JSON response body for this stream."""

        return handle_live_event_stream(
            session,
            self,
            run_id=run_id,
            round_count=round_count,
        )

    def _iter_round_by_round(
        self,
        session: WebRunSession,
        mapper: SandboxWebEventMapper,
        *,
        run_id: str,
        round_count: int,
    ) -> Iterator[dict[str, Any]]:
        sandbox = self._runner.build_sandbox(session)
        try:
            for event in mapper.start_stream(run_id=run_id):
                self._append_lifecycle_event(run_id, event)
                yield event
            if self._should_stop(run_id):
                self._mark_lifecycle_stopped(run_id, "user_stop")
                return
            for _ in range(round_count):
                for event in mapper.append_round_progress(
                    round_index=self._next_round_index(sandbox),
                    expected_model_calls=self._expected_model_calls(session),
                    persona_count=len(session.config.persona_ids),
                    candidate_count=session.config.candidates_per_round,
                ):
                    self._append_lifecycle_event(run_id, event)
                    yield event
                if self._should_stop(run_id):
                    self._mark_lifecycle_stopped(run_id, "user_stop")
                    return
                round_result = sandbox.run_round()
                for event in mapper.append_round_stream(round_result):
                    self._append_lifecycle_event(run_id, event)
                    yield event
                if self._should_stop(run_id):
                    self._mark_lifecycle_stopped(run_id, "user_stop")
                    return
            result = sandbox.build_result()
            for event in mapper.complete_stream(result):
                self._append_lifecycle_event(run_id, event)
                yield event
            self._mark_lifecycle_completed(run_id)
        except Exception as error:  # noqa: BLE001 - provider and model errors vary.
            try:
                failure_events = mapper.fail_stream(
                    error,
                    round_index=self._next_round_index(sandbox),
                    issue_kind=_issue_kind_for_error("run_failed", error),
                )
            except WebEventMappingError as mapping_error:
                raise WebEventStreamError(str(mapping_error)) from mapping_error
            for event in failure_events:
                self._append_lifecycle_event(run_id, event)
                yield event
            self._mark_lifecycle_failed(run_id, error)
            return

    def _register_lifecycle_run(self, run_id: str, session: WebRunSession) -> None:
        if self._lifecycle_manager is None:
            return
        self._lifecycle_manager.register_run(
            run_id,
            session_snapshot=session.public_snapshot(),
            secret_values=session.secret_values_for_redaction(),
        )

    def _append_lifecycle_event(self, run_id: str, event: Mapping[str, Any]) -> None:
        if self._lifecycle_manager is not None:
            self._lifecycle_manager.append_event(run_id, event)

    def _should_stop(self, run_id: str) -> bool:
        if self._lifecycle_manager is None:
            return False
        return bool(self._lifecycle_manager.should_stop(run_id))

    def _mark_lifecycle_stopped(self, run_id: str, reason: str) -> None:
        if self._lifecycle_manager is not None:
            self._lifecycle_manager.mark_stopped(run_id, reason=reason)

    def _mark_lifecycle_completed(self, run_id: str) -> None:
        if self._lifecycle_manager is not None:
            self._lifecycle_manager.mark_completed(run_id)

    def _mark_lifecycle_failed(self, run_id: str, error: Exception) -> None:
        if self._lifecycle_manager is not None:
            self._lifecycle_manager.mark_failed(run_id, reason=error.__class__.__name__)

    def _make_mapper(self, session: WebRunSession) -> SandboxWebEventMapper:
        return self._mapper_factory(
            sensitive_values=session.secret_values_for_redaction()
        )

    @staticmethod
    def _expected_model_calls(session: WebRunSession) -> int:
        """Return a simple per-round call estimate for the current web config."""

        persona_count = len(session.config.persona_ids)
        candidate_count = session.config.candidates_per_round
        decision_calls = 1
        synthesis_and_critic_calls = 2
        return decision_calls + candidate_count * (
            persona_count + synthesis_and_critic_calls
        )

    @staticmethod
    def _next_round_index(sandbox: Any) -> int:
        try:
            history = getattr(sandbox, "history", ())
            return max(len(history) + 1, 1)
        except Exception:  # noqa: BLE001 - failure reporting should not fail too.
            return 1

    @staticmethod
    def _require_live_session(session: WebRunSession) -> WebRunSession:
        if not isinstance(session, WebRunSession):
            raise WebEventStreamError("live event stream needs a WebRunSession.")
        if session.config.source != "live":
            raise WebEventStreamError("live event stream needs a live session.")
        return session

    @staticmethod
    def _round_count_for_session(
        session: WebRunSession,
        round_count: int | None,
    ) -> int:
        if round_count is None:
            return session.config.rounds
        if isinstance(round_count, bool) or not isinstance(round_count, int):
            raise WebEventStreamError("round_count must be a positive integer.")
        if round_count < 1:
            raise WebEventStreamError("round_count must be a positive integer.")
        if round_count > session.config.rounds:
            raise WebEventStreamError(
                "round_count cannot exceed the configured web run rounds."
            )
        return round_count

    @staticmethod
    def _resolve_run_id(session: WebRunSession, run_id: str | None) -> str:
        if run_id is not None:
            if not isinstance(run_id, str) or not run_id.strip():
                raise WebEventStreamError("run_id must be non-empty text.")
            return run_id.strip()
        token = RUN_ID_UNSAFE_PATTERN.sub("-", session.session_id).strip("-_")
        token = token[:80].strip("-_")
        return token or "live-run"


def handle_live_event_stream(
    session: WebRunSession,
    event_stream: WebRunEventStream,
    *,
    run_id: str | None = None,
    round_count: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """Framework-neutral response helper for a future live event route."""

    secret_values = _session_secret_values(session)
    try:
        stream = _require_event_stream(event_stream)
        events = stream.collect_events(
            session,
            run_id=run_id,
            round_count=round_count,
        )
    except WebEventStreamError as error:
        return _error_response(400, "invalid_request", error, secret_values)
    except WebRunnerError as error:
        return _error_response(502, "run_failed", error, secret_values)
    except Exception as error:  # noqa: BLE001 - model and transport errors vary.
        return _error_response(500, "run_failed", error, secret_values)

    status = (
        "failed"
        if events and events[-1].get("type") == "run_failed"
        else "completed"
    )
    return 200, {
        "ok": True,
        "status": status,
        "eventCount": len(events),
        "events": list(events),
    }


def format_json_line_event(event: Mapping[str, Any]) -> str:
    """Serialize one web event as newline-delimited JSON."""

    return f"{json.dumps(_require_event_payload(event), ensure_ascii=False, separators=(',', ':'))}\n"


def format_sse_event(event: Mapping[str, Any]) -> str:
    """Serialize one web event as a Server-Sent Event chunk."""

    payload = _require_event_payload(event)
    event_id = _require_sse_field(payload.get("id"), "event id")
    event_type = _require_sse_field(payload.get("type"), "event type")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"


def _require_event_stream(event_stream: Any) -> WebRunEventStream:
    if not isinstance(event_stream, WebRunEventStream):
        raise WebEventStreamError("event_stream must be a WebRunEventStream.")
    return event_stream


def _require_event_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise WebEventStreamError("stream event must be an object.")
    payload = dict(event)
    _require_sse_field(payload.get("id"), "event id")
    _require_sse_field(payload.get("type"), "event type")
    return payload


def _require_sse_field(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WebEventStreamError(f"{label} must be non-empty text.")
    text = value.strip()
    if "\n" in text or "\r" in text:
        raise WebEventStreamError(f"{label} must be a single line.")
    return text


def _error_response(
    status_code: int,
    status: str,
    error: Exception,
    secret_values: tuple[str, ...],
) -> tuple[int, dict[str, Any]]:
    return status_code, {
        "ok": False,
        "status": status,
        "issueKind": _issue_kind_for_error(status, error),
        "message": _redact_text(str(error), secret_values),
    }


def _issue_kind_for_error(status: str, error: Exception) -> str:
    if isinstance(error, (DecisionOutputError, OutputContractGuardError)):
        return "contract_error"
    if isinstance(error, WebEventMappingError):
        return "contract_error"

    error_text = f"{error.__class__.__name__} {error}".lower()
    if any(
        hint in error_text
        for hint in (
            "outputcontract",
            "output contract",
            "contract rejected",
            "web event",
            "event mapping",
        )
    ):
        return "contract_error"

    return "invalid_request" if status == "invalid_request" else "runtime_error"


def _session_secret_values(session: Any) -> tuple[str, ...]:
    if isinstance(session, WebRunSession):
        return session.secret_values_for_redaction()
    return ()


def _redact_text(text: str, secret_values: tuple[str, ...]) -> str:
    safe_text = text
    for secret in secret_values:
        if secret:
            safe_text = safe_text.replace(secret, "[redacted]")
    return safe_text
