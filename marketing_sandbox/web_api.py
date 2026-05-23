"""Local HTTP API surface for the visualization website.

The API class is deliberately framework-neutral.  ``web_server`` can mount it
with the standard library, and tests can call it directly without opening a
port.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

from .llm_backend import (
    ChatCompletionRequester,
    LLMBackendError,
    OpenAICompatibleChatBackend,
    make_openai_compatible_backend_factory,
)
from .web_event_stream import WebRunEventStream, handle_live_event_stream
from .web_lifecycle import (
    WebRunLifecycleManager,
    handle_api_disconnect_timeout,
    handle_archive_continue_request,
    handle_archive_list_request,
    handle_archive_restore_request,
    handle_archive_save_request,
    handle_stop_request,
)
from .web_runner import WebSandboxRunner
from .web_session import (
    BackendDefaults,
    ProbeRequester,
    ROLE_MODEL_KEYS,
    WebProviderRoute,
    WebRunConfigError,
    WebRunSession,
    handle_api_connection_test,
)


DEFAULT_ARCHIVE_ROOT = Path("marketing_sandbox_archives")
DEFAULT_MAX_BODY_BYTES = 2_000_000
_RUN_ID_UNSAFE_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")


class WebApiError(Exception):
    """Raised when an incoming website API request is malformed."""


@dataclass(frozen=True)
class WebApiResponse:
    """Framework-neutral HTTP response returned by ``WebSandboxApi``."""

    status_code: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    chunks: Iterable[bytes] | None = None

    @property
    def is_streaming(self) -> bool:
        """Return whether the response body is an iterator of byte chunks."""

        return self.chunks is not None


class WebSandboxApi:
    """Route website API requests to the web runner and lifecycle helpers."""

    def __init__(
        self,
        *,
        archive_root: str | Path | None = None,
        lifecycle_manager: WebRunLifecycleManager | None = None,
        event_stream: WebRunEventStream | None = None,
        backend_defaults: BackendDefaults = None,
        provider_probe_requester: ProbeRequester | None = None,
        provider_model_requester: ChatCompletionRequester | None = None,
        model_requester: Any | None = None,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        if isinstance(max_body_bytes, bool) or not isinstance(max_body_bytes, int):
            raise WebApiError("max_body_bytes must be an integer.")
        if max_body_bytes < 1:
            raise WebApiError("max_body_bytes must be positive.")
        self.max_body_bytes = max_body_bytes
        self.backend_defaults = dict(backend_defaults or {})
        self.provider_probe_requester = provider_probe_requester
        self.provider_model_requester = provider_model_requester
        self.lifecycle_manager = lifecycle_manager or WebRunLifecycleManager(
            archive_root or DEFAULT_ARCHIVE_ROOT
        )
        self.event_stream = event_stream or self._build_default_event_stream(
            model_requester=model_requester
        )

    def handle(
        self,
        method: str,
        path: str,
        body: bytes = b"",
        headers: Mapping[str, str] | None = None,
    ) -> WebApiResponse:
        """Handle one HTTP-like request and return a response object."""

        request_method = _normalize_method(method)
        request_path = _normalize_path(path)
        request_headers = _normalize_headers(headers or {})
        if len(body or b"") > self.max_body_bytes:
            return self._json_response(
                413,
                {
                    "ok": False,
                    "status": "body_too_large",
                    "message": "Request body is too large.",
                },
            )
        if request_method == "OPTIONS":
            return self._response(204, body=b"")
        try:
            return self._dispatch(request_method, request_path, body or b"", request_headers)
        except WebApiError as error:
            return self._json_response(
                400,
                {
                    "ok": False,
                    "status": "invalid_request",
                    "message": str(error),
                },
            )

    def _dispatch(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
    ) -> WebApiResponse:
        if path == "/api/sandbox/live-events":
            self._require_method(method, "POST")
            return self._handle_live_events(body, headers)
        if path == "/api/sandbox/provider-check":
            self._require_method(method, "POST")
            return self._handle_provider_check(body)
        if path == "/api/sandbox/runs/stop":
            self._require_method(method, "POST")
            return self._handle_stop(body)

        run_stop_match = re.fullmatch(r"/api/sandbox/runs/([^/]+)/stop", path)
        if run_stop_match:
            self._require_method(method, "POST")
            return self._handle_stop(body, run_id=unquote(run_stop_match.group(1)))

        disconnect_match = re.fullmatch(
            r"/api/sandbox/runs/([^/]+)/api-disconnect-timeout",
            path,
        )
        if disconnect_match:
            self._require_method(method, "POST")
            return self._handle_disconnect_timeout(
                body,
                run_id=unquote(disconnect_match.group(1)),
            )

        if path == "/api/sandbox/archives":
            if method == "GET":
                return self._handle_archive_list()
            if method == "POST":
                return self._handle_archive_save(body)
            return self._method_not_allowed(("GET", "POST"))

        archive_match = re.fullmatch(r"/api/sandbox/archives/([^/]+)", path)
        if archive_match:
            self._require_method(method, "GET")
            return self._handle_archive_restore(unquote(archive_match.group(1)))

        resume_match = re.fullmatch(r"/api/sandbox/archives/([^/]+)/resume", path)
        if resume_match:
            self._require_method(method, "POST")
            return self._handle_archive_resume(unquote(resume_match.group(1)), body)

        return self._json_response(
            404,
            {
                "ok": False,
                "status": "not_found",
                "message": f"Unknown sandbox API route: {path}.",
            },
        )

    def _handle_live_events(
        self,
        body: bytes,
        headers: Mapping[str, str],
    ) -> WebApiResponse:
        payload = self._json_body(body)
        try:
            run_id = self._resolve_run_id(payload, headers)
            session = WebRunSession.from_frontend_payload(run_id, payload)
            round_count = self._optional_round_count(payload)
        except WebRunConfigError as error:
            return self._json_response(
                400,
                {
                    "ok": False,
                    "status": "invalid_request",
                    "message": str(error),
                },
            )

        accept = headers.get("accept", "")
        if "text/event-stream" in accept:
            return self._stream_response(
                "text/event-stream; charset=utf-8",
                self.event_stream.iter_sse(
                    session,
                    run_id=run_id,
                    round_count=round_count,
                ),
            )
        if "application/x-ndjson" in accept:
            return self._stream_response(
                "application/x-ndjson; charset=utf-8",
                self.event_stream.iter_json_lines(
                    session,
                    run_id=run_id,
                    round_count=round_count,
                ),
            )

        status_code, response = handle_live_event_stream(
            session,
            self.event_stream,
            run_id=run_id,
            round_count=round_count,
        )
        return self._json_response(status_code, response)

    def _handle_provider_check(self, body: bytes) -> WebApiResponse:
        payload = self._json_body(body)
        status_code, response = handle_api_connection_test(
            payload,
            backend_defaults=self.backend_defaults,
            requester=self.provider_probe_requester,
        )
        if status_code == 200 and response.get("ok") is True:
            model_status, model_response = self._handle_provider_model_check(payload)
            if model_status != 200:
                return self._json_response(
                    model_status,
                    {
                        **response,
                        **model_response,
                        "ok": False,
                    },
                )
            response = {
                **response,
                "modelCheck": model_response,
            }
        return self._json_response(status_code, response)

    def _handle_provider_model_check(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        secret_values = self._provider_check_secret_candidates(payload)
        try:
            provider, session_api_key = self._provider_route_from_payload(payload)
            model = self._provider_check_model(provider)
            base_url, api_key = self._provider_credentials(provider, session_api_key)
            backend = OpenAICompatibleChatBackend(
                base_url=base_url,
                api_key=api_key,
                model=model,
                role="provider-check",
                timeout_seconds=15.0,
                max_retries=0,
                requester=self.provider_model_requester,
            )
            backend.generate("Reply with the word ok.")
        except (WebApiError, WebRunConfigError) as error:
            return 400, {
                "status": "invalid_request",
                "modelStatus": "configuration_required",
                "message": self._redact_text(str(error), secret_values),
            }
        except LLMBackendError as error:
            return 502, {
                "status": "provider_model_error",
                "modelStatus": "not_callable",
                "message": self._redact_text(str(error), secret_values),
            }
        return 200, {
            "ok": True,
            "modelStatus": "callable",
            "message": "Provider model check succeeded.",
        }

    def _handle_stop(self, body: bytes, *, run_id: str = "") -> WebApiResponse:
        payload = self._json_body(body, empty_ok=True)
        if run_id:
            payload = {**payload, "runId": run_id}
        status_code, response = handle_stop_request(payload, self.lifecycle_manager)
        return self._json_response(status_code, response)

    def _handle_archive_list(self) -> WebApiResponse:
        status_code, response = handle_archive_list_request(self.lifecycle_manager)
        return self._json_response(status_code, response)

    def _handle_archive_save(self, body: bytes) -> WebApiResponse:
        status_code, response = handle_archive_save_request(
            self._json_body(body),
            self.lifecycle_manager,
        )
        return self._json_response(status_code, response)

    def _handle_archive_restore(self, archive_id: str) -> WebApiResponse:
        status_code, response = handle_archive_restore_request(
            {"archiveId": archive_id},
            self.lifecycle_manager,
        )
        return self._json_response(status_code, response)

    def _handle_archive_resume(self, archive_id: str, body: bytes) -> WebApiResponse:
        payload = self._json_body(body, empty_ok=True)
        payload = {**payload, "archiveId": archive_id}
        status_code, response = handle_archive_continue_request(
            payload,
            self.lifecycle_manager,
        )
        return self._json_response(status_code, response)

    def _handle_disconnect_timeout(
        self,
        body: bytes,
        *,
        run_id: str = "",
    ) -> WebApiResponse:
        payload = self._json_body(body, empty_ok=True)
        if run_id:
            payload = {**payload, "runId": run_id}
        status_code, response = handle_api_disconnect_timeout(
            payload,
            self.lifecycle_manager,
        )
        return self._json_response(status_code, response)

    def _json_body(self, body: bytes, *, empty_ok: bool = False) -> dict[str, Any]:
        if not body:
            if empty_ok:
                return {}
            raise WebApiError("Request body must be JSON.")
        try:
            payload = json.loads(body.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise WebApiError("Request body must be UTF-8 JSON.") from error
        except json.JSONDecodeError as error:
            raise WebApiError("Request body is not valid JSON.") from error
        if not isinstance(payload, Mapping):
            raise WebApiError("Request body JSON must be an object.")
        return dict(payload)

    def _provider_route_from_payload(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[WebProviderRoute, str]:
        request_payload = self._require_mapping(payload, "provider-check payload")
        if "provider" in request_payload:
            provider_payload = self._require_mapping(
                request_payload.get("provider"),
                "provider",
            )
            models_payload = self._require_mapping(
                request_payload.get("models") or {},
                "models",
            )
        else:
            provider_payload = request_payload
            models_payload = self._require_mapping(
                request_payload.get("models") or {},
                "models",
            )
        provider = WebProviderRoute.from_frontend_payload(
            provider_payload,
            models_payload,
        )
        provider.require_live_ready()
        session_api_key = provider_payload.get("apiKey", "")
        if not isinstance(session_api_key, str):
            raise WebApiError("provider.apiKey must be text.")
        return provider, session_api_key.strip()

    def _provider_credentials(
        self,
        provider: WebProviderRoute,
        session_api_key: str,
    ) -> tuple[str, str]:
        base_url = provider.base_url
        api_key = session_api_key
        if provider.use_backend_defaults:
            base_url = base_url or self._optional_text(
                self.backend_defaults.get("base_url", ""),
                "backend_defaults.base_url",
            )
            api_key = self._optional_text(
                self.backend_defaults.get("api_key", ""),
                "backend_defaults.api_key",
            )
        if not base_url:
            raise WebApiError("Provider model check needs a Base URL.")
        if not api_key:
            raise WebApiError("Provider model check needs an API key.")
        return base_url, api_key

    @staticmethod
    def _provider_check_model(provider: WebProviderRoute) -> str:
        if provider.default_model:
            return provider.default_model
        for role in ROLE_MODEL_KEYS:
            model = provider.role_models.get(role)
            if model:
                return model
        raise WebApiError("Provider model check needs a model name.")

    def _provider_check_secret_candidates(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[str, ...]:
        candidates: list[str] = []
        provider_payload: Any = payload.get("provider", payload)
        if isinstance(provider_payload, Mapping):
            api_key = provider_payload.get("apiKey")
            if isinstance(api_key, str) and api_key.strip():
                candidates.append(api_key.strip())
        default_key = self.backend_defaults.get("api_key")
        if isinstance(default_key, str) and default_key.strip():
            candidates.append(default_key.strip())
        return tuple(candidates)

    @staticmethod
    def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise WebApiError(f"{label} must be an object.")
        return value

    @staticmethod
    def _optional_text(value: Any, label: str) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise WebApiError(f"{label} must be text.")
        return value.strip()

    @staticmethod
    def _redact_text(text: str, secret_values: Sequence[str]) -> str:
        safe_text = text
        for secret in secret_values:
            if secret:
                safe_text = safe_text.replace(secret, "[redacted]")
        return safe_text

    def _resolve_run_id(
        self,
        payload: Mapping[str, Any],
        headers: Mapping[str, str],
    ) -> str:
        candidate = headers.get("x-sandbox-run-id") or payload.get("runId") or "live-run"
        if not isinstance(candidate, str):
            raise WebApiError("runId must be text.")
        token = _RUN_ID_UNSAFE_PATTERN.sub("-", candidate.strip()).strip("-_")
        token = token[:80].strip("-_")
        return token or "live-run"

    @staticmethod
    def _optional_round_count(payload: Mapping[str, Any]) -> int | None:
        value = payload.get("roundCount", payload.get("round_count"))
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise WebApiError("roundCount must be an integer.")
        if value < 1:
            raise WebApiError("roundCount must be positive.")
        return value

    def _stream_response(
        self,
        content_type: str,
        chunks: Iterable[str],
    ) -> WebApiResponse:
        def encoded() -> Iterable[bytes]:
            for chunk in chunks:
                yield chunk.encode("utf-8")

        return self._response(
            200,
            headers={
                "Content-Type": content_type,
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
            chunks=encoded(),
        )

    def _json_response(self, status_code: int, payload: Mapping[str, Any]) -> WebApiResponse:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        return self._response(
            status_code,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
        )

    def _response(
        self,
        status_code: int,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
        chunks: Iterable[bytes] | None = None,
    ) -> WebApiResponse:
        response_headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": (
                "Content-Type, Accept, X-Sandbox-Run-Id"
            ),
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }
        response_headers.update(dict(headers or {}))
        return WebApiResponse(
            status_code=status_code,
            headers=response_headers,
            body=body,
            chunks=chunks,
        )

    def _require_method(self, actual: str, expected: str) -> None:
        if actual != expected:
            raise WebApiError(f"Route requires {expected}.")

    def _method_not_allowed(self, allowed: tuple[str, ...]) -> WebApiResponse:
        return self._json_response(
            405,
            {
                "ok": False,
                "status": "method_not_allowed",
                "message": f"Allowed methods: {', '.join(allowed)}.",
            },
        )

    def _build_default_event_stream(
        self,
        *,
        model_requester: Any | None,
    ) -> WebRunEventStream:
        backend_factory = make_openai_compatible_backend_factory(
            backend_defaults=self.backend_defaults,
            requester=model_requester,
        )
        return WebRunEventStream(
            WebSandboxRunner(backend_factory),
            lifecycle_manager=self.lifecycle_manager,
        )


def _normalize_method(method: str) -> str:
    if not isinstance(method, str) or not method.strip():
        raise WebApiError("HTTP method must be text.")
    return method.strip().upper()


def _normalize_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise WebApiError("Request path must be text.")
    parsed = urlsplit(path)
    route_path = parsed.path.rstrip("/") or "/"
    return route_path


def _normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in headers.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, str):
            normalized[key.lower()] = value
        else:
            normalized[key.lower()] = str(value)
    return normalized
