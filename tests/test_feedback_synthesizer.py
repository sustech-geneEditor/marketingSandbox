"""Contract tests for FeedbackSynthesizer."""

from __future__ import annotations

import copy
import unittest

from marketing_sandbox import (
    AdvocacyReaction,
    BehaviorDiagnosis,
    CompetitorReaction,
    ConsumerFeedback,
    FeedbackSynthesisInputError,
    FeedbackSynthesisOutputError,
    FeedbackSynthesizer,
    RepeatPurchaseReaction,
    Strategy,
    StrategyAction,
)


class RecordingBackend:
    """Stable synthesis backend used by contract tests."""

    def __init__(self, response):
        self.response = response
        self.prompts: list[str] = []

    def generate(self, prompt: str):
        self.prompts.append(prompt)
        return copy.deepcopy(self.response)


def make_strategy(**changes) -> Strategy:
    base = {
        "name": "Trust-first trial",
        "hypothesis": "Use product reassurance and a concrete first offer.",
        "actions": (
            StrategyAction(
                category="product",
                summary="Lead with trial pack and return support.",
                reason="Reduce first-use anxiety.",
                product_claims=("trial_pack",),
            ),
            StrategyAction(
                category="price",
                summary="Use a launch price action.",
                reason="Keep first action concrete.",
                parameters={"list_price": 49, "discount_rate": 0.1},
            ),
        ),
        "target_consumers": ("Trust-sensitive commuters",),
        "expected_tradeoffs": ("Bargain-only users may still compare offers.",),
    }
    base.update(changes)
    return Strategy(**base)


def make_feedback(persona_name="Trust-sensitive commuter", **changes) -> ConsumerFeedback:
    base = {
        "persona_name": persona_name,
        "scenario_name": "Competitor trust pressure",
        "first_impression": "The launch feels practical and less risky.",
        "understood_offer": "A bottled tea trial with reassurance.",
        "perceived_positioning": "Convenient and trying to look dependable.",
        "strongest_pull": "Trial support lowers the feeling of waste.",
        "strongest_rejection": "Repeat habit is still not obvious.",
        "current_attitude": "Interested but cautious.",
        "behavior_diagnosis": BehaviorDiagnosis(
            first_signal="Trial support.",
            reference_point="A familiar bottled tea.",
            perceived_risk="Unknown taste and repeat reason.",
            action_friction="Switching from a routine store.",
            dominant_driver="Risk reduction.",
        ),
        "repeat_purchase": RepeatPurchaseReaction(
            feeling="Repeat does not feel automatic.",
            condition="First use must be smooth and reordering easy.",
            habit_or_inertia="Old drink habits still matter.",
        ),
        "competitor_reaction": CompetitorReaction(
            likely_shift="May drift back under competitor pressure.",
            reason="Familiarity is stronger there.",
            retention_condition="A dependable first experience.",
        ),
        "advocacy": AdvocacyReaction(
            recommendation_feeling="Recommendation waits on experience.",
            sharing_feeling="Not ready to share just for an offer.",
            friend_description="A careful new tea trial.",
        ),
        "behavior_notes": (
            "Reference point clearly mattered.",
            "Social proof matters as reassurance.",
        ),
    }
    base.update(changes)
    return ConsumerFeedback(**base)


def make_payload(**changes):
    base = {
        "overall_feel": "This feels like a trust-aware trial strategy, not yet a routine strategy.",
        "who_was_moved": [
            "Cautious commuters moved closer because risk cues became clearer."
        ],
        "who_was_not_moved": [
            "Habit-bound buyers still lack a repeat reason strong enough to switch."
        ],
        "strongest_evidence": [
            "Trial support and reassurance show up in the main positive feedback."
        ],
        "weakest_points": [
            "Repeat-purchase logic feels thinner than first-trial logic."
        ],
        "repeat_purchase_feel": "Repeat depends on a smooth first experience and a natural reorder path.",
        "competitor_pressure_feel": "Competitor familiarity still makes the strategy feel vulnerable.",
        "next_round_focus": [
            "Test a clearer repeat trigger before broadening the launch story."
        ],
        "missing_evidence": [
            "The feedback cannot establish real market demand without outside evidence."
        ],
        "qualitative_tags": ["trust-aware trial", "repeat logic needs work"],
    }
    base.update(changes)
    return base


