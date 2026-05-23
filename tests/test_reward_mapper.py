"""Contract tests for deterministic qualitative reward mapping."""

from __future__ import annotations

import unittest

from marketing_sandbox import (
    CriticSearchSignals,
    FeedbackSearchSignals,
    RewardMapper,
    RewardMappingError,
)


def make_feedback_signals(**changes):
    base = {
        "core_target_response": "moved",
        "trial_momentum": "pulled_closer",
        "strategy_clarity": "clear",
        "repeat_logic": "natural",
        "competitor_resilience": "holds",
        "evidence_consistency": "consistent",
        "signal_note": "The qualitative feedback is coherent.",
    }
    base.update(changes)
    return FeedbackSearchSignals(**base)


def make_critic_signals(**changes):
    base = {
        "product_boundary_risk": "contained",
        "brand_risk": "contained",
        "execution_risk": "contained",
        "self_deception_risk": "contained",
        "risk_note": "No outsized boundary risk appeared in this round.",
    }
    base.update(changes)
    return CriticSearchSignals(**base)


class RewardMapperTests(unittest.TestCase):
    def test_normal_strong_feedback_and_contained_risk_map_to_full_reward(self):
        breakdown = RewardMapper().map(make_feedback_signals(), make_critic_signals())

        self.assertAlmostEqual(breakdown.reward, 1.0)
        self.assertIn("not a market forecast", breakdown.mapping_note)

    def test_boundary_negative_feedback_clamps_reward_at_zero(self):
        breakdown = RewardMapper().map(
            make_feedback_signals(
                core_target_response="unmoved",
                trial_momentum="pushed_away",
                strategy_clarity="confusing",
                repeat_logic="weak",
                competitor_resilience="displaced",
                evidence_consistency="thin",
            ),
            make_critic_signals(
                product_boundary_risk="serious",
                brand_risk="serious",
                execution_risk="serious",
                self_deception_risk="serious",
            ),
        )

        self.assertEqual(breakdown.reward, 0.0)

    def test_boundary_mid_labels_keep_conditional_reward(self):
        breakdown = RewardMapper().map(
            make_feedback_signals(
                core_target_response="mixed",
                trial_momentum="conditional",
                strategy_clarity="partial",
                repeat_logic="conditional",
                competitor_resilience="fragile",
                evidence_consistency="mixed",
            ),
            make_critic_signals(),
        )

        self.assertAlmostEqual(breakdown.reward, 0.5)

    def test_boundary_watch_risks_only_subtract_declared_weights(self):
        breakdown = RewardMapper().map(
            make_feedback_signals(),
            make_critic_signals(
                product_boundary_risk="watch",
                brand_risk="watch",
                execution_risk="watch",
                self_deception_risk="watch",
            ),
        )

        self.assertAlmostEqual(breakdown.risk_penalty, 0.175)
        self.assertLess(breakdown.reward, 1.0)

    def test_special_product_boundary_serious_caps_at_design_limit(self):
        breakdown = RewardMapper().map(
            make_feedback_signals(),
            make_critic_signals(product_boundary_risk="serious"),
        )

        self.assertEqual(breakdown.reward, 0.35)
        self.assertIn("serious_product_boundary_risk", breakdown.applied_caps)

    def test_special_self_deception_serious_caps_flattering_round(self):
        breakdown = RewardMapper().map(
            make_feedback_signals(),
            make_critic_signals(self_deception_risk="serious"),
        )

        self.assertEqual(breakdown.reward, 0.45)
        self.assertIn("serious_self_deception_risk", breakdown.applied_caps)

    def test_special_component_breakdown_keeps_trial_weight_visible(self):
        breakdown = RewardMapper().map(
            make_feedback_signals(trial_momentum="conditional"),
            make_critic_signals(brand_risk="watch"),
        )

        self.assertAlmostEqual(breakdown.positive_components["trial_momentum"], 0.1)
        self.assertAlmostEqual(breakdown.risk_components["brand_risk"], 0.04)

    def test_counterexample_missing_feedback_signals_is_rejected(self):
        with self.assertRaisesRegex(RewardMappingError, "FeedbackSearchSignals"):
            RewardMapper().map(None, make_critic_signals())

    def test_counterexample_unknown_feedback_label_is_rejected(self):
        with self.assertRaisesRegex(RewardMappingError, "unknown feedback"):
            RewardMapper().map(
                make_feedback_signals(strategy_clarity="crystal"),
                make_critic_signals(),
            )

    def test_limit_repeated_dense_mapping_stays_deterministic(self):
        mapper = RewardMapper()
        rewards = [
            mapper.map(
                make_feedback_signals(evidence_consistency="mixed"),
                make_critic_signals(execution_risk="watch"),
            ).reward
            for _ in range(200)
        ]

        self.assertEqual(len(set(rewards)), 1)
        self.assertAlmostEqual(rewards[0], 0.925)


if __name__ == "__main__":
    unittest.main()
