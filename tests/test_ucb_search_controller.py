"""Tests for family-level UCB exploration and update state."""

from __future__ import annotations

import math
import unittest

from marketing_sandbox import (
    CriticSearchSignals,
    FeedbackSearchSignals,
    RewardBreakdown,
    SearchBrief,
    SearchObservation,
    SearchSelection,
    StrategyFamily,
    UCBSearchConfig,
    UCBSearchController,
    UCBSearchInputError,
)


def make_family(family_id):
    return StrategyFamily(
        family_id=family_id,
        name=family_id.replace("_", " ").title(),
        core_barrier=f"{family_id} barrier",
        win_mechanism=f"{family_id} win mechanism",
        generation_guidance=f"Generate a concrete {family_id} variant.",
        expected_action_patterns=("bounded action pattern",),
        failure_signals=("family feedback turns thin",),
    )


def make_observation(family_id, reward=0.6, round_index=1, signal_note="Clearer trial."):
    return SearchObservation(
        round_index=round_index,
        family_id=family_id,
        strategy_name=f"{family_id} strategy",
        summary_signals=FeedbackSearchSignals(
            core_target_response="mixed",
            trial_momentum="conditional",
            strategy_clarity="partial",
            repeat_logic="conditional",
            competitor_resilience="fragile",
            evidence_consistency="mixed",
            signal_note=signal_note,
        ),
        critic_signals=CriticSearchSignals(
            product_boundary_risk="contained",
            brand_risk="watch",
            execution_risk="contained",
            self_deception_risk="watch",
            risk_note="Still requires pressure testing.",
        ),
        reward_breakdown=RewardBreakdown(
            reward=reward,
            positive_utility=reward,
            risk_penalty=0.0,
            positive_components={"utility": reward},
            risk_components={},
        ),
    )


class UCBSearchControllerTests(unittest.TestCase):
    def test_normal_cold_start_selection_updates_selected_family_state(self):
        controller = UCBSearchController(
            (make_family("trust"), make_family("trial")),
            UCBSearchConfig(candidate_slots_per_round=1),
        )

        selection = controller.select(1)
        updates = controller.update(
            (make_observation("trust", round_index=1),), selection=selection
        )

        self.assertEqual(selection.selected_family_ids, ("trust",))
        self.assertEqual(updates[0].state_after.pull_count, 1)

    def test_boundary_single_registered_family_can_be_selected(self):
        controller = UCBSearchController((make_family("trust"),))

        selection = controller.select(1)

        self.assertEqual(selection.selected_family_ids, ("trust",))

    def test_boundary_slots_equal_registered_families_select_each_once(self):
        controller = UCBSearchController(
            (make_family("trust"), make_family("trial")),
            UCBSearchConfig(candidate_slots_per_round=2),
        )

        selection = controller.select(1)

        self.assertEqual(selection.selected_family_ids, ("trust", "trial"))
        self.assertTrue(all(math.isinf(value) for value in selection.ucb_scores.values()))

    def test_boundary_zero_exploration_uses_guarded_mean_after_cold_start(self):
        controller = UCBSearchController(
            (make_family("trust"), make_family("trial")),
            UCBSearchConfig(exploration_coefficient=0),
        )
        first = controller.select(1)
        controller.update((make_observation("trust", reward=0.3, round_index=1),), selection=first)
        second = controller.select(2)
        controller.update((make_observation("trial", reward=0.8, round_index=2),), selection=second)

        third = controller.select(3)

        self.assertEqual(third.selected_family_ids, ("trial",))

    def test_special_cold_start_walks_to_untested_family_before_reuse(self):
        controller = UCBSearchController(
            (make_family("trust"), make_family("trial"), make_family("repeat"))
        )
        first = controller.select(1)
        controller.update((make_observation("trust", round_index=1),), selection=first)

        second = controller.select(2)

        self.assertEqual(second.selected_family_ids, ("trial",))
        self.assertEqual(second.brief.generation_intents["trial"], "cold_start")

    def test_special_promising_family_brief_requests_refinement(self):
        controller = UCBSearchController(
            (make_family("trust"),),
            UCBSearchConfig(promising_reward_threshold=0.5),
        )
        first = controller.select(1)
        controller.update((make_observation("trust", reward=0.8, round_index=1),), selection=first)

        second = controller.select(2)

        self.assertEqual(second.brief.generation_intents["trust"], "refine_promising")

    def test_special_qualitative_memory_returns_notes_not_rewards(self):
        controller = UCBSearchController((make_family("trust"),))
        first = controller.select(1)
        controller.update(
            (make_observation("trust", reward=0.9, round_index=1, signal_note="Trust cue worked."),),
            selection=first,
        )

        second = controller.select(2)
        memory = second.brief.qualitative_memory["trust"]

        self.assertTrue(any("Trust cue worked" in line for line in memory))
        self.assertFalse(any("0.9" in line for line in memory))

    def test_counterexample_duplicate_family_registry_is_rejected(self):
        with self.assertRaisesRegex(UCBSearchInputError, "unique"):
            UCBSearchController((make_family("trust"), make_family("trust")))

    def test_counterexample_update_requires_all_selected_family_observations(self):
        controller = UCBSearchController(
            (make_family("trust"), make_family("trial")),
            UCBSearchConfig(candidate_slots_per_round=2),
        )
        selection = controller.select(1)

        with self.assertRaisesRegex(UCBSearchInputError, "cover selected"):
            controller.update(
                (make_observation("trust", round_index=1),),
                selection=selection,
            )

        self.assertEqual(controller.total_pulls, 0)

    def test_counterexample_unknown_family_lookup_is_rejected(self):
        controller = UCBSearchController((make_family("trust"),))

        with self.assertRaisesRegex(UCBSearchInputError, "Unknown"):
            controller.state_for("missing")

    def test_limit_long_history_keeps_state_and_selection_finite(self):
        controller = UCBSearchController(
            (make_family("trust"), make_family("trial")),
            UCBSearchConfig(exploration_coefficient=0.4),
        )
        for round_index in range(1, 121):
            selection = controller.select(round_index)
            family_id = selection.selected_family_ids[0]
            controller.update(
                (make_observation(family_id, reward=0.4 + (round_index % 2) * 0.2, round_index=round_index),),
                selection=selection,
            )

        next_selection = controller.select(121)

        self.assertEqual(controller.total_pulls, 120)
        self.assertEqual(len(next_selection.selected_family_ids), 1)


if __name__ == "__main__":
    unittest.main()