class FeedbackSynthesizerTests(unittest.TestCase):
    def test_normal_summary_returns_strategy_feel(self):
        backend = RecordingBackend(make_payload())
        synthesizer = FeedbackSynthesizer(backend)

        summary = synthesizer.synthesize(
            make_strategy(),
            [make_feedback()],
            core_target="Trust-sensitive commuters",
        )

        self.assertEqual(summary.strategy_name, "Trust-first trial")
        self.assertIn("trust-aware", summary.overall_feel)
        self.assertEqual(summary.scenario_names, ("Competitor trust pressure",))
        self.assertIn("without outside evidence", summary.missing_evidence[0])

    def test_boundary_single_feedback_batch_is_allowed(self):
        backend = RecordingBackend(make_payload())
        synthesizer = FeedbackSynthesizer(backend)

        summary = synthesizer.synthesize(
            make_strategy(), (make_feedback(),), core_target="Commuters"
        )

        self.assertEqual(len(summary.who_was_moved), 1)
        self.assertIn("one candidate strategy", backend.prompts[0])

    def test_boundary_duplicate_scenarios_are_deduplicated_in_summary(self):
        backend = RecordingBackend(make_payload())
        synthesizer = FeedbackSynthesizer(backend)
        feedbacks = [
            make_feedback("Trust-sensitive commuter"),
            make_feedback("Price-aware explorer"),
        ]

        summary = synthesizer.synthesize(
            make_strategy(), feedbacks, core_target="Core commuters"
        )

        self.assertEqual(summary.scenario_names, ("Competitor trust pressure",))

    def test_boundary_prior_summary_can_be_empty(self):
        backend = RecordingBackend(make_payload())
        synthesizer = FeedbackSynthesizer(backend)

        synthesizer.synthesize(
            make_strategy(), [make_feedback()], core_target="Core commuters"
        )

        self.assertIn("none supplied", backend.prompts[0])

    def test_special_conflicting_feedback_is_rendered_for_synthesis(self):
        backend = RecordingBackend(make_payload())
        synthesizer = FeedbackSynthesizer(backend)
        split_feedback = make_feedback(
            "Price-aware explorer",
            strongest_pull="The launch price action makes trying feel easier.",
            strongest_rejection="The brand story still feels plain.",
            current_attitude="Interested for a one-off trial.",
        )

        synthesizer.synthesize(
            make_strategy(),
            [make_feedback(), split_feedback],
            core_target="Trust-sensitive commuters",
        )

        prompt = backend.prompts[0]
        self.assertIn("one-off trial", prompt)
        self.assertIn("Repeat habit is still not obvious", prompt)

    def test_special_multi_scenario_feedback_keeps_scenario_context(self):
        backend = RecordingBackend(make_payload())
        synthesizer = FeedbackSynthesizer(backend)
        feedbacks = [
            make_feedback(),
            make_feedback(
                "Social proof seeker",
                scenario_name="Normal launch",
                strongest_rejection="Not enough friend talk yet.",
            ),
        ]

        summary = synthesizer.synthesize(
            make_strategy(), feedbacks, core_target="Trust-sensitive commuters"
        )

        self.assertEqual(
            summary.scenario_names, ("Competitor trust pressure", "Normal launch")
        )
        self.assertIn("Normal launch", backend.prompts[0])

    def test_special_prior_summary_reaches_prompt(self):
        backend = RecordingBackend(make_payload())
        synthesizer = FeedbackSynthesizer(backend)

        synthesizer.synthesize(
            make_strategy(),
            [make_feedback()],
            core_target="Trust-sensitive commuters",
            prior_summary="Last round over-indexed on first trial cues.",
        )

        self.assertIn("over-indexed on first trial", backend.prompts[0])

    def test_counterexample_rejects_overall_score_field(self):
        payload = make_payload(overall_score=8)
        synthesizer = FeedbackSynthesizer(RecordingBackend(payload))

        with self.assertRaisesRegex(FeedbackSynthesisOutputError, "scoring or forecast field"):
            synthesizer.synthesize(
                make_strategy(), [make_feedback()], core_target="Core commuters"
            )

    def test_counterexample_rejects_dimension_score_text(self):
        payload = make_payload(
            overall_feel="The dimension score on trust feels strong."
        )
        synthesizer = FeedbackSynthesizer(RecordingBackend(payload))

        with self.assertRaisesRegex(FeedbackSynthesisOutputError, "score, probability"):
            synthesizer.synthesize(
                make_strategy(), [make_feedback()], core_target="Core commuters"
            )

    def test_counterexample_rejects_market_forecast_key_nested(self):
        payload = make_payload()
        payload["qualitative_tags"] = [{"market_share": "not allowed"}]
        synthesizer = FeedbackSynthesizer(RecordingBackend(payload))

        with self.assertRaisesRegex(FeedbackSynthesisOutputError, "scoring or forecast field"):
            synthesizer.synthesize(
                make_strategy(), [make_feedback()], core_target="Core commuters"
            )

    def test_counterexample_rejects_empty_feedback_batch(self):
        synthesizer = FeedbackSynthesizer(RecordingBackend(make_payload()))

        with self.assertRaisesRegex(FeedbackSynthesisInputError, "at least one"):
            synthesizer.synthesize(make_strategy(), [], core_target="Core commuters")

    def test_limit_dense_feedback_batch_still_synthesizes(self):
        feedbacks = [
            make_feedback(
                f"Persona {index}",
                scenario_name=f"Scenario {index % 4}",
                current_attitude=f"Qualitative attitude {index} with a distinct tension.",
            )
            for index in range(180)
        ]
        backend = RecordingBackend(make_payload())
        synthesizer = FeedbackSynthesizer(backend)

        summary = synthesizer.synthesize(
            make_strategy(), feedbacks, core_target="Trust-sensitive commuters"
        )

        self.assertEqual(summary.qualitative_tags[0], "trust-aware trial")
        self.assertIn("Persona 179", backend.prompts[0])
        self.assertGreater(len(backend.prompts[0]), len(feedbacks))

    def test_ucb_search_signals_are_parsed_as_categorical_labels(self):
        payload = make_payload(
            search_signals={
                "core_target_response": "mixed",
                "trial_momentum": "conditional",
                "strategy_clarity": "partial",
                "repeat_logic": "weak",
                "competitor_resilience": "fragile",
                "evidence_consistency": "mixed",
                "signal_note": "Trust improves before repeat logic catches up.",
            }
        )
        synthesizer = FeedbackSynthesizer(RecordingBackend(payload))

        summary = synthesizer.synthesize(
            make_strategy(), [make_feedback()], core_target="Core commuters"
        )

        self.assertEqual(summary.search_signals.trial_momentum, "conditional")
        self.assertIn("search_signals", synthesizer.last_prompt)

    def test_ucb_search_signals_reject_unknown_label(self):
        payload = make_payload(
            search_signals={
                "core_target_response": "moved",
                "trial_momentum": "conditional",
                "strategy_clarity": "shiny",
                "repeat_logic": "weak",
                "competitor_resilience": "fragile",
                "evidence_consistency": "mixed",
                "signal_note": "The label should stay controlled.",
            }
        )
        synthesizer = FeedbackSynthesizer(RecordingBackend(payload))

        with self.assertRaisesRegex(FeedbackSynthesisOutputError, "must use one of"):
            synthesizer.synthesize(
                make_strategy(), [make_feedback()], core_target="Core commuters"
            )

    def test_ucb_search_signal_note_still_rejects_fake_score_text(self):
        payload = make_payload(
            search_signals={
                "core_target_response": "moved",
                "trial_momentum": "pulled_closer",
                "strategy_clarity": "clear",
                "repeat_logic": "conditional",
                "competitor_resilience": "fragile",
                "evidence_consistency": "mixed",
                "signal_note": "The overall score looks high.",
            }
        )
        synthesizer = FeedbackSynthesizer(RecordingBackend(payload))

        with self.assertRaisesRegex(FeedbackSynthesisOutputError, "score"):
            synthesizer.synthesize(
                make_strategy(), [make_feedback()], core_target="Core commuters"
            )


if __name__ == "__main__":
    unittest.main()
