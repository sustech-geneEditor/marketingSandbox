"""Provider adapters that turn sandbox prompts into model text responses.

The core agents only need a backend with ``generate(prompt)``. This module
keeps provider HTTP details, retry policy, cancellation checks, and secret
redaction outside those agent classes.
"""

from __future__ import annotations

import json
import math
import socket
import time
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

from .web_session import BackendDefaults, ROLE_MODEL_KEYS, WebRunSession


ChatCompletionPayload = bytes | str | Mapping[str, Any]
ChatCompletionRequester = Callable[
    [str, Mapping[str, str], bytes, float],
    tuple[int, ChatCompletionPayload],
]
CancellationCheck = Callable[[], bool]
Sleeper = Callable[[float], None]

_MAX_RESPONSE_BYTES = 4_000_000
_RETRYABLE_HTTP_STATUSES = frozenset({408, 409, 425, 429})


class LLMTextBackend(Protocol):
    """Minimal model backend shared by all LLM-backed sandbox roles."""

    def generate(self, prompt: str) -> str:
        """Return one text response for the supplied role prompt."""


class LLMBackendError(Exception):
    """Base error for live model adapter failures."""


class LLMBackendConfigurationError(LLMBackendError):
    """Raised when a provider adapter lacks a safe runnable configuration."""


class LLMBackendCancelledError(LLMBackendError):
    """Raised when a caller asks a provider adapter to stop before a request."""


class LLMBackendTransportError(LLMBackendError):
    """Raised when a provider cannot be reached over the configured transport."""


class LLMBackendTimeoutError(LLMBackendTransportError):
    """Raised when a provider request times out."""


class LLMBackendResponseError(LLMBackendError):
    """Raised when a provider response cannot become role output text."""


