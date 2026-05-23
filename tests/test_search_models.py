"""Search data-contract tests for family-level sandbox search."""

from __future__ import annotations

import unittest

from marketing_sandbox import (
    CriticSearchSignals,
    FamilyArmState,
    FeedbackSearchSignals,
    RewardBreakdown,
    SearchBrief,
    SearchModelError,
    SearchObservation,
    SearchSelection,
    StrategyFamily,
    UCBSearchConfig,
)


def make_family(family_id="trust_risk_reduction", **changes):
    base = {
        "family_id": family_id,
        "name": "Trust and risk reduction",
        "core_barrier": "Cautious buyers fear a first-use mistake.",
        "win_mechanism": "Make the first choice feel believable and reversible.",
        "generation_guidance": "Use trust cues before piling on more promotion.",
        "expected_action_patterns": ("product reassurance", "focused evidence"),
        "failure_signals": ("discount voice overwhelms trust",),
    }
    base.update(changes)
    return StrategyFamily(**base)


def make_feedback_signals(**changes):
    base = {
        "core_target_response": "moved",
        "trial_momentum": "pulled_closer",
        "strategy_clarity": "clear",
        "repeat_logic": "conditional",
        "competitor_resilience": "fragile",
        "evidence_consistency": "mixed",
        "signal_note": "Core cautious buyers saw the offer more clearly.",
    }
    base.update(changes)
    return FeedbackSearchSignals(**base)


def make_critic_signals(**changes):
    base = {
        "product_boundary_risk": "contained",
        "brand_risk": "watch",
        "execution_risk": "contained",
        "self_deception_risk": "watch",
        "risk_note": "Repeat proof is still thinner than first-trial proof.",
    }
    base.update(changes)
    return CriticSearchSignals(**base)


def make_breakdown(reward=0.6):
    return RewardBreakdown(
        reward=reward,
        positive_utility=0.8,
        risk_penalty=0.2,
        positive_components={"trial_momentum": 0.2},
        risk_components={"brand_risk": 0.04},
    )


def make_observation(family_id="trust_risk_reduction", **changes):
    base = {
        "round_index": 1,
        "family_id": family_id,
        "strategy_name": "Trust-first trial",
        "summary_signals": make_feedback_signals(),
        "critic_signals": make_critic_signals(),
        "reward_breakdown": make_breakdown(),
    }
    base.update(changes)
    return SearchObservation(**base)


