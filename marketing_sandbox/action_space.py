"""Marketing action boundaries shared by the sandbox decision flow."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping, Protocol, Sequence


NumericLimit = tuple[float | None, float | None]

DEFAULT_ACTION_CATEGORIES = frozenset(
    {"positioning", "product", "price", "channel", "promotion", "retention"}
)


class ActionSpaceError(Exception):
    """Base error for ActionSpace failures."""


class ActionSpaceDefinitionError(ActionSpaceError):
    """Raised when an ActionSpace configuration is internally inconsistent."""


class ActionSpaceValidationError(ActionSpaceError):
    """Raised when a strategy action leaves its declared ActionSpace."""


class ActionLike(Protocol):
    """The action fields required for ActionSpace validation."""

    category: str
    parameters: Mapping[str, Any]
    product_claims: Sequence[str]


@dataclass(frozen=True)
class ActionSpace:
    """Boundaries for the marketing actions a DecisionAgent may propose."""

    allowed_categories: frozenset[str] = DEFAULT_ACTION_CATEGORIES
    allowed_product_claims: frozenset[str] = frozenset()
    parameter_limits: Mapping[str, Mapping[str, NumericLimit]] = field(
        default_factory=dict
    )
    parameter_options: Mapping[str, Mapping[str, frozenset[str]]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        categories = self._clean_name_set(
            self.allowed_categories, "allowed action categories"
        )
        unknown_categories = categories - DEFAULT_ACTION_CATEGORIES
        if unknown_categories:
            rendered = ", ".join(sorted(unknown_categories))
            raise ActionSpaceDefinitionError(
                f"ActionSpace has unknown action categories: {rendered}."
            )

        claims = self._clean_name_set(
            self.allowed_product_claims, "approved product claims"
        )
        object.__setattr__(self, "allowed_categories", categories)
        object.__setattr__(self, "allowed_product_claims", claims)

        self._validate_parameter_limits()
        self._validate_parameter_options()
        self._reject_overlapping_parameter_rules()

    def validate(self, action: ActionLike) -> None:
        """Compatibility alias for callers validating one action."""

        self.validate_action(action)

    def validate_action(self, action: ActionLike) -> None:
        """Reject one action when it exceeds categories, claims, or parameters."""

        if action.category not in self.allowed_categories:
            raise ActionSpaceValidationError(
                f"Action category '{action.category}' is outside the ActionSpace."
            )

        if action.product_claims and action.category != "product":
            raise ActionSpaceValidationError(
                "Only product actions may carry approved product claims."
            )
        if action.category == "product":
            unknown_claims = set(action.product_claims) - set(
                self.allowed_product_claims
            )
            if unknown_claims:
                claims = ", ".join(sorted(unknown_claims))
                raise ActionSpaceValidationError(
                    f"Product action uses unapproved product claims: {claims}."
                )

        limits = self.parameter_limits.get(action.category, {})
        options = self.parameter_options.get(action.category, {})
        for name, value in action.parameters.items():
            if name in limits:
                self._validate_numeric_parameter(name, value, limits[name])
                continue
            if self._is_numeric_action_value(value):
                raise ActionSpaceValidationError(
                    f"Numeric action parameter '{name}' needs an ActionSpace limit."
                )
            if name in options:
                self._validate_option_parameter(name, value, options[name])

    def validate_actions(self, actions: Iterable[ActionLike]) -> None:
        """Validate a batch of actions using the same declared boundaries."""

        for action in actions:
            self.validate_action(action)

    def validate_strategy_actions(self, actions: Iterable[ActionLike]) -> None:
        """Reject a strategy unless every allowed category has a real action."""

        actions_tuple = tuple(actions)
        if not actions_tuple:
            raise ActionSpaceValidationError(
                "Strategy actions must include one action from every ActionSpace category."
            )
        self.validate_actions(actions_tuple)
        for action in actions_tuple:
            self._reject_pause_action(action)
        selected_categories = {action.category for action in actions_tuple}
        missing_categories = self.allowed_categories - selected_categories
        if missing_categories:
            rendered = ", ".join(sorted(missing_categories))
            raise ActionSpaceValidationError(
                "Strategy actions must include one action from every ActionSpace "
                f"category; missing: {rendered}."
            )

    def describe(self) -> str:
        """Render concise action boundaries for a model prompt."""

        categories = ", ".join(sorted(self.allowed_categories)) or "none declared"
        claim_text = ", ".join(sorted(self.allowed_product_claims)) or "none declared"
        rendered_limits = self._describe_limits()
        rendered_options = self._describe_options()
        return (
            f"Allowed action categories: {categories}\n"
            f"Approved product claims: {claim_text}\n"
            f"Numeric action limits: {rendered_limits}\n"
            f"Semantic action options: {rendered_options}\n"
            "Strategy action coverage: include one concrete action for every "
            "allowed category; pause, skip, no-op, and do-nothing actions are "
            "not allowed."
        )

    def _describe_limits(self) -> str:
        items: list[str] = []
        for category, category_limits in sorted(self.parameter_limits.items()):
            for parameter, (lower, upper) in sorted(category_limits.items()):
                items.append(f"{category}.{parameter}: [{lower}, {upper}]")
        return "; ".join(items) or "no numeric limits declared"

    def _describe_options(self) -> str:
        items: list[str] = []
        for category, category_options in sorted(self.parameter_options.items()):
            for parameter, values in sorted(category_options.items()):
                items.append(
                    f"{category}.{parameter}: {', '.join(sorted(values))}"
                )
        return "; ".join(items) or "no semantic options declared"

    def _validate_parameter_limits(self) -> None:
        self._ensure_rule_categories(self.parameter_limits, "numeric limits")
        for category, category_limits in self.parameter_limits.items():
            if not isinstance(category_limits, Mapping):
                raise ActionSpaceDefinitionError(
                    f"Numeric limits for '{category}' must be a mapping."
                )
            for name, limit in category_limits.items():
                self._require_name(name, "numeric action parameter")
                if (
                    isinstance(limit, (str, bytes))
                    or not isinstance(limit, Sequence)
                    or len(limit) != 2
                ):
                    raise ActionSpaceDefinitionError(
                        f"Numeric limit for '{category}.{name}' must have two bounds."
                    )
                lower, upper = limit
                self._validate_bound(category, name, "lower", lower)
                self._validate_bound(category, name, "upper", upper)
                if lower is not None and upper is not None and lower > upper:
                    raise ActionSpaceDefinitionError(
                        f"Numeric limit for '{category}.{name}' has reversed bounds."
                    )

    def _validate_parameter_options(self) -> None:
        self._ensure_rule_categories(self.parameter_options, "semantic options")
        for category, category_options in self.parameter_options.items():
            if not isinstance(category_options, Mapping):
                raise ActionSpaceDefinitionError(
                    f"Semantic options for '{category}' must be a mapping."
                )
            for name, values in category_options.items():
                self._require_name(name, "semantic action parameter")
                if isinstance(values, (str, bytes)):
                    raise ActionSpaceDefinitionError(
                        f"Semantic options for '{category}.{name}' must be a set."
                    )
                cleaned = self._clean_name_set(
                    values, f"semantic options for '{category}.{name}'"
                )
                if not cleaned:
                    raise ActionSpaceDefinitionError(
                        f"Semantic options for '{category}.{name}' cannot be empty."
                    )

    def _reject_overlapping_parameter_rules(self) -> None:
        for category in set(self.parameter_limits) & set(self.parameter_options):
            overlap = set(self.parameter_limits[category]) & set(
                self.parameter_options[category]
            )
            if overlap:
                rendered = ", ".join(sorted(overlap))
                raise ActionSpaceDefinitionError(
                    f"Action parameters cannot have both limits and options: {rendered}."
                )

    def _ensure_rule_categories(
        self, rules: Mapping[str, Mapping[str, Any]], label: str
    ) -> None:
        unknown = set(rules) - set(self.allowed_categories)
        if unknown:
            rendered = ", ".join(sorted(unknown))
            raise ActionSpaceDefinitionError(
                f"ActionSpace {label} target disabled categories: {rendered}."
            )

    def _validate_numeric_parameter(
        self, name: str, value: Any, limit: NumericLimit
    ) -> None:
        if not self._is_numeric_action_value(value):
            raise ActionSpaceValidationError(
                f"Action parameter '{name}' must be numeric inside its limit."
            )
        if not math.isfinite(float(value)):
            raise ActionSpaceValidationError(
                f"Action parameter '{name}' must be a finite number."
            )
        lower, upper = limit
        if lower is not None and value < lower:
            raise ActionSpaceValidationError(
                f"Action parameter '{name}' is below the ActionSpace limit."
            )
        if upper is not None and value > upper:
            raise ActionSpaceValidationError(
                f"Action parameter '{name}' is above the ActionSpace limit."
            )

    def _validate_option_parameter(
        self, name: str, value: Any, allowed_values: frozenset[str]
    ) -> None:
        selected_values = self._parse_selected_options(name, value)
        unknown = set(selected_values) - set(allowed_values)
        if unknown:
            rendered = ", ".join(sorted(unknown))
            raise ActionSpaceValidationError(
                f"Action parameter '{name}' uses unsupported options: {rendered}."
            )

    @classmethod
    def _reject_pause_action(cls, action: ActionLike) -> None:
        for field_name in ("summary", "reason"):
            value = getattr(action, field_name, "")
            if isinstance(value, str) and cls._is_pause_text(value):
                raise ActionSpaceValidationError(
                    "Strategy actions cannot pause, skip, or choose no action."
                )

    @staticmethod
    def _is_pause_text(value: str) -> bool:
        normalized = value.lower().replace("_", " ").replace("-", " ")
        blocked_phrases = (
            "no action",
            "do nothing",
            "skip",
            "pause",
            "no op",
            "noop",
            "hold this category",
            "leave unchanged",
        )
        return any(phrase in normalized for phrase in blocked_phrases)

    @classmethod
    def _parse_selected_options(cls, name: str, value: Any) -> tuple[str, ...]:
        if isinstance(value, str):
            return (cls._require_selected_option(value, name),)
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ActionSpaceValidationError(
                f"Action parameter '{name}' must use declared text options."
            )
        selected = tuple(
            cls._require_selected_option(item, name) for item in value
        )
        if not selected:
            raise ActionSpaceValidationError(
                f"Action parameter '{name}' must select at least one option."
            )
        return selected

    @staticmethod
    def _require_selected_option(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ActionSpaceValidationError(
                f"Action parameter '{name}' must use non-empty text options."
            )
        return value.strip()

    @staticmethod
    def _is_numeric_action_value(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    @classmethod
    def _clean_name_set(cls, values: Iterable[Any], label: str) -> frozenset[str]:
        if isinstance(values, (str, bytes)):
            raise ActionSpaceDefinitionError(f"{label} must be a collection of text.")
        try:
            cleaned = frozenset(cls._require_name(value, label) for value in values)
        except TypeError as error:
            raise ActionSpaceDefinitionError(
                f"{label} must be a collection of text."
            ) from error
        return cleaned

    @staticmethod
    def _require_name(value: Any, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ActionSpaceDefinitionError(f"{label} must be non-empty text.")
        return value.strip()

    @staticmethod
    def _validate_bound(
        category: str, name: str, bound_name: str, value: float | None
    ) -> None:
        if value is None:
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ActionSpaceDefinitionError(
                f"{bound_name} bound for '{category}.{name}' must be numeric."
            )
        if not math.isfinite(float(value)):
            raise ActionSpaceDefinitionError(
                f"{bound_name} bound for '{category}.{name}' must be finite."
            )
