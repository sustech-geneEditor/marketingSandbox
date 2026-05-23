"""Web-facing session configuration and provider connection checks.

This module keeps browser run configuration outside the core sandbox classes.
It also keeps a session API key out of public snapshots so later web runners and
archive stores have a safe handoff point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


RUN_SOURCES = frozenset({"fixture", "live"})
PROVIDER_IDS = frozenset({"openai-compatible", "deepseek-compatible"})
ROLE_MODEL_KEYS = ("decision", "consumers", "synthesizer", "critic")
ACTION_CATEGORIES = frozenset(
    {"Positioning", "Product", "Price", "Channel", "Promotion", "Retention"}
)
_MODEL_ROUTE_KEYS = frozenset(ROLE_MODEL_KEYS)

BackendDefaults = Mapping[str, Any] | None
ProbeRequester = Callable[[str, Mapping[str, str], float], int]


class WebSessionError(Exception):
    """Base error for web-facing sandbox session configuration."""


class WebRunConfigError(WebSessionError):
    """Raised when a browser run config cannot become backend data."""


@dataclass(frozen=True)
class WebProviderRoute:
    """Non-secret model-provider route selected in the website config."""

    provider_id: str
    base_url: str = ""
    default_model: str = ""
    role_models: Mapping[str, str] = field(default_factory=dict)
    use_backend_defaults: bool = False

    def __post_init__(self) -> None:
        provider_id = _require_text(self.provider_id, "provider.id")
        if provider_id not in PROVIDER_IDS:
            raise WebRunConfigError("provider.id is not supported.")
        object.__setattr__(self, "provider_id", provider_id)

        base_url = _optional_text(self.base_url, "provider.baseUrl")
        if base_url:
            _validate_base_url(base_url, "provider.baseUrl")
        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(
            self,
            "default_model",
            _optional_text(self.default_model, "provider.defaultModel"),
        )
        object.__setattr__(
            self,
            "use_backend_defaults",
            _require_bool(self.use_backend_defaults, "provider.useBackendDefaults"),
        )
        role_models = _require_mapping(self.role_models, "models")
        unknown_roles = set(role_models) - _MODEL_ROUTE_KEYS
        if unknown_roles:
            raise WebRunConfigError("models contains an unsupported role route.")
        cleaned_models = {
            role: _require_text(model, f"models.{role}")
            for role, model in role_models.items()
            if model is not None and _optional_text(model, f"models.{role}")
        }
        object.__setattr__(self, "role_models", MappingProxyType(cleaned_models))

    @classmethod
    def from_frontend_payload(
        cls,
        provider_payload: Mapping[str, Any] | None,
        models_payload: Mapping[str, Any] | None = None,
    ) -> "WebProviderRoute":
        """Build a non-secret route from the website provider controls."""

        provider = _require_mapping(provider_payload or {}, "provider")
        models = _require_mapping(models_payload or {}, "models")
        return cls(
            provider_id=provider.get("id", "openai-compatible"),
            base_url=provider.get("baseUrl", ""),
            default_model=provider.get("defaultModel", ""),
            use_backend_defaults=provider.get("useBackendDefaults", False),
            role_models=models,
        )

    @property
    def has_model_route(self) -> bool:
        """Return whether a default model or all role models are available."""

        if self.default_model:
            return True
        return all(self.role_models.get(role) for role in ROLE_MODEL_KEYS)

    def require_live_ready(self) -> None:
        """Check the provider route fields needed before a live run."""

        if not self.use_backend_defaults and not self.base_url:
            raise WebRunConfigError(
                "live provider needs provider.baseUrl or backend defaults."
            )
        if not self.has_model_route:
            raise WebRunConfigError(
                "live provider needs a default model or every role model route."
            )

    def public_snapshot(self) -> dict[str, Any]:
        """Return provider routing data that is safe for logs and archives."""

        return {
            "id": self.provider_id,
            "baseUrl": self.base_url,
            "defaultModel": self.default_model,
            "useBackendDefaults": self.use_backend_defaults,
            "models": dict(self.role_models),
        }


@dataclass(frozen=True)
class WebRunConfig:
    """Validated browser config waiting for a future web sandbox runner."""

    source: str
    provider: WebProviderRoute
    product_name: str
    brand_facts: str
    product_facts: str
    marketing_goal: str
    persona_ids: tuple[str, ...]
    scenario_id: str
    action_categories: tuple[str, ...]
    use_ucb: bool
    rounds: int
    candidates_per_round: int
    family_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        source = _require_text(self.source, "source")
        if source not in RUN_SOURCES:
            raise WebRunConfigError("source must be fixture or live.")
        object.__setattr__(self, "source", source)
        if not isinstance(self.provider, WebProviderRoute):
            raise WebRunConfigError("provider must be a WebProviderRoute.")
        for field_name, label in (
            ("product_name", "product.name"),
            ("product_facts", "product.facts"),
            ("marketing_goal", "product.goal"),
            ("scenario_id", "scenarioId"),
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(getattr(self, field_name), label),
            )
        object.__setattr__(
            self,
            "brand_facts",
            _optional_text(self.brand_facts, "product.brand"),
        )
        object.__setattr__(
            self,
            "persona_ids",
            _require_text_items(self.persona_ids, "personaIds"),
        )
        action_categories = _require_text_items(
            self.action_categories, "actionCategories"
        )
        if any(category not in ACTION_CATEGORIES for category in action_categories):
            raise WebRunConfigError("actionCategories contains an unsupported category.")
        object.__setattr__(self, "action_categories", action_categories)
        object.__setattr__(self, "use_ucb", _require_bool(self.use_ucb, "search.useUcb"))
        object.__setattr__(
            self,
            "rounds",
            _require_int_range(self.rounds, "search.rounds", minimum=1, maximum=24),
        )
        object.__setattr__(
            self,
            "candidates_per_round",
            _require_int_range(
                self.candidates_per_round,
                "search.candidatesPerRound",
                minimum=1,
                maximum=4,
            ),
        )
        family_ids = _optional_text_items(self.family_ids, "search.familyIds")
        if self.use_ucb and not family_ids:
            raise WebRunConfigError("search.familyIds is required when UCB is enabled.")
        object.__setattr__(self, "family_ids", family_ids)
        if self.source == "live":
            self.provider.require_live_ready()

    @classmethod
    def from_frontend_payload(cls, payload: Mapping[str, Any]) -> "WebRunConfig":
        """Parse the current frontend run-config payload."""

        run_payload = _require_mapping(payload, "run config")
        product = _require_mapping(run_payload.get("product"), "product")
        search = _require_mapping(run_payload.get("search"), "search")
        return cls(
            source=run_payload.get("source"),
            provider=WebProviderRoute.from_frontend_payload(
                run_payload.get("provider"),
                run_payload.get("models"),
            ),
            product_name=product.get("name"),
            brand_facts=product.get("brand", ""),
            product_facts=product.get("facts"),
            marketing_goal=product.get("goal"),
            persona_ids=run_payload.get("personaIds"),
            scenario_id=run_payload.get("scenarioId"),
            action_categories=run_payload.get("actionCategories"),
            use_ucb=search.get("useUcb"),
            rounds=search.get("rounds"),
            candidates_per_round=search.get("candidatesPerRound"),
            family_ids=search.get("familyIds", ()),
        )

    def public_snapshot(self) -> dict[str, Any]:
        """Return the non-secret config payload for logs, exports, or archives."""

        return {
            "source": self.source,
            "provider": self.provider.public_snapshot(),
            "product": {
                "name": self.product_name,
                "brand": self.brand_facts,
                "facts": self.product_facts,
                "goal": self.marketing_goal,
            },
            "personaIds": list(self.persona_ids),
            "scenarioId": self.scenario_id,
            "actionCategories": list(self.action_categories),
            "search": {
                "useUcb": self.use_ucb,
                "rounds": self.rounds,
                "candidatesPerRound": self.candidates_per_round,
                "familyIds": list(self.family_ids),
            },
        }


class WebRunSession:
    """One website session with live credentials kept outside public config."""

    def __init__(
        self,
        session_id: str,
        config: WebRunConfig,
        *,
        session_api_key: str = "",
    ) -> None:
        self.session_id = _require_text(session_id, "session_id")
        if not isinstance(config, WebRunConfig):
            raise WebRunConfigError("config must be a WebRunConfig.")
        self.config = config
        self._session_api_key = _optional_text(session_api_key, "provider.apiKey")
        if self.config.source != "live" or self.config.provider.use_backend_defaults:
            self._session_api_key = ""
        if (
            self.config.source == "live"
            and not self.config.provider.use_backend_defaults
            and not self._session_api_key
        ):
            raise WebRunConfigError(
                "live provider needs a session API key or backend defaults."
            )

    def __repr__(self) -> str:
        """Describe the session without echoing a plaintext API key."""

        return (
            "WebRunSession("
            f"session_id={self.session_id!r}, "
            f"source={self.config.source!r}, "
            f"credential_source={self.credential_source!r})"
        )

    @classmethod
    def from_frontend_payload(
        cls,
        session_id: str,
        payload: Mapping[str, Any],
    ) -> "WebRunSession":
        """Create a web session while splitting session secrets from config."""

        run_payload = _require_mapping(payload, "run config")
        provider_payload = _require_mapping(run_payload.get("provider") or {}, "provider")
        return cls(
            session_id,
            WebRunConfig.from_frontend_payload(run_payload),
            session_api_key=_extract_session_api_key(provider_payload),
        )

    @property
    def has_session_api_key(self) -> bool:
        """Return whether this live session carries a temporary user key."""

        return bool(self._session_api_key)

    @property
    def credential_source(self) -> str:
        """Return a safe label for where provider credentials should come from."""

        if self.config.source != "live":
            return "not_required"
        if self.config.provider.use_backend_defaults:
            return "backend_defaults"
        if self._session_api_key:
            return "session_key"
        return "missing"

    def secret_values_for_redaction(self) -> tuple[str, ...]:
        """Return session-only secrets that downstream web payloads must redact."""

        return (self._session_api_key,) if self._session_api_key else ()

    def session_api_key_for_backend(self) -> str:
        """Return the session-only key to a local live backend adapter.

        Public snapshots, archives, and event payloads must keep using the
        redaction helpers instead of this credential handoff.
        """

        return self._session_api_key

    def public_snapshot(self) -> dict[str, Any]:
        """Return safe session data for the UI, logs, and future archives."""

        return {
            "sessionId": self.session_id,
            "credentialSource": self.credential_source,
            "sessionKeyPresent": self.has_session_api_key,
            "config": self.config.public_snapshot(),
        }


@dataclass(frozen=True)
class ApiConnectionTestResult:
    """Public result of one provider connection check."""

    ok: bool
    status: str
    provider_id: str
    message: str
    models_url: str = ""

    def public_payload(self) -> dict[str, Any]:
        """Return the JSON-safe connection-test response body."""

        return {
            "ok": self.ok,
            "status": self.status,
            "providerId": self.provider_id,
            "message": self.message,
            "modelsUrl": self.models_url,
        }


def probe_api_connection(
    provider: WebProviderRoute,
    *,
    session_api_key: str = "",
    backend_defaults: BackendDefaults = None,
    requester: ProbeRequester | None = None,
    timeout_seconds: float = 5.0,
) -> ApiConnectionTestResult:
    """Test an OpenAI-compatible provider models endpoint safely."""

    if not isinstance(provider, WebProviderRoute):
        raise WebRunConfigError("provider must be a WebProviderRoute.")
    provider.require_live_ready()
    timeout = _require_timeout(timeout_seconds)
    session_key = _optional_text(session_api_key, "provider.apiKey")
    defaults = _require_mapping(backend_defaults or {}, "backend defaults")
    default_base_url = _optional_text(defaults.get("base_url", ""), "default.base_url")
    default_api_key = _optional_text(defaults.get("api_key", ""), "default.api_key")
    base_url = provider.base_url
    api_key = session_key
    if provider.use_backend_defaults:
        base_url = base_url or default_base_url
        api_key = default_api_key
    if not base_url:
        return ApiConnectionTestResult(
            ok=False,
            status="configuration_required",
            provider_id=provider.provider_id,
            message="Provider connection needs a Base URL.",
        )
    _validate_base_url(base_url, "connection base URL")
    if not api_key:
        return ApiConnectionTestResult(
            ok=False,
            status="configuration_required",
            provider_id=provider.provider_id,
            message="Provider connection needs an API key.",
        )

    models_url = _build_models_url(base_url)
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    request = requester or _request_models_endpoint
    secret_values = tuple(item for item in (session_key, default_api_key) if item)
    try:
        status_code = request(models_url, headers, timeout)
    except HTTPError as error:
        status_code = error.code
    except Exception as error:  # noqa: BLE001 - external transports vary.
        return ApiConnectionTestResult(
            ok=False,
            status="request_failed",
            provider_id=provider.provider_id,
            message=_redact_text(f"Provider request failed: {error}", secret_values),
            models_url=models_url,
        )
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        return ApiConnectionTestResult(
            ok=False,
            status="request_failed",
            provider_id=provider.provider_id,
            message="Provider test returned an invalid HTTP status.",
            models_url=models_url,
        )
    if 200 <= status_code < 300:
        return ApiConnectionTestResult(
            ok=True,
            status="connected",
            provider_id=provider.provider_id,
            message="Provider connection test succeeded.",
            models_url=models_url,
        )
    return ApiConnectionTestResult(
        ok=False,
        status="provider_error",
        provider_id=provider.provider_id,
        message=f"Provider replied with HTTP {status_code}.",
        models_url=models_url,
    )


def handle_api_connection_test(
    payload: Mapping[str, Any],
    *,
    backend_defaults: BackendDefaults = None,
    requester: ProbeRequester | None = None,
) -> tuple[int, dict[str, Any]]:
    """Framework-neutral handler for the future connection-test route."""

    secret_values = _connection_secret_candidates(payload, backend_defaults)
    try:
        route, session_api_key = _provider_route_from_connection_payload(payload)
        result = probe_api_connection(
            route,
            session_api_key=session_api_key,
            backend_defaults=backend_defaults,
            requester=requester,
        )
    except WebRunConfigError as error:
        return 400, {
            "ok": False,
            "status": "invalid_request",
            "message": _redact_text(str(error), secret_values),
        }

    if result.ok:
        status_code = 200
    elif result.status == "configuration_required":
        status_code = 400
    else:
        status_code = 502
    return status_code, result.public_payload()


def _provider_route_from_connection_payload(
    payload: Mapping[str, Any],
) -> tuple[WebProviderRoute, str]:
    request_payload = _require_mapping(payload, "connection payload")
    provider_payload: Mapping[str, Any]
    models_payload: Mapping[str, Any] | None
    if "provider" in request_payload:
        provider_payload = _require_mapping(request_payload.get("provider"), "provider")
        models_payload = _require_mapping(request_payload.get("models") or {}, "models")
    else:
        provider_payload = request_payload
        models_payload = _require_mapping(request_payload.get("models") or {}, "models")
    route = WebProviderRoute.from_frontend_payload(provider_payload, models_payload)
    route.require_live_ready()
    return route, _extract_session_api_key(provider_payload)


def _request_models_endpoint(
    models_url: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> int:
    request = Request(models_url, headers=dict(headers), method="GET")
    with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        response.read(1024)
        return int(getattr(response, "status", 200))


def _build_models_url(base_url: str) -> str:
    parts = urlsplit(base_url)
    path = parts.path.rstrip("/")
    if not path.endswith("/models"):
        path = f"{path}/models" if path else "/models"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _extract_session_api_key(provider_payload: Mapping[str, Any]) -> str:
    return _optional_text(provider_payload.get("apiKey", ""), "provider.apiKey")


def _connection_secret_candidates(
    payload: Any,
    backend_defaults: BackendDefaults,
) -> tuple[str, ...]:
    candidates: list[str] = []
    if isinstance(payload, Mapping):
        provider = payload.get("provider", payload)
        if isinstance(provider, Mapping) and isinstance(provider.get("apiKey"), str):
            if provider["apiKey"].strip():
                candidates.append(provider["apiKey"].strip())
    if isinstance(backend_defaults, Mapping):
        default_key = backend_defaults.get("api_key")
        if isinstance(default_key, str) and default_key.strip():
            candidates.append(default_key.strip())
    return tuple(candidates)


def _redact_text(text: str, secret_values: Sequence[str]) -> str:
    safe_text = text
    for secret in secret_values:
        if secret:
            safe_text = safe_text.replace(secret, "[redacted]")
    return safe_text


def _validate_base_url(value: str, label: str) -> None:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise WebRunConfigError(f"{label} must be an HTTP(S) URL.")
    if parts.username or parts.password:
        raise WebRunConfigError(f"{label} must not embed credentials.")
    if parts.query or parts.fragment:
        raise WebRunConfigError(f"{label} must not carry query or fragment text.")


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WebRunConfigError(f"{label} must be an object.")
    return value


def _require_text(value: Any, label: str) -> str:
    text = _optional_text(value, label)
    if not text:
        raise WebRunConfigError(f"{label} must be non-empty text.")
    return text


def _optional_text(value: Any, label: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise WebRunConfigError(f"{label} must be text.")
    return value.strip()


def _require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise WebRunConfigError(f"{label} must be true or false.")
    return value


def _require_text_items(value: Any, label: str) -> tuple[str, ...]:
    parsed = _optional_text_items(value, label)
    if not parsed:
        raise WebRunConfigError(f"{label} must contain at least one item.")
    return parsed


def _optional_text_items(value: Any, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise WebRunConfigError(f"{label} must be a text list.")
    items = tuple(_require_text(item, f"{label} item") for item in value)
    if len(items) != len(set(items)):
        raise WebRunConfigError(f"{label} cannot contain duplicates.")
    return items


def _require_int_range(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WebRunConfigError(f"{label} must be an integer.")
    if value < minimum or value > maximum:
        raise WebRunConfigError(f"{label} must be between {minimum} and {maximum}.")
    return value


def _require_timeout(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        raise WebRunConfigError("timeout_seconds must be a positive finite number.")
    return float(value)
