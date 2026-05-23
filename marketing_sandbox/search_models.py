"""Data contracts for family-level marketing strategy search."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


FAMILY_ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
GENERATION_INTENTS = frozenset({"cold_start", "explore_variant", "refine_promising"})


class SearchModelError(Exception):
    """Raised when family search data leaves its contract."""


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SearchModelError(f"{label} must be non-empty text.")
    return value.strip()


def _require_text_tuple(values: Sequence[str], label: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise SearchModelError(f"{label} must be a sequence of text.")
    parsed = tuple(_require_text(value, label) for value in values)
    if not parsed:
        raise SearchModelError(f"{label} must contain at least one item.")
    return parsed


def _freeze_text_mapping(
    values: Mapping[str, Any], label: str
) -> Mapping[str, Any]:
    if not isinstance(values, Mapping):
        raise SearchModelError(f"{label} must be a mapping.")
    return MappingProxyType(dict(values))


@dataclass(frozen=True)
class StrategyFamily:
    """High-level strategy arm sharing one marketing win logic."""

    family_id: str
    name: str
    core_barrier: str
    win_mechanism: str
    generation_guidance: str
    expected_action_patterns: tuple[str, ...]
    failure_signals: tuple[str, ...]

    def __post_init__(self) -> None:
        family_id = _require_text(self.family_id, "StrategyFamily family_id")
        if not FAMILY_ID_PATTERN.fullmatch(family_id):
            raise SearchModelError(
                "StrategyFamily family_id must be an ASCII identifier."
            )
        object.__setattr__(self, "family_id", family_id)
        for field_name in (
            "name",
            "core_barrier",
            "win_mechanism",
            "generation_guidance",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_text(
                    getattr(self, field_name), f"StrategyFamily {field_name}"
                ),
            )
        object.__setattr__(
            self,
            "expected_action_patterns",
            _require_text_tuple(
                self.expected_action_patterns,
                "StrategyFamily expected_action_patterns",
            ),
        )
        object.__setattr__(
            self,
            "failure_signals",
            _require_text_tuple(self.failure_signals, "StrategyFamily failure_signals"),
        )


@dataclass(frozen=True)
class UCBSearchConfig:
    """Deterministic family-level UCB search configuration."""

    candidate_slots_per_round: int = 1
    exploration_coefficient: float = 0.7
    promising_reward_threshold: float = 0.65
    strategies_per_family: int = 1
    memory_lines_per_family: int = 4

    def __post_init__(self) -> None:
        for field_name in (
            "candidate_slots_per_round",
            "strategies_per_family",
            "memory_lines_per_family",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise SearchModelError(f"UCBSearchConfig {field_name} must be positive.")
        if self.strategies_per_family != 1:
            raise SearchModelError(
                "UCBSearchConfig currently supports one strategy per family slot."
            )
        for field_name in ("exploration_coefficient", "promising_reward_threshold"):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise SearchModelError(f"UCBSearchConfig {field_name} must be finite.")
        if self.exploration_coefficient < 0:
            raise SearchModelError(
                "UCBSearchConfig exploration_coefficient cannot be negative."
            )
        if not 0 <= self.promising_reward_threshold <= 1:
            raise SearchModelError(
                "UCBSearchConfig promising_reward_threshold must be in [0, 1]."
            )


@dataclass(frozen=True)
class SearchBrief:
    """Qualitative family-generation instruction for DecisionAgent."""

    selected_families: tuple[StrategyFamily, ...]
    generation_intents: Mapping[str, str]
    qualitative_memory: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    strategies_per_family: int = 1

    def __post_init__(self) -> None:
        if not self.selected_families:
            raise SearchModelError("SearchBrief needs selected families.")
        if any(not isinstance(item, StrategyFamily) for item in self.selected_families):
            raise SearchModelError("SearchBrief selected_families must be StrategyFamily.")
        family_ids = self.selected_family_ids
        if len(family_ids) != len(set(family_ids)):
            raise SearchModelError("SearchBrief selected family ids must be unique.")
        if self.strategies_per_family != 1:
            raise SearchModelError("SearchBrief currently needs one strategy per family.")

        intents = dict(_freeze_text_mapping(self.generation_intents, "generation_intents"))
        if set(intents) != set(family_ids):
            raise SearchModelError("SearchBrief intents must cover selected families.")
        for family_id, intent in intents.items():
            _require_text(family_id, "SearchBrief intent family_id")
            if intent not in GENERATION_INTENTS:
                raise SearchModelError(f"SearchBrief has unknown intent: {intent}.")
        object.__setattr__(self, "generation_intents", MappingProxyType(intents))

        raw_memory = dict(
            _freeze_text_mapping(self.qualitative_memory, "qualitative_memory")
        )
        if set(raw_memory) - set(family_ids):
            raise SearchModelError(
                "SearchBrief qualitative memory targets unselected families."
            )
        memory = {
            family_id: _require_text_tuple(lines, "SearchBrief memory lines")
            for family_id, lines in raw_memory.items()
        }
        object.__setattr__(self, "qualitative_memory", MappingProxyType(memory))

    @property
    def selected_family_ids(self) -> tuple[str, ...]:
        """Return the family ids in requested output order."""

        return tuple(item.family_id for item in self.selected_families)

    @property
    def expected_strategy_count(self) -> int:
        """Return the number of concrete strategies the brief expects."""

        return len(self.selected_families) * self.strategies_per_family

    def describe(self) -> str:
        """Render a prompt-safe family brief without UCB numbers."""

        blocks: list[str] = []
        for family in self.selected_families:
            action_patterns = "; ".join(family.expected_action_patterns)
            failure_signals = "; ".join(family.failure_signals)
            memory_lines = self.qualitative_memory.get(family.family_id, ())
            memory = (
                "\n".join(f"  - {line}" for line in memory_lines)
                if memory_lines
                else "  - no guarded family memory yet"
            )
            blocks.append(
                f"- family_id: {family.family_id}\n"
                f"  name: {family.name}\n"
                f"  generation intent: {self.generation_intents[family.family_id]}\n"
                f"  core barrier: {family.core_barrier}\n"
                f"  win mechanism: {family.win_mechanism}\n"
                f"  guidance: {family.generation_guidance}\n"
                f"  expected action patterns: {action_patterns}\n"
                f"  failure signals: {failure_signals}\n"
                f"  qualitative memory:\n{memory}"
            )
        return "\n".join(blocks)


@dataclass(frozen=True)
class SearchSelection:
    """One controller selection with internal score audit kept off prompts."""

    round_index: int
    brief: SearchBrief
    selection_reasons: Mapping[str, str]
    ucb_scores: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            isinstance(self.round_index, bool)
            or not isinstance(self.round_index, int)
            or self.round_index < 1
        ):
            raise SearchModelError("SearchSelection round_index must be positive.")
        reasons = dict(_freeze_text_mapping(self.selection_reasons, "selection_reasons"))
        if set(reasons) != set(self.brief.selected_family_ids):
            raise SearchModelError(
                "SearchSelection reasons must cover selected families."
            )
        cleaned_reasons = {
            family_id: _require_text(reason, "SearchSelection reason")
            for family_id, reason in reasons.items()
        }
        object.__setattr__(
            self, "selection_reasons", MappingProxyType(cleaned_reasons)
        )
        scores = dict(_freeze_text_mapping(self.ucb_scores, "ucb_scores"))
        for family_id, score in scores.items():
            _require_text(family_id, "SearchSelection score family_id")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise SearchModelError("SearchSelection score must be numeric.")
        object.__setattr__(self, "ucb_scores", MappingProxyType(scores))

    @property
    def selected_family_ids(self) -> tuple[str, ...]:
        """Return selected family ids in brief order."""

        return self.brief.selected_family_ids


@dataclass(frozen=True)
class RewardBreakdown:
    """Auditable deterministic reward used only by the search layer."""

    reward: float
    positive_utility: float
    risk_penalty: float
    positive_components: Mapping[str, float]
    risk_components: Mapping[str, float]
    applied_caps: tuple[str, ...] = ()
    mapping_note: str = ""

    def __post_init__(self) -> None:
        for field_name in ("reward", "positive_utility", "risk_penalty"):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise SearchModelError(f"RewardBreakdown {field_name} must be finite.")
        if self.reward > 1:
            raise SearchModelError("RewardBreakdown reward must be in [0, 1].")
        object.__setattr__(
            self,
            "positive_components",
            self._validate_components(
                self.positive_components, "positive_components"
            ),
        )
        object.__setattr__(
            self,
            "risk_components",
            self._validate_components(self.risk_components, "risk_components"),
        )
        if isinstance(self.applied_caps, (str, bytes)):
            raise SearchModelError("RewardBreakdown applied_caps must be text items.")
        object.__setattr__(
            self,
            "applied_caps",
            tuple(
                _require_text(item, "RewardBreakdown applied cap")
                for item in self.applied_caps
            ),
        )
        if self.mapping_note:
            object.__setattr__(
                self,
                "mapping_note",
                _require_text(self.mapping_note, "RewardBreakdown mapping_note"),
            )

    @staticmethod
    def _validate_components(
        components: Mapping[str, float], label: str
    ) -> Mapping[str, float]:
        raw = dict(_freeze_text_mapping(components, f"RewardBreakdown {label}"))
        parsed: dict[str, float] = {}
        for name, value in raw.items():
            parsed_name = _require_text(name, f"RewardBreakdown {label} name")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise SearchModelError(
                    f"RewardBreakdown {label} values must be finite."
                )
            parsed[parsed_name] = float(value)
        return MappingProxyType(parsed)


@dataclass(frozen=True)
class SearchObservation:
    """One complete family pull after strategy test and reward mapping."""

    round_index: int
    family_id: str
    strategy_name: str
    summary_signals: Any
    critic_signals: Any
    reward_breakdown: RewardBreakdown

    def __post_init__(self) -> None:
        if (
            isinstance(self.round_index, bool)
            or not isinstance(self.round_index, int)
            or self.round_index < 1
        ):
            raise SearchModelError("SearchObservation round_index must be positive.")
        family_id = _require_text(self.family_id, "SearchObservation family_id")
        if not FAMILY_ID_PATTERN.fullmatch(family_id):
            raise SearchModelError(
                "SearchObservation family_id must be an ASCII identifier."
            )
        object.__setattr__(self, "family_id", family_id)
        object.__setattr__(
            self,
            "strategy_name",
            _require_text(self.strategy_name, "SearchObservation strategy_name"),
        )
        if self.summary_signals is None or self.critic_signals is None:
            raise SearchModelError("SearchObservation needs complete search signals.")
        if not isinstance(self.reward_breakdown, RewardBreakdown):
            raise SearchModelError("SearchObservation needs a RewardBreakdown.")

    @property
    def qualitative_memory(self) -> tuple[str, ...]:
        """Extract guarded text notes for later strategy generation."""

        lines: list[str] = []
        signal_note = getattr(self.summary_signals, "signal_note", "")
        risk_note = getattr(self.critic_signals, "risk_note", "")
        if isinstance(signal_note, str) and signal_note.strip():
            lines.append(f"{self.strategy_name} summary: {signal_note.strip()}")
        if isinstance(risk_note, str) and risk_note.strip():
            lines.append(f"{self.strategy_name} critic: {risk_note.strip()}")
        return tuple(lines)


@dataclass(frozen=True)
class FamilyArmState:
    """Immutable snapshot of one family arm state."""

    family_id: str
    pull_count: int = 0
    reward_sum: float = 0.0
    last_selected_round: int | None = None
    observations: tuple[SearchObservation, ...] = ()

    def __post_init__(self) -> None:
        family_id = _require_text(self.family_id, "FamilyArmState family_id")
        if not FAMILY_ID_PATTERN.fullmatch(family_id):
            raise SearchModelError("FamilyArmState family_id must be ASCII.")
        object.__setattr__(self, "family_id", family_id)
        if (
            isinstance(self.pull_count, bool)
            or not isinstance(self.pull_count, int)
            or self.pull_count < 0
        ):
            raise SearchModelError("FamilyArmState pull_count cannot be negative.")
        if (
            isinstance(self.reward_sum, bool)
            or not isinstance(self.reward_sum, (int, float))
            or not math.isfinite(float(self.reward_sum))
            or self.reward_sum < 0
        ):
            raise SearchModelError("FamilyArmState reward_sum cannot be negative.")
        if self.pull_count != len(self.observations):
            raise SearchModelError(
                "FamilyArmState pull_count must match saved observations."
            )
        if self.last_selected_round is not None and (
            isinstance(self.last_selected_round, bool)
            or not isinstance(self.last_selected_round, int)
            or self.last_selected_round < 1
        ):
            raise SearchModelError(
                "FamilyArmState last_selected_round must be positive."
            )

    @property
    def mean_reward(self) -> float:
        """Return mean internal reward without inventing unseen evidence."""

        if not self.pull_count:
            return 0.0
        return self.reward_sum / self.pull_count

    def add_observation(self, observation: SearchObservation) -> "FamilyArmState":
        """Return a state snapshot updated by one complete observation."""

        if observation.family_id != self.family_id:
            raise SearchModelError("Observation family does not match arm state.")
        reward = observation.reward_breakdown.reward
        if (
            isinstance(reward, bool)
            or not isinstance(reward, (int, float))
            or not math.isfinite(float(reward))
            or reward < 0
        ):
            raise SearchModelError("Observation reward must be a finite reward.")
        return FamilyArmState(
            family_id=self.family_id,
            pull_count=self.pull_count + 1,
            reward_sum=self.reward_sum + float(reward),
            last_selected_round=observation.round_index,
            observations=self.observations + (observation,),
        )


@dataclass(frozen=True)
class SearchUpdate:
    """Auditable controller update for one family observation."""

    family_id: str
    observation: SearchObservation
    state_before: FamilyArmState
    state_after: FamilyArmState
