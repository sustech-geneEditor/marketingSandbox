"""Repeatable smoke checks for the real website API path.

The smoke runner is intentionally separate from unit tests.  It can run the
cheap/local failure scenarios without credentials, and it only calls an
external provider when the caller explicitly enables the real smoke flag and
supplies an API key through the environment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from .web_api import WebApiResponse, WebSandboxApi


REAL_SMOKE_FLAG = "MARKETING_SANDBOX_SMOKE_RUN_REAL"
BASE_URL_ENV = "MARKETING_SANDBOX_SMOKE_BASE_URL"
API_KEY_ENV = "MARKETING_SANDBOX_SMOKE_API_KEY"
MODEL_ENV = "MARKETING_SANDBOX_SMOKE_MODEL"
PROVIDER_ENV = "MARKETING_SANDBOX_SMOKE_PROVIDER"
ARCHIVE_ROOT_ENV = "MARKETING_SANDBOX_SMOKE_ARCHIVE_ROOT"

DEFAULT_PROVIDER_ID = "openai-compatible"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"

REQUIRED_REAL_EVENT_TYPES = frozenset(
    {
        "run_started",
        "round_progress",
        "round_started",
        "family_selected",
        "strategy_proposed",
        "consumer_feedback_ready",
        "feedback_summary_ready",
        "critique_ready",
        "search_updated",
        "round_completed",
        "run_completed",
    }
)


@dataclass(frozen=True)
class SmokeConfig:
    """External provider route for an optional real smoke run."""

    base_url: str = DEFAULT_GROQ_BASE_URL
    model: str = DEFAULT_GROQ_MODEL
    provider_id: str = DEFAULT_PROVIDER_ID
    api_key: str = ""
    archive_root: str = ""

    @classmethod
    def from_env(cls) -> "SmokeConfig":
        """Build config from env without printing secrets."""

        return cls(
            base_url=os.environ.get(BASE_URL_ENV, DEFAULT_GROQ_BASE_URL).strip(),
            model=os.environ.get(MODEL_ENV, DEFAULT_GROQ_MODEL).strip(),
            provider_id=os.environ.get(PROVIDER_ENV, DEFAULT_PROVIDER_ID).strip(),
            api_key=os.environ.get(API_KEY_ENV, "").strip(),
            archive_root=os.environ.get(ARCHIVE_ROOT_ENV, "").strip(),
        )

    @property
    def has_real_credentials(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def safe_summary(self) -> dict[str, Any]:
        return {
            "providerId": self.provider_id,
            "baseUrl": self.base_url,
            "model": self.model,
            "apiKeyPresent": bool(self.api_key),
            "archiveRoot": self.archive_root or "temporary",
        }


@dataclass
class SmokeStep:
    """One smoke-test step result."""

    name: str
    ok: bool
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class SmokeReport:
    """Aggregated smoke-test report."""

    real_run_requested: bool
    provider: dict[str, Any]
    steps: list[SmokeStep] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(step.ok for step in self.steps)

    def add(self, step: SmokeStep) -> SmokeStep:
        self.steps.append(step)
        return step

    def public_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "realRunRequested": self.real_run_requested,
            "provider": self.provider,
            "steps": [step.public_payload() for step in self.steps],
        }


def build_minimal_live_payload(config: SmokeConfig, *, run_id: str = "real-smoke") -> dict[str, Any]:
    """Return the smallest UCB-enabled live payload for one smoke round."""

    return {
        "runId": run_id,
        "roundCount": 1,
        "source": "live",
        "provider": {
            "id": config.provider_id,
            "baseUrl": config.base_url,
            "apiKey": config.api_key,
            "defaultModel": config.model,
            "useBackendDefaults": False,
        },
        "models": {
            "decision": config.model,
            "consumers": config.model,
            "synthesizer": config.model,
            "critic": config.model,
        },
        "product": {
            "name": "Smoke Test Sample",
            "brand": "Use only supplied facts. No external brand claims.",
            "facts": "A classroom sample product for testing the sandbox API path.",
            "goal": "Verify one real marketing sandbox round can stream events.",
        },
        "personaIds": ["value-pragmatist"],
        "scenarioId": "normal",
        "actionCategories": ["Product", "Price", "Promotion", "Retention"],
        "search": {
            "useUcb": True,
            "rounds": 1,
            "candidatesPerRound": 1,
            "familyIds": ["trial_value_entry"],
        },
    }


def run_smoke_suite(config: SmokeConfig | None = None, *, run_real: bool = False) -> SmokeReport:
    """Run local failure checks and, when enabled, one real provider smoke."""

    resolved = config or SmokeConfig.from_env()
    report = SmokeReport(
        real_run_requested=run_real,
        provider=resolved.safe_summary(),
    )
    report.steps.extend(run_failure_scenarios())
    if not run_real:
        report.add(
            SmokeStep(
                name="real_provider_smoke",
                ok=True,
                status="skipped",
                message=f"Set {REAL_SMOKE_FLAG}=1 and {API_KEY_ENV} to call a real provider.",
            )
        )
        return report
    if not resolved.has_real_credentials:
        report.add(
            SmokeStep(
                name="real_provider_smoke",
                ok=False,
                status="missing_credentials",
                message=f"Real smoke needs {BASE_URL_ENV}, {MODEL_ENV}, and {API_KEY_ENV}.",
            )
        )
        return report
    report.steps.extend(run_real_provider_smoke(resolved))
    return report


def run_real_provider_smoke(config: SmokeConfig) -> list[SmokeStep]:
    """Call provider-check, stream one real round, save, and request resume plan."""

    steps: list[SmokeStep] = []
    with _archive_root(config.archive_root) as archive_root:
        api = WebSandboxApi(archive_root=archive_root)
        payload = build_minimal_live_payload(config)

        provider_step, provider_body = _provider_check_step(api, payload)
        steps.append(provider_step)
        if not provider_step.ok:
            return steps

        stream_step, events = _live_stream_step(api, payload, run_id="real-smoke")
        steps.append(stream_step)
        if not stream_step.ok:
            return steps

        archive_step, archive_id = _archive_step(api, "real-smoke")
        steps.append(archive_step)
        if archive_id:
            steps.append(_resume_plan_step(api, archive_id))

        steps.append(
            SmokeStep(
                name="real_provider_model_check",
                ok=True,
                status=str(provider_body.get("modelStatus") or "callable"),
                message="Provider model check and live stream completed.",
                details={
                    "eventCount": len(events),
                    "archiveId": archive_id,
                },
            )
        )
    return steps


def run_failure_scenarios() -> list[SmokeStep]:
    """Run deterministic failure checks without touching external providers."""

    steps: list[SmokeStep] = []
    with tempfile.TemporaryDirectory(prefix="marketing-smoke-failures-") as root:
        steps.append(_wrong_key_step(root))
        steps.append(_wrong_model_step(root))
        steps.append(_bad_base_url_step(root))
        steps.append(_runtime_provider_failure_step(root))
        steps.extend(_stop_archive_resume_failure_path_steps(root))
    return steps


def _provider_check_step(api: WebSandboxApi, payload: Mapping[str, Any]) -> tuple[SmokeStep, dict[str, Any]]:
    response = api.handle(
        "POST",
        "/api/sandbox/provider-check",
        _json_body(payload),
    )
    body = _response_json(response)
    ok = response.status_code == 200 and body.get("ok") is True
    return (
        SmokeStep(
            name="provider_check",
            ok=ok,
            status=str(body.get("status") or response.status_code),
            message=str(body.get("message") or "provider-check completed"),
            details={"modelStatus": body.get("modelStatus") or body.get("modelCheck", {}).get("modelStatus")},
        ),
        body,
    )


def _live_stream_step(
    api: WebSandboxApi,
    payload: Mapping[str, Any],
    *,
    run_id: str,
) -> tuple[SmokeStep, list[dict[str, Any]]]:
    response = api.handle(
        "POST",
        "/api/sandbox/live-events",
        _json_body(payload),
        headers={"Accept": "application/x-ndjson", "X-Sandbox-Run-Id": run_id},
    )
    try:
        events = _events_from_response(response)
    except Exception as error:  # noqa: BLE001 - external providers vary.
        return (
            SmokeStep(
                name="live_event_stream",
                ok=False,
                status="stream_failed",
                message=str(error),
            ),
            [],
        )
    event_types = {event.get("type") for event in events}
    missing_types = sorted(REQUIRED_REAL_EVENT_TYPES - event_types)
    search_event = next((event for event in events if event.get("type") == "search_updated"), {})
    family_event = next((event for event in events if event.get("type") == "family_selected"), {})
    has_reward = isinstance(
        search_event.get("search", {}).get("internalMetrics", {}).get("reward"),
        (int, float),
    )
    has_ucb = bool(family_event.get("internalSearch", {}).get("ucbScore"))
    ok = response.status_code == 200 and not missing_types and has_reward and has_ucb
    return (
        SmokeStep(
            name="live_event_stream",
            ok=ok,
            status="completed" if ok else "incomplete_events",
            message="One live round streamed required role, reward, and UCB events."
            if ok
            else "Live stream did not expose every required smoke-test event.",
            details={
                "eventCount": len(events),
                "missingTypes": missing_types,
                "hasReward": has_reward,
                "hasUcb": has_ucb,
            },
        ),
        events,
    )


def _archive_step(api: WebSandboxApi, run_id: str) -> tuple[SmokeStep, str]:
    response = api.handle(
        "POST",
        "/api/sandbox/archives",
        _json_body({"runId": run_id, "label": "Real API smoke archive"}),
    )
    body = _response_json(response)
    archive = body.get("archive") if isinstance(body.get("archive"), Mapping) else {}
    archive_id = str(archive.get("archiveId") or "")
    ok = response.status_code == 200 and bool(archive_id)
    return (
        SmokeStep(
            name="stop_or_completed_archive",
            ok=ok,
            status=str(body.get("status") or response.status_code),
            message="Saved a backend archive at the latest safe boundary."
            if ok
            else str(body.get("message") or "Archive save failed."),
            details={"archiveId": archive_id, "completedRoundCount": archive.get("completedRoundCount")},
        ),
        archive_id,
    )


def _resume_plan_step(api: WebSandboxApi, archive_id: str) -> SmokeStep:
    response = api.handle(
        "POST",
        f"/api/sandbox/archives/{archive_id}/resume",
        b"",
    )
    body = _response_json(response)
    return SmokeStep(
        name="archive_resume_plan",
        ok=response.status_code == 200 and body.get("ok") is True,
        status=str(body.get("status") or response.status_code),
        message=str(body.get("message") or "Resume plan checked."),
        details={
            "requiresFreshCredentials": body.get("requiresFreshCredentials"),
            "completedRoundCount": body.get("safeBoundary", {}).get("completedRoundCount"),
            "restoresUcbState": body.get("resumePlan", {}).get("restoresUcbState"),
        },
    )


def _wrong_key_step(root: str) -> SmokeStep:
    def requester(url: str, headers: Mapping[str, str], timeout: float) -> int:
        del url, headers, timeout
        return 401

    api = WebSandboxApi(archive_root=root, provider_probe_requester=requester)
    payload = build_minimal_live_payload(
        SmokeConfig(base_url="https://provider.example/v1", model="demo", api_key="bad-secret")
    )
    response = api.handle("POST", "/api/sandbox/provider-check", _json_body(payload))
    body = _response_json(response)
    message = json.dumps(body, ensure_ascii=False)
    return SmokeStep(
        name="failure_wrong_key",
        ok=response.status_code == 502 and "bad-secret" not in message,
        status=str(body.get("status") or response.status_code),
        message="Wrong-key provider-check fails safely without echoing the key.",
    )


def _wrong_model_step(root: str) -> SmokeStep:
    def requester(url: str, headers: Mapping[str, str], timeout: float) -> int:
        del url, headers, timeout
        return 200

    def model_requester(
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        del url, headers, body, timeout
        return 404, {"error": {"message": "missing model for bad-secret"}}

    api = WebSandboxApi(
        archive_root=root,
        provider_probe_requester=requester,
        provider_model_requester=model_requester,
    )
    payload = build_minimal_live_payload(
        SmokeConfig(base_url="https://provider.example/v1", model="missing-model", api_key="bad-secret")
    )
    response = api.handle("POST", "/api/sandbox/provider-check", _json_body(payload))
    body = _response_json(response)
    message = json.dumps(body, ensure_ascii=False)
    return SmokeStep(
        name="failure_wrong_model",
        ok=response.status_code == 502 and body.get("modelStatus") == "not_callable" and "bad-secret" not in message,
        status=str(body.get("modelStatus") or response.status_code),
        message="Wrong-model provider-check is reported as not callable and redacted.",
    )


def _bad_base_url_step(root: str) -> SmokeStep:
    api = WebSandboxApi(archive_root=root)
    payload = build_minimal_live_payload(
        SmokeConfig(base_url="not-a-url", model="demo", api_key="bad-secret")
    )
    response = api.handle("POST", "/api/sandbox/provider-check", _json_body(payload))
    body = _response_json(response)
    return SmokeStep(
        name="failure_bad_base_url",
        ok=response.status_code == 400 and body.get("status") == "invalid_request",
        status=str(body.get("status") or response.status_code),
        message="Bad Base URL is rejected before any provider call.",
    )


def _runtime_provider_failure_step(root: str) -> SmokeStep:
    def model_requester(
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        del url, headers, body, timeout
        return 500, {"error": {"message": "provider failed for runtime-secret"}}

    api = WebSandboxApi(archive_root=root, model_requester=model_requester)
    payload = build_minimal_live_payload(
        SmokeConfig(base_url="https://provider.example/v1", model="demo", api_key="runtime-secret")
    )
    response = api.handle(
        "POST",
        "/api/sandbox/live-events",
        _json_body(payload),
        headers={"Accept": "application/json", "X-Sandbox-Run-Id": "runtimeFailure"},
    )
    body = _response_json(response)
    message = json.dumps(body, ensure_ascii=False)
    events = body.get("events") if isinstance(body.get("events"), list) else []
    last_event = events[-1] if events and isinstance(events[-1], Mapping) else {}
    issue = last_event.get("issue") if isinstance(last_event.get("issue"), Mapping) else {}
    return SmokeStep(
        name="failure_runtime_provider_error",
        ok=(
            response.status_code == 200
            and body.get("status") == "failed"
            and last_event.get("type") == "run_failed"
            and issue.get("kind") == "runtime_error"
            and "runtime-secret" not in message
        ),
        status=str(issue.get("kind") or body.get("status") or response.status_code),
        message="Runtime provider errors are surfaced as safe run failures.",
    )


def _stop_archive_resume_failure_path_steps(root: str) -> list[SmokeStep]:
    api = WebSandboxApi(archive_root=root)
    run_id = "manualStopSmoke"
    api.lifecycle_manager.register_run(run_id)
    api.lifecycle_manager.append_event(
        run_id,
        {
            "id": "manual-stop-run-started",
            "type": "run_started",
            "round": 0,
            "headline": "Run started",
            "summary": "Manual lifecycle smoke.",
        },
    )
    api.lifecycle_manager.append_event(
        run_id,
        {
            "id": "manual-stop-round-completed",
            "type": "round_completed",
            "round": 1,
            "headline": "Round completed",
            "summary": "Manual safe boundary.",
        },
    )

    stop_body = _response_json(
        api.handle("POST", "/api/sandbox/runs/stop", _json_body({"runId": run_id}))
    )
    save_response = api.handle(
        "POST",
        "/api/sandbox/archives",
        _json_body({"runId": run_id, "label": "Stop smoke archive"}),
    )
    save_body = _response_json(save_response)
    archive_id = str(save_body.get("archive", {}).get("archiveId") or "")
    resume_response = api.handle(
        "POST",
        f"/api/sandbox/archives/{archive_id}/resume",
        b"",
    )
    resume_body = _response_json(resume_response)
    return [
        SmokeStep(
            name="failure_path_user_stop",
            ok=stop_body.get("status") == "stop_requested",
            status=str(stop_body.get("status")),
            message="User stop route accepts the active run id.",
        ),
        SmokeStep(
            name="failure_path_archive_after_stop",
            ok=save_response.status_code == 200 and bool(archive_id),
            status=str(save_body.get("status") or save_response.status_code),
            message="Stopped safe boundary can be archived.",
            details={"archiveId": archive_id},
        ),
        SmokeStep(
            name="failure_path_resume_plan_after_archive",
            ok=resume_response.status_code == 200 and resume_body.get("ok") is True,
            status=str(resume_body.get("status") or resume_response.status_code),
            message="Archive can return a safe resume plan with fresh credentials required.",
        ),
    ]


def _events_from_response(response: WebApiResponse) -> list[dict[str, Any]]:
    if response.is_streaming:
        text = b"".join(response.chunks or ()).decode("utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    body = _response_json(response)
    events = body.get("events")
    if not isinstance(events, list):
        raise TypeError(str(body.get("message") or "live response did not include events"))
    return [event for event in events if isinstance(event, dict)]


def _json_body(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _response_json(response: WebApiResponse) -> dict[str, Any]:
    if response.body:
        payload = json.loads(response.body.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    return {}


def _archive_root(path: str) -> Any:
    if path:
        Path(path).mkdir(parents=True, exist_ok=True)
        return _StaticArchiveRoot(path)
    return tempfile.TemporaryDirectory(prefix="marketing-real-smoke-")


class _StaticArchiveRoot:
    def __init__(self, path: str) -> None:
        self.name = path

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


def _print_report(report: SmokeReport) -> None:
    print(json.dumps(report.public_payload(), ensure_ascii=False, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run marketing sandbox API smoke checks.")
    parser.add_argument(
        "--real",
        action="store_true",
        help=f"Call the external provider. Also enabled by {REAL_SMOKE_FLAG}=1.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help=f"Override provider base URL. API key still comes only from {API_KEY_ENV}.",
    )
    parser.add_argument("--model", default="", help="Override smoke model.")
    parser.add_argument("--provider-id", default="", help="Override provider id.")
    parser.add_argument("--archive-root", default="", help="Keep real smoke archives here.")
    args = parser.parse_args(argv)

    env_config = SmokeConfig.from_env()
    config = SmokeConfig(
        base_url=args.base_url.strip() or env_config.base_url,
        model=args.model.strip() or env_config.model,
        provider_id=args.provider_id.strip() or env_config.provider_id,
        api_key=env_config.api_key,
        archive_root=args.archive_root.strip() or env_config.archive_root,
    )
    run_real = args.real or os.environ.get(REAL_SMOKE_FLAG, "").strip() == "1"
    report = run_smoke_suite(config, run_real=run_real)
    _print_report(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
