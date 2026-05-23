"""Family-level UCB controller for marketing strategy search."""

from __future__ import annotations

import math
from types import SimpleNamespace
from typing import Any, Mapping, Sequence

from .search_models import (
    FamilyArmState,
    RewardBreakdown,
    SearchBrief,
    SearchModelError,
    SearchObservation,
    SearchSelection,
    SearchUpdate,
    StrategyFamily,
    UCBSearchConfig,
)


class UCBSearchControllerError(Exception):
    """Base error for UCB family search failures."""


class UCBSearchInputError(UCBSearchControllerError):
    """Raised when UCB selection or update input is incomplete."""


class UCBSearchController:
    """Select strategy families with deterministic cold start and UCB."""

    def __init__(
        self,
        families: Sequence[StrategyFamily],
        config: UCBSearchConfig | None = None,
    ) -> None:
        self.config = config or UCBSearchConfig()
        self._families = tuple(families)
        self._validate_families()
        self._family_by_id = {family.family_id: family for family in self._families}
        self._states = {
            family.family_id: FamilyArmState(family.family_id)
            for family in self._families
        }
        self._last_selection: SearchSelection | None = None

    @property
    def families(self) -> tuple[StrategyFamily, ...]:
        """Return registered families in deterministic tie-break order."""

        return self._families

    @property
    def states(self) -> tuple[FamilyArmState, ...]:
        """Return immutable state snapshots in family registration order."""

        return tuple(self._states[item.family_id] for item in self._families)

    @property
    def total_pulls(self) -> int:
        """Return complete family observations already updated."""

        return sum(state.pull_count for state in self._states.values())

    def state_for(self, family_id: str) -> FamilyArmState:
        """Return one family state or fail on unknown family id."""

        try:
            return self._states[family_id]
        except KeyError as error:
            raise UCBSearchInputError(f"Unknown strategy family: {family_id}.") from error

    def restore_from_archive_search_state(
        self,
        search_state: Mapping[str, Any],
    ) -> None:
        """Restore family arm state from a versioned safe-boundary archive.

        The archive carries only completed round search events. This method
        rebuilds minimal ``SearchObservation`` objects from the reward history
        so the next ``select`` call follows the same cold-start/UCB logic as a
        controller that had naturally observed those completed rounds.
        """

        if not isinstance(search_state, Mapping):
            raise UCBSearchInputError("Archive searchState must be a mapping.")
        records = search_state.get("rewardHistory", ())
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
            raise UCBSearchInputError("Archive rewardHistory must be a sequence.")

        next_states = {
            family.family_id: FamilyArmState(family.family_id)
            for family in self._families
        }
        for record in records:
            observation = self._observation_from_archive_record(record)
            if observation.family_id not in next_states:
                raise UCBSearchInputError(
                    f"Archive searchState targets unknown family: {observation.family_id}."
                )
            try:
                next_states[observation.family_id] = next_states[
                    observation.family_id
                ].add_observation(observation)
            except SearchModelError as error:
                raise UCBSearchInputError(str(error)) from error

        self._validate_restored_family_states(next_states, search_state)
        self._states = next_states
        self._last_selection = None

    def select(
        self, round_index: int, history: Sequence[Any] = ()
    ) -> SearchSelection:
        """Select family slots for one sandbox round."""

        if isinstance(round_index, bool) or not isinstance(round_index, int):
            raise UCBSearchInputError("UCB round_index must be an integer.")
        if round_index < 1:
            raise UCBSearchInputError("UCB round_index must be positive.")
        del history

        selected_ids, reasons, scores = self._select_family_ids()
        selected_families = tuple(self._family_by_id[item] for item in selected_ids)
        intents = {
            family_id: self._generation_intent(self._states[family_id])
            for family_id in selected_ids
        }
        memory = {
            family_id: self._qualitative_memory(self._states[family_id])
            for family_id in selected_ids
            if self._qualitative_memory(self._states[family_id])
        }
        selection = SearchSelection(
            round_index=round_index,
            brief=SearchBrief(
                selected_families=selected_families,
                generation_intents=intents,
                qualitative_memory=memory,
                strategies_per_family=self.config.strategies_per_family,
            ),
            selection_reasons=reasons,
            ucb_scores=scores,
        )
        self._last_selection = selection
        return selection

    def update(
        self,
        observations: Sequence[SearchObservation],
        *,
        selection: SearchSelection | None = None,
    ) -> tuple[SearchUpdate, ...]:
        """Update each selected family from one complete observation."""

        chosen_selection = selection or self._last_selection
        if chosen_selection is None:
            raise UCBSearchInputError("UCB update needs a prior SearchSelection.")
        if not observations:
            raise UCBSearchInputError("UCB update needs observations.")
        observations_tuple = tuple(observations)
        self._validate_observations(observations_tuple, chosen_selection)

        updates: list[SearchUpdate] = []
        next_states = dict(self._states)
        for observation in observations_tuple:
            before = next_states[observation.family_id]
            try:
                after = before.add_observation(observation)
            except SearchModelError as error:
                raise UCBSearchInputError(str(error)) from error
            next_states[observation.family_id] = after
            updates.append(
                SearchUpdate(
                    family_id=observation.family_id,
                    observation=observation,
                    state_before=before,
                    state_after=after,
                )
            )
        self._states = next_states
        return tuple(updates)

    def _select_family_ids(
        self,
    ) -> tuple[tuple[str, ...], dict[str, str], dict[str, float]]:
        slots = self.config.candidate_slots_per_round
        untested = [
            family.family_id
            for family in self._families
            if self._states[family.family_id].pull_count == 0
        ]
        chosen = untested[:slots]
        reasons = {
            family_id: "cold start family has no complete observation yet"
            for family_id in chosen
        }
        scores = {family_id: math.inf for family_id in chosen}
        if len(chosen) == slots:
            return tuple(chosen), reasons, scores

        remaining_slots = slots - len(chosen)
        tested = [
            family.family_id
            for family in self._families
            if self._states[family.family_id].pull_count > 0
            and family.family_id not in chosen
        ]
        scored_tested = [
            (self._ucb_score(self._states[family_id]), index, family_id)
            for index, family_id in enumerate(tested)
        ]
        scored_tested.sort(key=lambda item: (-item[0], item[1]))
        for score, _, family_id in scored_tested[:remaining_slots]:
            chosen.append(family_id)
            reasons[family_id] = "UCB balances guarded mean reward and exploration"
            scores[family_id] = score
        return tuple(chosen), reasons, scores

    def _ucb_score(self, state: FamilyArmState) -> float:
        if not state.pull_count:
            return math.inf
        log_term = math.log(max(self.total_pulls, 1))
        exploration = self.config.exploration_coefficient * math.sqrt(
            log_term / state.pull_count
        )
        return state.mean_reward + exploration

    def _generation_intent(self, state: FamilyArmState) -> str:
        if not state.pull_count:
            return "cold_start"
        if state.mean_reward >= self.config.promising_reward_threshold:
            return "refine_promising"
        return "explore_variant"

    def _qualitative_memory(self, state: FamilyArmState) -> tuple[str, ...]:
        memory: list[str] = []
        for observation in reversed(state.observations):
            memory.extend(reversed(observation.qualitative_memory))
            if len(memory) >= self.config.memory_lines_per_family:
                break
        memory.reverse()
        return tuple(memory[-self.config.memory_lines_per_family :])

    def _validate_families(self) -> None:
        if not self._families:
            raise UCBSearchInputError("UCBSearchController needs strategy families.")
        if any(not isinstance(item, StrategyFamily) for item in self._families):
            raise UCBSearchInputError(
                "UCBSearchController families must be StrategyFamily."
            )
        family_ids = [item.family_id for item in self._families]
        if len(family_ids) != len(set(family_ids)):
            raise UCBSearchInputError("Strategy family ids must be unique.")
        if self.config.candidate_slots_per_round > len(self._families):
            raise UCBSearchInputError(
                "UCB candidate slots cannot exceed registered strategy families."
            )

    def _validate_observations(
        self,
        observations: tuple[SearchObservation, ...],
        selection: SearchSelection,
    ) -> None:
        if any(not isinstance(item, SearchObservation) for item in observations):
            raise UCBSearchInputError("UCB observations must be SearchObservation.")
        observed_ids = [item.family_id for item in observations]
        if len(observed_ids) != len(set(observed_ids)):
            raise UCBSearchInputError("UCB update accepts one observation per family.")
        expected_ids = set(selection.selected_family_ids)
        if set(observed_ids) != expected_ids:
            raise UCBSearchInputError(
                "UCB update observations must cover selected families exactly."
            )
        for observation in observations:
            if observation.family_id not in self._states:
                raise UCBSearchInputError(
                    f"UCB observation targets unknown family: {observation.family_id}."
                )
            if observation.round_index != selection.round_index:
                raise UCBSearchInputError(
                    "UCB observation round must match SearchSelection round."
                )

    def _observation_from_archive_record(
        self,
        record: Any,
    ) -> SearchObservation:
        if not isinstance(record, Mapping):
            raise UCBSearchInputError("Archive reward history records must be objects.")
        family_id = self._require_record_text(record, "familyId")
        round_index = self._require_record_positive_int(record, "round")
        strategy_name = self._require_record_text(record, "strategyName")
        reward = self._require_record_reward(record, "reward")
        positive_utility = self._optional_record_number(
            record,
            "positiveUtility",
            default=reward,
        )
        risk_penalty = self._optional_record_number(record, "riskPenalty", default=0.0)
        positive_components = self._optional_component_mapping(
            record.get("positiveComponents")
        )
        risk_components = self._optional_component_mapping(record.get("riskComponents"))
        reward_breakdown = RewardBreakdown(
            reward=reward,
            positive_utility=positive_utility,
            risk_penalty=risk_penalty,
            positive_components=positive_components,
            risk_components=risk_components,
            applied_caps=tuple(str(item) for item in record.get("appliedCaps", ()) or ()),
            mapping_note=str(record.get("mappingNote") or "Restored from archive."),
        )
        return SearchObservation(
            round_index=round_index,
            family_id=family_id,
            strategy_name=strategy_name,
            summary_signals=SimpleNamespace(
                signal_note=str(record.get("summaryNote") or "")
            ),
            critic_signals=SimpleNamespace(
                risk_note=str(record.get("riskNote") or "")
            ),
            reward_breakdown=reward_breakdown,
        )

    def _validate_restored_family_states(
        self,
        next_states: Mapping[str, FamilyArmState],
        search_state: Mapping[str, Any],
    ) -> None:
        raw_states = search_state.get("familyStates", {})
        if not isinstance(raw_states, Mapping):
            raise UCBSearchInputError("Archive familyStates must be a mapping.")
        for family_id, raw_state in raw_states.items():
            if family_id not in next_states:
                raise UCBSearchInputError(
                    f"Archive familyStates targets unknown family: {family_id}."
                )
            if not isinstance(raw_state, Mapping):
                raise UCBSearchInputError("Archive family state must be an object.")
            restored = next_states[family_id]
            expected_count = self._optional_record_int(raw_state, "pullCount", 0)
            expected_sum = self._optional_record_number(raw_state, "rewardSum", default=0.0)
            if restored.pull_count != expected_count:
                raise UCBSearchInputError(
                    "Archive family pull count does not match reward history."
                )
            if not math.isclose(restored.reward_sum, expected_sum, rel_tol=1e-9, abs_tol=1e-9):
                raise UCBSearchInputError(
                    "Archive family reward sum does not match reward history."
                )

    @staticmethod
    def _require_record_text(record: Mapping[str, Any], key: str) -> str:
        value = record.get(key)
        if not isinstance(value, str) or not value.strip():
            raise UCBSearchInputError(f"Archive reward history needs {key}.")
        return value.strip()

    @staticmethod
    def _require_record_positive_int(record: Mapping[str, Any], key: str) -> int:
        value = record.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise UCBSearchInputError(f"Archive reward history {key} must be positive.")
        return value

    @staticmethod
    def _optional_record_int(
        record: Mapping[str, Any],
        key: str,
        default: int,
    ) -> int:
        value = record.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise UCBSearchInputError(f"Archive field {key} must be a non-negative integer.")
        return value

    @staticmethod
    def _require_record_reward(record: Mapping[str, Any], key: str) -> float:
        value = UCBSearchController._optional_record_number(record, key, default=None)
        if value is None or value > 1:
            raise UCBSearchInputError(f"Archive reward history {key} must be in [0, 1].")
        return value

    @staticmethod
    def _optional_record_number(
        record: Mapping[str, Any],
        key: str,
        *,
        default: float | None,
    ) -> float | None:
        value = record.get(key, default)
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0
        ):
            raise UCBSearchInputError(f"Archive field {key} must be a finite number.")
        return float(value)

    @staticmethod
    def _optional_component_mapping(value: Any) -> dict[str, float]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise UCBSearchInputError("Archive reward components must be mappings.")
        parsed: dict[str, float] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise UCBSearchInputError("Archive reward component keys must be text.")
            if (
                isinstance(item, bool)
                or not isinstance(item, (int, float))
                or not math.isfinite(float(item))
                or float(item) < 0
            ):
                raise UCBSearchInputError("Archive reward component values must be finite.")
            parsed[key.strip()] = float(item)
        return parsed