class LLMBackendProviderError(LLMBackendError):
    """Raised when a provider returns an HTTP error response."""

    def __init__(self, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMBackendAuthenticationError(LLMBackendProviderError):
    """Raised when an API key is rejected by a provider."""


class LLMBackendRateLimitError(LLMBackendProviderError):
    """Raised when a provider refuses a request because of rate pressure."""


class LLMBackendModelError(LLMBackendProviderError):
    """Raised when a configured model or completion endpoint is unavailable."""


class OpenAICompatibleChatBackend:
    """Text backend for providers exposing OpenAI-style chat completions.

    Inputs are one prompt, a provider base URL, an API key, and a model route.
    Output is only the assistant text that the existing role parsers already
    expect. The adapter never places the API key in its ``repr`` or raised
    error text.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        role: str = "",
        timeout_seconds: float = 45.0,
        max_retries: int = 8,
        retry_backoff_seconds: float = 0.0,
        requester: ChatCompletionRequester | None = None,
        cancellation_check: CancellationCheck | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        self.base_url = _require_http_base_url(base_url)
        self.chat_completions_url = _build_chat_completions_url(self.base_url)
        self._api_key = _require_text(api_key, "api_key")
        self.model = _require_text(model, "model")
        self.role = _optional_text(role, "role")
        self.timeout_seconds = _require_positive_float(
            timeout_seconds,
            "timeout_seconds",
        )
        self.max_retries = _require_non_negative_int(max_retries, "max_retries")
        self.retry_backoff_seconds = _require_non_negative_float(
            retry_backoff_seconds,
            "retry_backoff_seconds",
        )
        self._requester = requester or _request_chat_completion
        self._cancellation_check = cancellation_check
        self._sleeper = sleeper or time.sleep

    def __repr__(self) -> str:
        """Describe the public route without echoing a provider secret."""

        return (
            "OpenAICompatibleChatBackend("
            f"model={self.model!r}, "
            f"role={self.role!r}, "
            f"chat_completions_url={self.chat_completions_url!r})"
        )

    def generate(self, prompt: str) -> str:
        """Generate text with bounded retries and categorized live errors."""

        clean_prompt = _require_prompt_text(prompt)
        body = self._build_request_body(clean_prompt)
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        secret_values = (self._api_key,)
        for attempt in range(self.max_retries + 1):
            self._raise_if_cancelled()
            try:
                status_code, payload = self._requester(
                    self.chat_completions_url,
                    headers,
                    body,
                    self.timeout_seconds,
                )
            except HTTPError as error:
                status_code = int(error.code)
                payload = _read_http_error_payload(error)
            except (TimeoutError, socket.timeout) as error:
                failure = LLMBackendTimeoutError(
                    _redact_text(f"Provider request timed out: {error}", secret_values)
                )
                if self._can_retry_transport(attempt):
                    self._sleep_before_retry(attempt)
                    continue
                raise failure from error
            except URLError as error:
                failure = self._transport_error_from_url_error(error, secret_values)
                if self._can_retry_transport(attempt):
                    self._sleep_before_retry(attempt)
                    continue
                raise failure from error
            except LLMBackendError:
                raise
            except Exception as error:  # noqa: BLE001 - provider transports vary.
                failure = LLMBackendTransportError(
                    _redact_text(
                        f"Provider request failed before a response: {error}",
                        secret_values,
                    )
                )
                if self._can_retry_transport(attempt):
                    self._sleep_before_retry(attempt)
                    continue
                raise failure from error

            if isinstance(status_code, bool) or not isinstance(status_code, int):
                raise LLMBackendResponseError(
                    "Provider completion transport returned an invalid HTTP status."
                )
            if 200 <= status_code < 300:
                return _extract_assistant_text(payload)

            provider_error = _provider_error_for_status(
                status_code,
                payload,
                secret_values,
            )
            if _is_retryable_status(status_code) and attempt < self.max_retries:
                self._sleep_before_retry(attempt)
                continue
            raise provider_error

        raise LLMBackendTransportError("Provider retry loop ended unexpectedly.")

    def _build_request_body(self, prompt: str) -> bytes:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    def _raise_if_cancelled(self) -> None:
        if self._cancellation_check and self._cancellation_check():
            raise LLMBackendCancelledError(
                "Provider request cancelled before the next safe request."
            )

    def _sleep_before_retry(self, attempt: int) -> None:
        self._raise_if_cancelled()
        delay = self.retry_backoff_seconds * (2**attempt)
        if delay:
            self._sleeper(delay)

    def _can_retry_transport(self, attempt: int) -> bool:
        return attempt < self.max_retries

    @staticmethod
    def _transport_error_from_url_error(
        error: URLError,
        secret_values: Sequence[str],
    ) -> LLMBackendTransportError:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            return LLMBackendTimeoutError(
                _redact_text(f"Provider request timed out: {error}", secret_values)
            )
        return LLMBackendTransportError(
            _redact_text(f"Provider base URL could not be reached: {error}", secret_values)
        )


def openai_compatible_backend_factory(
    *,
    role: str,
    model: str,
    session: WebRunSession,
    persona: Any = None,
    backend_defaults: BackendDefaults = None,
    requester: ChatCompletionRequester | None = None,
    timeout_seconds: float = 45.0,
    max_retries: int = 8,
    retry_backoff_seconds: float = 0.0,
    cancellation_check: CancellationCheck | None = None,
    sleeper: Sleeper | None = None,
) -> OpenAICompatibleChatBackend:
    """Build a live role backend from one validated website session."""

    del persona
    clean_role = _require_text(role, "role")
    if clean_role not in ROLE_MODEL_KEYS:
        raise LLMBackendConfigurationError(f"Unknown live model role: {clean_role}.")
    if not isinstance(session, WebRunSession) or session.config.source != "live":
        raise LLMBackendConfigurationError(
            "OpenAI-compatible backends need a live WebRunSession."
        )
    defaults = _require_mapping(backend_defaults or {}, "backend_defaults")
    provider = session.config.provider
    base_url = provider.base_url
    api_key = session.session_api_key_for_backend()
    if provider.use_backend_defaults:
        base_url = base_url or _optional_text(defaults.get("base_url"), "base_url")
        api_key = _optional_text(defaults.get("api_key"), "api_key")
    return OpenAICompatibleChatBackend(
        base_url=base_url,
        api_key=api_key,
        model=model,
        role=clean_role,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_seconds=retry_backoff_seconds,
        requester=requester,
        cancellation_check=cancellation_check,
        sleeper=sleeper,
    )


def make_openai_compatible_backend_factory(
    *,
    backend_defaults: BackendDefaults = None,
    requester: ChatCompletionRequester | None = None,
    timeout_seconds: float = 45.0,
    max_retries: int = 8,
    retry_backoff_seconds: float = 0.0,
    cancellation_check: CancellationCheck | None = None,
    sleeper: Sleeper | None = None,
) -> Callable[..., OpenAICompatibleChatBackend]:
    """Bind transport and default credential choices for a future Web runner."""

    defaults = dict(_require_mapping(backend_defaults or {}, "backend_defaults"))

    def factory(
        *,
        role: str,
        model: str,
        session: WebRunSession,
        persona: Any = None,
    ) -> OpenAICompatibleChatBackend:
        return openai_compatible_backend_factory(
            role=role,
            model=model,
            session=session,
            persona=persona,
            backend_defaults=defaults,
            requester=requester,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
            cancellation_check=cancellation_check,
            sleeper=sleeper,
        )

    return factory


def _request_chat_completion(
    url: str,
    headers: Mapping[str, str],
    body: bytes,
    timeout_seconds: float,
) -> tuple[int, bytes]:
    request = Request(url, data=body, headers=dict(headers), method="POST")
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        payload = response.read(_MAX_RESPONSE_BYTES + 1)
        return int(getattr(response, "status", 200)), payload


def _extract_assistant_text(payload: ChatCompletionPayload) -> str:
    response = _load_json_object(payload)
    choices = response.get("choices")
    if isinstance(choices, (str, bytes)) or not isinstance(choices, Sequence):
        raise LLMBackendResponseError("Provider completion response needs choices.")
    if not choices or not isinstance(choices[0], Mapping):
        raise LLMBackendResponseError("Provider completion response has no first choice.")
    message = choices[0].get("message")
    if not isinstance(message, Mapping):
        raise LLMBackendResponseError("Provider completion choice needs a message.")
    content = _content_to_text(message.get("content"))
    if not content:
        raise LLMBackendResponseError("Provider completion returned empty assistant text.")
    return content


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, Mapping):
                text = part.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts).strip()
    return ""


def _provider_error_for_status(
    status_code: int,
    payload: ChatCompletionPayload,
    secret_values: Sequence[str],
) -> LLMBackendProviderError:
    detail = _provider_error_detail(payload, secret_values)
    suffix = f" Detail: {detail}" if detail else ""
    if status_code in {401, 403}:
        return LLMBackendAuthenticationError(
            f"Provider rejected API credentials with HTTP {status_code}.{suffix}",
            status_code=status_code,
        )
    if status_code == 429:
        return LLMBackendRateLimitError(
            f"Provider rate limit blocked completion with HTTP {status_code}.{suffix}",
            status_code=status_code,
        )
    if status_code == 404:
        return LLMBackendModelError(
            f"Provider could not find the model or endpoint with HTTP {status_code}.{suffix}",
            status_code=status_code,
        )
    if status_code >= 500:
        return LLMBackendProviderError(
            f"Provider server failed completion with HTTP {status_code}.{suffix}",
            status_code=status_code,
        )
    return LLMBackendProviderError(
        f"Provider refused completion with HTTP {status_code}.{suffix}",
        status_code=status_code,
    )


def _provider_error_detail(
    payload: ChatCompletionPayload,
    secret_values: Sequence[str],
) -> str:
    try:
        response = _load_json_object(payload)
    except LLMBackendResponseError:
        return ""
    raw_error = response.get("error")
    candidates: list[Any] = []
    if isinstance(raw_error, Mapping):
        candidates.extend((raw_error.get("message"), raw_error.get("type")))
    candidates.append(response.get("message"))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            detail = _redact_text(candidate.strip(), secret_values)
            return detail[:240]
    return ""


def _load_json_object(payload: ChatCompletionPayload) -> Mapping[str, Any]:
    if isinstance(payload, Mapping):
        return payload
    if isinstance(payload, bytes):
        if len(payload) > _MAX_RESPONSE_BYTES:
            raise LLMBackendResponseError("Provider completion response is too large.")
        text = payload.decode("utf-8", errors="replace")
    elif isinstance(payload, str):
        text = payload
    else:
        raise LLMBackendResponseError("Provider completion payload must be JSON text.")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMBackendResponseError(
            "Provider completion response is not valid JSON."
        ) from error
    if not isinstance(parsed, Mapping):
        raise LLMBackendResponseError("Provider completion response must be an object.")
    return parsed


def _read_http_error_payload(error: HTTPError) -> bytes:
    try:
        return error.read(_MAX_RESPONSE_BYTES + 1)
    except Exception:  # noqa: BLE001 - not every fake HTTPError has a body.
        return b""


def _build_chat_completions_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    path = parts.path.rstrip("/")
    if not path.endswith("/chat/completions"):
        path = f"{path}/chat/completions" if path else "/chat/completions"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _is_retryable_status(status_code: int) -> bool:
    return status_code in _RETRYABLE_HTTP_STATUSES or status_code >= 500


def _redact_text(text: str, secret_values: Sequence[str]) -> str:
    safe_text = text
    for secret in secret_values:
        if secret:
            safe_text = safe_text.replace(secret, "[redacted]")
    return safe_text


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LLMBackendConfigurationError(f"{label} must be a mapping.")
    return value


def _require_text(value: Any, label: str) -> str:
    text = _optional_text(value, label)
    if not text:
        raise LLMBackendConfigurationError(f"{label} must be non-empty text.")
    return text


def _require_prompt_text(value: Any) -> str:
    if not isinstance(value, str):
        raise LLMBackendConfigurationError("prompt must be text.")
    if not value.strip():
        raise LLMBackendConfigurationError("prompt must be non-empty text.")
    return value


def _optional_text(value: Any, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LLMBackendConfigurationError(f"{label} must be text.")
    return value.strip()


def _require_http_base_url(value: Any) -> str:
    base_url = _require_text(value, "base_url")
    parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise LLMBackendConfigurationError("base_url must be an HTTP(S) URL.")
    if parts.username or parts.password:
        raise LLMBackendConfigurationError("base_url must not embed credentials.")
    if parts.query or parts.fragment:
        raise LLMBackendConfigurationError(
            "base_url must not carry query or fragment text."
        )
    return base_url


def _require_positive_float(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        raise LLMBackendConfigurationError(f"{label} must be a positive finite number.")
    return float(value)


def _require_non_negative_float(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value < 0
    ):
        raise LLMBackendConfigurationError(
            f"{label} must be a non-negative finite number."
        )
    return float(value)


def _require_non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LLMBackendConfigurationError(f"{label} must be a non-negative integer.")
    return value