class SearchModelsTests(unittest.TestCase):
    def test_normal_strategy_family_keeps_one_win_logic(self):
        family = make_family()

        self.assertEqual(family.family_id, "trust_risk_reduction")
        self.assertIn("reversible", family.win_mechanism)

    def test_boundary_strategy_family_accepts_single_pattern_and_failure(self):
        family = make_family(
            expected_action_patterns=("trial pack",),
            failure_signals=("repeat reason missing",),
        )

        self.assertEqual(family.expected_action_patterns, ("trial pack",))

    def test_boundary_strategy_family_trims_human_text_fields(self):
        family = make_family(
            name="  Trust family  ",
            core_barrier="  Trust barrier  ",
            win_mechanism="  Risk falls  ",
            generation_guidance="  Stay concrete  ",
        )

        self.assertEqual(family.name, "Trust family")
        self.assertEqual(family.generation_guidance, "Stay concrete")

    def test_boundary_strategy_family_accepts_uppercase_ascii_identifier(self):
        family = make_family("TrustFamily")

        self.assertEqual(family.family_id, "TrustFamily")

    def test_boundary_ucb_config_allows_one_slot_and_zero_exploration(self):
        config = UCBSearchConfig(exploration_coefficient=0)

        self.assertEqual(config.candidate_slots_per_round, 1)
        self.assertEqual(config.exploration_coefficient, 0)

    def test_boundary_search_brief_can_start_without_memory(self):
        brief = SearchBrief(
            selected_families=(make_family(),),
            generation_intents={"trust_risk_reduction": "cold_start"},
        )

        self.assertEqual(brief.expected_strategy_count, 1)
        self.assertIn("no guarded family memory yet", brief.describe())

    def test_special_search_brief_renders_guarded_family_memory(self):
        brief = SearchBrief(
            selected_families=(make_family(),),
            generation_intents={"trust_risk_reduction": "explore_variant"},
            qualitative_memory={
                "trust_risk_reduction": ("Competitor pressure exposed repeat fragility.",)
            },
        )

        rendered = brief.describe()
        self.assertIn("explore_variant", rendered)
        self.assertIn("repeat fragility", rendered)

    def test_special_strategy_family_preserves_mixed_action_patterns(self):
        family = make_family(
            expected_action_patterns=(
                "product reassurance",
                "price stays bounded",
                "promotion carries evidence",
            ),
            failure_signals=(
                "product claim outruns facts",
                "trust story becomes noisy",
            ),
        )

        self.assertIn("promotion carries evidence", family.expected_action_patterns)
        self.assertEqual(len(family.failure_signals), 2)

    def test_special_strategy_family_distinguishes_barrier_from_win_mechanism(self):
        family = make_family(
            core_barrier="Routine buyers do not see a switching reason.",
            win_mechanism="Build a repeat trigger after a credible first use.",
        )

        self.assertNotEqual(family.core_barrier, family.win_mechanism)
        self.assertIn("repeat trigger", family.win_mechanism)

    def test_special_observation_extracts_summary_and_critic_memory(self):
        observation = make_observation()

        self.assertEqual(len(observation.qualitative_memory), 2)
        self.assertIn("summary", observation.qualitative_memory[0])
        self.assertIn("critic", observation.qualitative_memory[1])

    def test_special_arm_state_updates_mean_reward_from_observation(self):
        state = FamilyArmState("trust_risk_reduction")

        updated = state.add_observation(make_observation())

        self.assertEqual(updated.pull_count, 1)
        self.assertAlmostEqual(updated.mean_reward, 0.6)
        self.assertEqual(updated.last_selected_round, 1)

    def test_counterexample_strategy_family_rejects_non_ascii_identifier(self):
        with self.assertRaisesRegex(SearchModelError, "ASCII identifier"):
            make_family("信任")

    def test_counterexample_strategy_family_rejects_empty_action_patterns(self):
        with self.assertRaisesRegex(SearchModelError, "expected_action_patterns"):
            make_family(expected_action_patterns=())

    def test_counterexample_strategy_family_rejects_empty_failure_signals(self):
        with self.assertRaisesRegex(SearchModelError, "failure_signals"):
            make_family(failure_signals=())

    def test_counterexample_strategy_family_rejects_numeric_identifier_prefix(self):
        with self.assertRaisesRegex(SearchModelError, "ASCII identifier"):
            make_family("1trust")

    def test_counterexample_brief_rejects_memory_for_unselected_family(self):
        with self.assertRaisesRegex(SearchModelError, "unselected families"):
            SearchBrief(
                selected_families=(make_family(),),
                generation_intents={"trust_risk_reduction": "cold_start"},
                qualitative_memory={"trial_value_entry": ("Wrong memory.",)},
            )

    def test_counterexample_reward_breakdown_rejects_reward_above_one(self):
        with self.assertRaisesRegex(SearchModelError, r"\[0, 1\]"):
            make_breakdown(reward=1.2)

    def test_limit_strategy_family_keeps_many_failure_signals(self):
        family = make_family(
            expected_action_patterns=tuple(
                f"pattern {index}" for index in range(60)
            ),
            failure_signals=tuple(f"failure {index}" for index in range(60)),
        )

        self.assertEqual(family.expected_action_patterns[-1], "pattern 59")
        self.assertEqual(family.failure_signals[-1], "failure 59")

    def test_limit_selection_keeps_many_family_scores_auditable(self):
        families = tuple(make_family(f"family_{index}") for index in range(40))
        brief = SearchBrief(
            selected_families=families,
            generation_intents={item.family_id: "cold_start" for item in families},
        )
        selection = SearchSelection(
            round_index=1,
            brief=brief,
            selection_reasons={item.family_id: "cold" for item in families},
            ucb_scores={item.family_id: float("inf") for item in families},
        )

        self.assertEqual(len(selection.selected_family_ids), 40)
        self.assertEqual(selection.selected_family_ids[-1], "family_39")


if __name__ == "__main__":
    unittest.main()
