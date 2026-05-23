"""Deterministic mapping from qualitative search labels to UCB reward."""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from .critic_agent import CriticSearchSignals
from .feedback_synthesizer import FeedbackSearchSignals
from .search_models import RewardBreakdown


class RewardMappingError(Exception):
    """Raised when qualitative search signals cannot map to reward."""


class RewardMapper:
    """Map guarded non-numeric labels into internal search reward."""

    POSITIVE_LABEL_VALUES = {
        "core_target_response": {"moved": 1.0, "mixed": 0.5, "unmoved": 0.0},
        "trial_momentum": {
            "pulled_closer": 1.0,
            "conditional": 0.5,
            "pushed_away": 0.0,
        },
        "strategy_clarity": {"clear": 1.0, "partial": 0.5, "confusing": 0.0},
        "repeat_logic": {"natural": 1.0, "conditional": 0.5, "weak": 0.0},
        "competitor_resilience": {"holds": 1.0, "fragile": 0.5, "displaced": 0.0},
        "evidence_consistency": {"consistent": 1.0, "mixed": 0.5, "thin": 0.0},
    }
    POSITIVE_WEIGHTS = {
        "core_target_response": 0.25,
        "trial_momentum": 0.20,
        "strategy_clarity": 0.15,
        "repeat_logic": 0.15,
        "competitor_resilience": 0.15,
        "evidence_consistency": 0.10,
    }
    RISK_LABEL_VALUES = {"contained": 0.0, "watch": 0.5, "serious": 1.0}
    RISK_WEIGHTS = {
        "product_boundary_risk": 0.14,
        "brand_risk": 0.08,
        "execution_risk": 0.05,
        "self_deception_risk": 0.08,
    }

    def map(
        self,
        feedback_signals: FeedbackSearchSignals | None,
        critic_signals: CriticSearchSignals | None,
    ) -> RewardBreakdown:
        """Return one auditable internal reward for complete search signals."""

        if not isinstance(feedback_signals, FeedbackSearchSignals):
            raise RewardMappingError("RewardMapper needs FeedbackSearchSignals.")
        if not isinstance(critic_signals, CriticSearchSignals):
            raise RewardMappingError("RewardMapper needs CriticSearchSignals.")

        positive_components = self._positive_components(feedback_signals)
        risk_components = self._risk_components(critic_signals)
        positive_utility = sum(positive_components.values())
        risk_penalty = sum(risk_components.values())
        raw_reward = positive_utility - risk_penalty
        reward = max(0.0, min(1.0, raw_reward))
        caps: list[str] = []
        if critic_signals.product_boundary_risk == "serious" and reward > 0.35:
            reward = 0.35
            caps.append("serious_product_boundary_risk")
        if critic_signals.self_deception_risk == "serious" and reward > 0.45:
            reward = 0.45
            caps.append("serious_self_deception_risk")
        return RewardBreakdown(
            reward=reward,
            positive_utility=positive_utility,
            risk_penalty=risk_penalty,
            positive_components=MappingProxyType(positive_components),
            risk_components=MappingProxyType(risk_components),
            applied_caps=tuple(caps),
            mapping_note=(
                "Internal sandbox search utility from qualitative summary and critic "
                "labels; it is not a market forecast."
            ),
        )

    def _positive_components(
        self, signals: FeedbackSearchSignals
    ) -> dict[str, float]:
        components: dict[str, float] = {}
        for field_name, weight in self.POSITIVE_WEIGHTS.items():
            label = getattr(signals, field_name)
            components[field_name] = weight * self._label_value(
                self.POSITIVE_LABEL_VALUES[field_name],
                label,
                f"feedback {field_name}",
            )
        return components

    def _risk_components(self, signals: CriticSearchSignals) -> dict[str, float]:
        components: dict[str, float] = {}
        for field_name, weight in self.RISK_WEIGHTS.items():
            label = getattr(signals, field_name)
            components[field_name] = weight * self._label_value(
                self.RISK_LABEL_VALUES,
                label,
                f"critic {field_name}",
            )
        return components

    @staticmethod
    def _label_value(values: Mapping[str, float], label: str, field: str) -> float:
        try:
            return values[label]
        except KeyError as error:
            raise RewardMappingError(
                f"RewardMapper cannot map unknown {field} label: {label}."
            ) from error
